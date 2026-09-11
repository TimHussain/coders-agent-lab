-- All entities are invented. Amounts use one synthetic reporting currency.
CREATE TABLE IF NOT EXISTS publisher (
    publisher_id integer PRIMARY KEY,
    name text NOT NULL,
    tier text NOT NULL CHECK (tier IN ('premium', 'standard', 'long_tail')),
    country text NOT NULL
);
CREATE TABLE IF NOT EXISTS advertiser (
    advertiser_id integer PRIMARY KEY,
    name text NOT NULL,
    vertical text NOT NULL
);
CREATE TABLE IF NOT EXISTS plan (
    plan_id integer PRIMARY KEY,
    advertiser_id integer NOT NULL REFERENCES advertiser,
    month date NOT NULL CHECK (EXTRACT(DAY FROM month) = 1),
    planned_spend numeric(16,2) NOT NULL CHECK (planned_spend >= 0),
    UNIQUE (advertiser_id, month)
);
CREATE TABLE IF NOT EXISTS fact_delivery (
    day date NOT NULL,
    publisher_id integer NOT NULL REFERENCES publisher,
    advertiser_id integer NOT NULL REFERENCES advertiser,
    country text NOT NULL,
    device text NOT NULL CHECK (device IN ('desktop', 'mobile', 'tablet')),
    requests integer NOT NULL CHECK (requests >= 0),
    impressions integer NOT NULL CHECK (impressions BETWEEN 0 AND requests),
    clicks integer NOT NULL CHECK (clicks BETWEEN 0 AND impressions),
    spend numeric(14,2) NOT NULL CHECK (spend >= 0),
    revenue numeric(14,2) NOT NULL CHECK (revenue >= 0)
);
CREATE TABLE IF NOT EXISTS seed_status (
    id integer PRIMARY KEY CHECK (id=1),
    ready boolean NOT NULL,
    version integer NOT NULL,
    fact_rows integer NOT NULL,
    completed_at timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agentlab_readonly') THEN
        CREATE ROLE agentlab_readonly LOGIN PASSWORD 'agentlab'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
END $$;
REVOKE ALL ON DATABASE agentlab FROM PUBLIC;
GRANT CONNECT ON DATABASE agentlab TO agentlab_readonly;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO agentlab_readonly;
GRANT SELECT ON publisher, advertiser, plan, fact_delivery, seed_status TO agentlab_readonly;
ALTER ROLE agentlab_readonly SET default_transaction_read_only = on;
ALTER ROLE agentlab_readonly SET statement_timeout = '2s';
ALTER ROLE agentlab_readonly SET lock_timeout = '500ms';
-- The fixed password is only for this loopback-only synthetic local database.
-- Indexes are created after COPY in seed.py so first startup stays fast.
