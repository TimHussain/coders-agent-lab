"""Hour one. The docstring IS the model-facing tool description: write it as an API.

SQL belongs here. Models choose tools; PostgreSQL filters, joins and calculates.
Dates are inclusive ISO dates; ratios are fractions, not percentages.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from typing_extensions import TypedDict

from agentlab.db import fetch_all


class Period(TypedDict):
    start_date: str | None
    end_date: str | None


class Envelope(TypedDict):
    period: Period
    generated_at: str


class TotalsResult(Envelope):
    country: str | None
    impressions: int
    clicks: int
    spend: float
    revenue: float
    fill_rate: float


class PublisherRow(TypedDict):
    publisher_id: int
    name: str
    spend: float
    impressions: int
    fill_rate: float


class PublisherResult(Envelope):
    rows: list[PublisherRow]


class ComparisonResult(Envelope):
    prior_period: Period
    spend_delta: float
    spend_delta_pct: float | None
    impressions_delta: int
    fill_rate_delta: float


class PacingRow(TypedDict):
    advertiser_id: int
    name: str
    actual_spend: float
    planned_spend: float
    pacing_ratio: float | None
    variance: float


class PacingResult(Envelope):
    rows: list[PacingRow]


class QueryResult(Envelope):
    rows: list[dict]
    next_cursor: str | None


class RefusalsResult(Envelope):
    refusals: list[str]


def period(start_date: str, end_date: str) -> Period:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must be on or before end_date")
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}


def envelope(bounds: Period | None = None) -> Envelope:
    return {
        "period": bounds or {"start_date": None, "end_date": None},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


TOTALS_SQL = """
SELECT COALESCE(SUM(impressions),0)::bigint AS impressions,
       COALESCE(SUM(clicks),0)::bigint AS clicks,
       COALESCE(SUM(spend),0)::double precision AS spend,
       COALESCE(SUM(revenue),0)::double precision AS revenue,
       COALESCE(SUM(impressions)::numeric / NULLIF(SUM(requests),0),0)::double precision
         AS fill_rate
FROM fact_delivery WHERE day BETWEEN %s AND %s
"""


def totals_for_period(start_date: str, end_date: str, country: str | None = None) -> TotalsResult:
    """Return totals for inclusive ISO dates, optionally filtered by ISO country code.

    Use for a single reporting period. Returns impressions, clicks, spend, revenue
    and fill_rate=sum(impressions)/sum(requests), plus period, country and UTC
    generated_at. Empty periods return zeroes. Amounts are synthetic currency units.
    Use period_over_period for comparisons; do not subtract independently fetched totals.
    """
    bounds = period(start_date, end_date)
    if country is not None:
        country = country.upper()
        if len(country) != 2 or not country.isascii() or not country.isalpha():
            raise ValueError("country must be a two-letter ISO country code")
    sql = TOTALS_SQL + (" AND country = %s" if country is not None else "")
    params = (start_date, end_date, country) if country is not None else (start_date, end_date)
    row = fetch_all(sql, params)[0]
    return {**envelope(bounds), "country": country, **row}


def publisher_mix(start_date: str, end_date: str, limit: int = 10) -> PublisherResult:
    """Return publishers ranked by spend DESC, then publisher_id ASC for inclusive dates.

    Aggregate in SQL before LIMIT. Rows contain publisher_id, name, spend,
    impressions and weighted fill_rate. Clamp positive limit to 500; reject <=0.
    Return period and UTC generated_at. See test_publisher_mix and test_row_caps.
    """
    raise NotImplementedError(
        "H1.1: Implement publisher_mix: SQL aggregation, ranked rows, envelope."
    )


def period_over_period(
    current_start: str, current_end: str, prior_start: str, prior_end: str
) -> ComparisonResult:
    """Calculate current-minus-prior deltas inside one SQL statement/snapshot.

    Return period, prior_period, generated_at, spend_delta, spend_delta_pct
    (fraction of prior; null when prior spend is zero), impressions_delta and
    fill_rate_delta (difference of weighted ratios). Do not return two raw totals.
    See test_period_over_period and test_zero_prior.
    """
    raise NotImplementedError(
        "H1.2: Implement period_over_period: the database returns the deltas."
    )


def pacing_against_plan(month: str) -> PacingResult:
    """For YYYY-MM, return all planned advertisers, including those with no delivery.

    Rows: advertiser_id, name, actual_spend, planned_spend, pacing_ratio (actual/
    planned; null for zero plan), variance (actual-planned). Aggregate actuals
    BEFORE joining plans to avoid budget multiplication. Order by pacing_ratio
    ASC NULLS LAST then advertiser_id; cap at 500. Echo the full month in period
    and UTC generated_at. See test_pacing_against_plan.
    """
    raise NotImplementedError("H1.3: Implement pacing_against_plan without multiplying plan rows.")


def run_query(sql: str, limit: int = 500, cursor: str | None = None) -> QueryResult:
    """Governed SELECT escape hatch: bounded rows, read-only connection, 2s timeout.

    Accept one SELECT with an explicit positive integer LIMIT and stable ORDER BY.
    Only public warehouse tables and an allowlist of aggregate/scalar functions;
    reject writes, DDL, grants, system tables, functions with side effects, SELECT
    INTO, locking, stacked statements and unbounded queries. Add an outer LIMIT
    of min(limit,500), regardless of the supplied SQL. Cap the full result at 5000.
    Return rows, next_cursor, period with null dates, UTC generated_at. Continue
    with identical SQL/limit and the opaque cursor; tampered, expired or mismatched
    cursors must raise ValueError. Paging is over this immutable synthetic dataset.
    See test_run_query_*; a keyword regex alone is insufficient.
    """
    raise NotImplementedError("H1.4: Implement run_query: SELECT policy, forced LIMIT and paging.")


def refusals() -> RefusalsResult:
    """Return the written refusal policy in refusals[], plus period(null dates), generated_at.

    Cover writes/schema changes, credentials/PII, unbounded exports, system tables,
    external access and unsupported SQL. The policy describes enforced boundaries;
    it does not enforce them itself. See test_refusals.
    """
    raise NotImplementedError("H1.5: Implement refusals: state the server's enforced boundaries.")
