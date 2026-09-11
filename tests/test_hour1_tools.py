"""Hour one acceptance criteria. Read the failing test before changing a tool."""

from __future__ import annotations

import json
import time
from datetime import datetime

import psycopg
import pytest
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import TypeAdapter

from agentlab.db import get_pool
from agentlab.mcp_server import tools as t

pytestmark = pytest.mark.usefixtures("warehouse")
START, END = "2026-08-01", "2026-08-31"


def check(result, shape, start=START, end=END):
    assert isinstance(result, dict), "Tools return JSON-compatible typed dictionaries."
    TypeAdapter(shape).validate_python(result, strict=True)
    assert result["period"] == {"start_date": start, "end_date": end}
    assert datetime.fromisoformat(result["generated_at"]).utcoffset() is not None
    assert len(result.get("rows", [])) <= 500, "Never expose more than 500 rows in one response."
    json.dumps(result)  # No Decimal/date objects leaking through the JSON contract.


@pytest.mark.smoke
def test_worked_totals(warehouse):
    result = t.totals_for_period(START, END)
    check(result, t.TotalsResult)
    expected = warehouse(
        "SELECT SUM(impressions)::bigint i, SUM(clicks)::bigint c, "
        "SUM(spend)::float s, SUM(revenue)::float r, "
        "SUM(impressions)::float/SUM(requests) f FROM fact_delivery "
        "WHERE day BETWEEN %s AND %s",
        (START, END),
    )[0]
    assert result["impressions"] == expected["i"]
    assert result["clicks"] == expected["c"]
    assert result["spend"] == pytest.approx(expected["s"])
    assert result["revenue"] == pytest.approx(expected["r"])
    assert result["fill_rate"] == pytest.approx(expected["f"])


@pytest.mark.smoke
def test_worked_filter_empty_and_validation(warehouse):
    filtered = t.totals_for_period(START, END, "it")
    check(filtered, t.TotalsResult)
    assert filtered["country"] == "IT"
    expected = warehouse(
        "SELECT SUM(impressions) i FROM fact_delivery WHERE day BETWEEN %s AND %s AND country='IT'",
        (START, END),
    )[0]["i"]
    assert filtered["impressions"] == expected
    empty = t.totals_for_period("2030-01-01", "2030-01-02")
    assert empty["impressions"] == empty["spend"] == empty["fill_rate"] == 0
    with pytest.raises(ValueError):
        t.totals_for_period(END, START)


@pytest.mark.smoke
def test_seed_and_database_boundary(warehouse):
    counts = warehouse(
        "SELECT (SELECT COUNT(*) FROM publisher) p, "
        "(SELECT COUNT(*) FROM advertiser) a, (SELECT COUNT(*) FROM plan) plans, "
        "COUNT(*) n, MIN(day)::text first, MAX(day)::text last FROM fact_delivery"
    )[0]
    assert counts == {
        "p": 60,
        "a": 120,
        "plans": 2160,
        "n": 1515240,
        "first": "2025-03-01",
        "last": "2026-08-31",
    }
    with get_pool().connection() as conn:
        assert (
            conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on"
        )
        assert conn.execute("SHOW statement_timeout").fetchone()["statement_timeout"] == "2s"
        assert conn.execute("SELECT current_user u").fetchone()["u"] == "agentlab_readonly"
    # Even disabling the default read-only setting cannot grant write privileges.
    with get_pool().connection() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.transaction():
                conn.execute("SET TRANSACTION READ WRITE")
                conn.execute("UPDATE publisher SET name=name WHERE false")
    indexes = {
        row["indexname"]
        for row in warehouse("SELECT indexname FROM pg_indexes WHERE tablename='fact_delivery'")
    }
    assert {
        "delivery_grain_idx",
        "delivery_country_day_idx",
        "delivery_publisher_day_idx",
        "delivery_advertiser_day_idx",
    } <= indexes


@pytest.mark.smoke
def test_sql_aggregation_budget(warehouse):
    started = time.perf_counter()
    result = t.totals_for_period("2025-03-01", END)
    elapsed = time.perf_counter() - started
    assert result["impressions"] > 1_000_000
    assert elapsed < 3.0, f"Full-range SQL aggregation took {elapsed:.2f}s; budget is 3s."
    # A time budget alone does not prove where aggregation happened: inspect SQL too.
    plan = warehouse("EXPLAIN (FORMAT JSON) " + t.TOTALS_SQL, ("2025-03-01", END))
    assert "Aggregate" in json.dumps(plan), "PostgreSQL must own aggregation."


@pytest.mark.smoke
def test_seed_has_the_promised_reporting_patterns(warehouse):
    rows = warehouse("""
        SELECT publisher_id,
          SUM(impressions) FILTER (WHERE day<'2026-05-01')::float /
            SUM(requests) FILTER (WHERE day<'2026-05-01') before_fill,
          SUM(impressions) FILTER (WHERE day>='2026-05-01')::float /
            SUM(requests) FILTER (WHERE day>='2026-05-01') after_fill
        FROM fact_delivery WHERE day>='2026-03-01' GROUP BY publisher_id
    """)
    assert {r["publisher_id"] for r in rows if r["before_fill"] - r["after_fill"] > 0.1} == {
        7,
        19,
        43,
    }
    season = warehouse("""
        SELECT AVG(requests) FILTER (WHERE EXTRACT(ISODOW FROM day)>=6)::float weekend,
          AVG(requests) FILTER (WHERE EXTRACT(ISODOW FROM day)<6)::float weekday,
          AVG(requests) FILTER (WHERE day BETWEEN '2025-10-01' AND '2025-12-31')::float q4,
          AVG(requests) FILTER (WHERE day BETWEEN '2025-07-01' AND '2025-09-30')::float q3
        FROM fact_delivery
    """)[0]
    assert season["weekend"] < season["weekday"] * 0.85
    assert season["q4"] > season["q3"] * 1.25


@pytest.mark.smoke
async def test_http_discovery_and_worked_tool(mcp_url):
    client = MultiServerMCPClient({"lab": {"transport": "streamable_http", "url": mcp_url}})
    discovered = {tool.name: tool for tool in await client.get_tools()}
    assert set(discovered) == {
        "totals_for_period",
        "publisher_mix",
        "period_over_period",
        "pacing_against_plan",
        "run_query",
        "refusals",
    }
    assert "inclusive" in discovered["totals_for_period"].description
    assert "start_date" in discovered["totals_for_period"].args
    result = await discovered["totals_for_period"].ainvoke({"start_date": START, "end_date": END})
    assert "impressions" in str(result)


def test_publisher_mix(warehouse):
    result = t.publisher_mix(START, END, limit=10)
    check(result, t.PublisherResult)
    expected = warehouse(
        "SELECT publisher_id, SUM(spend)::float spend FROM fact_delivery "
        "WHERE day BETWEEN %s AND %s GROUP BY publisher_id "
        "ORDER BY spend DESC,publisher_id LIMIT 10",
        (START, END),
    )
    assert [r["publisher_id"] for r in result["rows"]] == [r["publisher_id"] for r in expected]
    assert [r["spend"] for r in result["rows"]] == pytest.approx([r["spend"] for r in expected])


def test_row_caps():
    check(t.publisher_mix(START, END, limit=9999), t.PublisherResult)
    with pytest.raises(ValueError):
        t.publisher_mix(START, END, limit=0)
    for limit in (1, 7, 500, 9999):
        result = t.run_query(
            "SELECT * FROM fact_delivery ORDER BY day,publisher_id,advertiser_id,"
            "country,device LIMIT 10000",
            limit=limit,
        )
        check(result, t.QueryResult, None, None)
        assert len(result["rows"]) == min(limit, 500)


def test_period_over_period():
    result = t.period_over_period(START, END, "2026-07-01", "2026-07-31")
    check(result, t.ComparisonResult)
    current = t.totals_for_period(START, END)
    prior = t.totals_for_period("2026-07-01", "2026-07-31")
    assert result["prior_period"] == {"start_date": "2026-07-01", "end_date": "2026-07-31"}
    assert result["spend_delta"] == pytest.approx(current["spend"] - prior["spend"])
    assert result["spend_delta_pct"] == pytest.approx(result["spend_delta"] / prior["spend"])
    assert result["impressions_delta"] == current["impressions"] - prior["impressions"]
    assert result["fill_rate_delta"] == pytest.approx(current["fill_rate"] - prior["fill_rate"])
    assert "current" not in result and "prior" not in result, (
        "Return deltas, not two raw total objects."
    )


def test_zero_prior():
    result = t.period_over_period(START, END, "2030-01-01", "2030-01-31")
    assert result["spend_delta_pct"] is None, "Zero prior must produce null, not infinity."


def test_pacing_against_plan(warehouse):
    result = t.pacing_against_plan("2026-08")
    check(result, t.PacingResult)
    assert len(result["rows"]) == 120
    laggard = result["rows"][0]
    assert laggard["advertiser_id"] == 17
    assert laggard["pacing_ratio"] == pytest.approx(0.48, abs=0.001)
    expected = warehouse(
        "SELECT planned_spend::float p FROM plan WHERE advertiser_id=17 AND month='2026-08-01'"
    )[0]["p"]
    assert laggard["planned_spend"] == expected, "Join each plan once; don't multiply its budget."
    assert laggard["variance"] == pytest.approx(laggard["actual_spend"] - expected)
    assert t.pacing_against_plan("2030-01")["rows"] == []
    with pytest.raises(ValueError):
        t.pacing_against_plan("2026-13")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO publisher VALUES (999,'bad','standard','GB')",
        "UPDATE publisher SET name='bad'",
        "DELETE FROM publisher",
        "DROP TABLE publisher",
        "ALTER TABLE publisher ADD x int",
        "GRANT ALL ON publisher TO PUBLIC",
        "SELECT * FROM fact_delivery",
        "SELECT * FROM publisher LIMIT ALL",
        "SELECT * FROM publisher LIMIT -1",
        "SELECT * FROM publisher LIMIT 3; DROP TABLE plan",
        "WITH d AS (DELETE FROM publisher RETURNING *) SELECT * FROM d ORDER BY 1 LIMIT 1",
        "SELECT * INTO stolen FROM publisher LIMIT 1",
        "SELECT * FROM publisher ORDER BY 1 LIMIT 1 FOR UPDATE",
        "SELECT pg_sleep(10) ORDER BY 1 LIMIT 1",
        "SELECT set_config('statement_timeout','0',false) ORDER BY 1 LIMIT 1",
        "SELECT * FROM pg_catalog.pg_authid ORDER BY 1 LIMIT 1",
        "SELECT * FROM information_schema.tables ORDER BY 1 LIMIT 1",
        "SELECT * FROM publisher LIMIT 5",  # paging needs stable ordering
    ],
)
def test_run_query_rejects_unsafe_or_unbounded(sql):
    with pytest.raises(ValueError, match="(?i)select|limit|allow|read.only|order|policy|blocked"):
        t.run_query(sql)


def test_run_query_limit_and_paging():
    sql = "SELECT publisher_id FROM publisher ORDER BY publisher_id LIMIT 25"
    first = t.run_query(sql, limit=10)
    check(first, t.QueryResult, None, None)
    assert [r["publisher_id"] for r in first["rows"]] == list(range(1, 11))
    assert first["next_cursor"], "A bounded result larger than a page needs a continuation cursor."
    second = t.run_query(sql, limit=10, cursor=first["next_cursor"])
    third = t.run_query(sql, limit=10, cursor=second["next_cursor"])
    assert [r["publisher_id"] for r in second["rows"]] == list(range(11, 21))
    assert [r["publisher_id"] for r in third["rows"]] == list(range(21, 26))
    assert third["next_cursor"] is None
    with pytest.raises(ValueError):
        t.run_query(sql, limit=10, cursor=first["next_cursor"] + "broken")
    with pytest.raises(ValueError):
        t.run_query(sql.replace("25", "24"), limit=10, cursor=first["next_cursor"])
    with pytest.raises(ValueError):
        t.run_query(sql, limit=0)


def test_run_query_timeout(monkeypatch):
    # pg_sleep is correctly refused. A tiny DB timeout exercises a permitted, costly SELECT.
    original = t.fetch_all

    def short_query(sql, params=()):
        with get_pool().connection() as conn:
            with conn.transaction():
                conn.execute("SET LOCAL statement_timeout = '1ms'")
                return conn.execute(sql, params).fetchall()

    monkeypatch.setattr(t, "fetch_all", short_query)
    with pytest.raises((ValueError, psycopg.errors.QueryCanceled)):
        t.run_query(
            "SELECT SUM(a.requests*b.requests::bigint) AS n FROM fact_delivery a "
            "CROSS JOIN fact_delivery b ORDER BY n LIMIT 1"
        )
    monkeypatch.setattr(t, "fetch_all", original)
    assert t.totals_for_period(START, END)["impressions"] > 0, (
        "Pool must recover after cancellation."
    )


def test_refusals():
    result = t.refusals()
    check(result, t.RefusalsResult, None, None)
    text = " ".join(result["refusals"]).lower()
    for word in ("write", "credentials", "pii", "unbounded", "system", "external"):
        assert word in text, f"State the boundary on {word}."
