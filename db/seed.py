"""Deterministic warehouse generator. Run automatically by the Postgres image.

Uses only the standard library and psql. COPY receives in-memory daily buffers;
no CSV file or third-party Python installation is needed inside the container.
The transaction, advisory lock and seed marker make reruns safe and atomic.
"""

from __future__ import annotations

import io
import logging
import os
import random
import subprocess
import time
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

START = date(2025, 3, 1)
END = date(2026, 8, 31)
SEED = 42
VERSION = 1
COUNTRIES = ("GB", "IT", "DE", "FR", "US", "ES")
DEVICES = ("desktop", "mobile", "tablet")
INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS delivery_grain_idx
 ON fact_delivery(day,publisher_id,advertiser_id,country,device);
CREATE INDEX IF NOT EXISTS delivery_country_day_idx ON fact_delivery(country,day);
CREATE INDEX IF NOT EXISTS delivery_publisher_day_idx ON fact_delivery(publisher_id,day);
CREATE INDEX IF NOT EXISTS delivery_advertiser_day_idx ON fact_delivery(advertiser_id,day);
CREATE INDEX IF NOT EXISTS plan_month_advertiser_idx ON plan(month,advertiser_id);
ANALYZE publisher; ANALYZE advertiser; ANALYZE plan; ANALYZE fact_delivery;
"""


def seed() -> None:
    started = time.perf_counter()
    cmd = [
        "psql",
        "-X",
        "-q",
        "-A",
        "-t",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        os.getenv("POSTGRES_USER", "agentlab"),
        "-d",
        os.getenv("POSTGRES_DB", "agentlab"),
    ]
    # Read the marker while holding the lock, BEFORE streaming any COPY data.
    # psql cannot skip COPY payloads safely inside a false conditional branch.
    process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert process.stdin is not None and process.stdout is not None
    out = process.stdin
    out.write("BEGIN; SELECT pg_advisory_xact_lock(420042);\n")
    out.write(
        "SELECT CASE WHEN EXISTS(SELECT 1 FROM seed_status WHERE id=1 AND ready) "
        "THEN 'READY' ELSE 'EMPTY' END;\n"
    )
    out.flush()
    while True:
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("Unable to read seed marker; inspect PostgreSQL startup logs.")
        state = line.strip()
        if state in {"READY", "EMPTY"}:
            break
    if state == "READY":
        out.write("COMMIT;\n")
        out.close()
        if process.wait() != 0:
            raise RuntimeError("Seed recheck failed")
        logging.info("Seed already complete; no changes (%.2fs).", time.perf_counter() - started)
        return
    rng = random.Random(SEED)
    out.write("COPY publisher FROM STDIN;\n")
    for pub in range(1, 61):
        tier = ("premium", "standard", "long_tail")[(pub - 1) // 20]
        out.write(f"{pub}\tPublisher {pub:03d}\t{tier}\t{COUNTRIES[pub % 6]}\n")
    out.write("\\.\nCOPY advertiser FROM STDIN;\n")
    for adv in range(1, 121):
        vertical = ("retail", "travel", "finance", "automotive", "entertainment")[adv % 5]
        out.write(f"{adv}\tAdvertiser {adv:03d}\t{vertical}\n")
    out.write("\\.\nCOPY fact_delivery FROM STDIN;\n")
    monthly_cents: dict[tuple[int, date], int] = defaultdict(int)
    rows = 0
    for day_offset in range((END - START).days + 1):
        day = START + timedelta(days=day_offset)
        month = day.replace(day=1)
        season = (0.78 if day.weekday() >= 5 else 1.0) * (1.38 if day.month >= 10 else 1.0)
        buffer = io.StringIO()
        for pub in range(1, 61):
            # 46 rotating advertisers per publisher/day: 1,515,240 fact rows.
            for slot in range(46):
                adv = (day_offset * 7 + pub * 11 + slot) % 120 + 1
                country = COUNTRIES[(pub + slot) % 6]
                device = DEVICES[(day_offset + slot) % 3]
                requests = int(rng.randint(1200, 11000) * season * (1.3 if pub <= 20 else 1))
                fill = 0.81 + rng.uniform(-0.05, 0.05)
                if pub in (7, 19, 43) and day >= date(2026, 5, 1):
                    fill -= 0.14 + (day.month - 5) * 0.055
                impressions = int(requests * fill)
                clicks = int(impressions * rng.uniform(0.002, 0.018))
                spend_cents = round(impressions * rng.uniform(1.7, 4.3) / 10)
                if adv == 17:
                    spend_cents = round(spend_cents * 0.45)
                revenue_cents = round(spend_cents * (1.12 + rng.random() * 0.13))
                monthly_cents[(adv, month)] += spend_cents
                buffer.write(
                    f"{day}\t{pub}\t{adv}\t{country}\t{device}\t{requests}\t"
                    f"{impressions}\t{clicks}\t{spend_cents / 100:.2f}\t"
                    f"{revenue_cents / 100:.2f}\n"
                )
                rows += 1
        out.write(buffer.getvalue())
    out.write("\\.\nCOPY plan FROM STDIN;\n")
    for plan_id, ((adv, month), cents) in enumerate(sorted(monthly_cents.items()), 1):
        pace = Decimal("0.48") if adv == 17 else Decimal(str(0.90 + (adv % 17) / 100))
        planned = (Decimal(cents) / 100 / pace).quantize(Decimal("0.01"))
        out.write(f"{plan_id}\t{adv}\t{month}\t{planned}\n")
    out.write("\\.\n" + INDEX_SQL)
    out.write(
        f"INSERT INTO seed_status(id,ready,version,fact_rows) VALUES(1,true,{VERSION},{rows});\n"
    )
    out.write("COMMIT;\n")
    out.close()
    if process.wait() != 0:
        raise RuntimeError("Seed failed; transaction rolled back. Inspect docker compose logs db.")
    logging.info("Seed checked/completed: %s rows, %.2fs", rows, time.perf_counter() - started)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    seed()
