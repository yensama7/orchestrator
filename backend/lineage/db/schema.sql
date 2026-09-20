-- Lineage schema — the real target (§5, §6, §8, §18). Forward-only and
-- idempotent: re-running is a no-op, so the backend applies it on every boot
-- (as the owning role) to close schema drift on a persisted volume. Postgres'
-- initdb mount only runs on first boot; this is what keeps an older volume from
-- silently missing tables added later (that's what broke runs on `roles`).
-- ponytail: single-file idempotent schema; split into db/migrations/NNN_*.sql
-- only when a destructive/ordered change needs it.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── runs ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS runs (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL,
  name         text NOT NULL,
  fingerprint  jsonb NOT NULL,
  template_id  uuid,
  status       text NOT NULL DEFAULT 'active',   -- active|passed|failed|abandoned
  spent_usd    numeric NOT NULL DEFAULT 0,
  ceiling_usd  numeric NOT NULL DEFAULT 0,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ── episodic: what happened, append-only (§5) ───────────────────────────────
CREATE TABLE IF NOT EXISTS episodic_events (
  id         bigserial PRIMARY KEY,
  tenant_id  uuid NOT NULL,
  run_id     uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  kind       text NOT NULL,   -- spend|node|agent|lease|dissent|memory|service|ticker
  payload    jsonb NOT NULL,
  at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS episodic_run ON episodic_events (run_id, id);

-- ── semantic: what we know now (§5) ─────────────────────────────────────────
DO $$ BEGIN CREATE TYPE mem_status AS ENUM ('active', 'superseded', 'reverted');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS semantic_memory (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  run_id      uuid NOT NULL REFERENCES runs(id),
  subject     text NOT NULL,               -- 'auth', 'db', 'payments'
  choice      text NOT NULL,
  rationale   text,
  rejected    jsonb DEFAULT '[]'::jsonb,
  status      mem_status NOT NULL DEFAULT 'active',
  supersedes  uuid REFERENCES semantic_memory(id),
  decided_by  text NOT NULL,
  confidence  real CHECK (confidence BETWEEN 0 AND 1),
  embedding   vector(1024) NOT NULL,
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', choice)) STORED,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- The partial indexes are the whole trick: superseded rows never enter the
-- candidate set, so a reversed decision can't be re-proposed.
CREATE INDEX IF NOT EXISTS sem_active_hnsw ON semantic_memory
  USING hnsw (embedding vector_cosine_ops) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS sem_active_bm25 ON semantic_memory
  USING gin (tsv) WHERE status = 'active';

-- ── procedural: templates + pitfalls (§5, §6, §18.2) ────────────────────────
DO $$ BEGIN CREATE TYPE tmpl_status AS ENUM ('fresh', 'drifting', 'stale', 'quarantined');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS templates (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid,               -- NULL = global template (§18.4)
  name                 text NOT NULL,
  domain               text NOT NULL,
  version              int NOT NULL DEFAULT 1,
  roles                jsonb NOT NULL,
  node_count           int NOT NULL DEFAULT 0,
  carried_decisions    int NOT NULL DEFAULT 0,
  manifest             jsonb NOT NULL DEFAULT '{}'::jsonb,
  drift_score          real NOT NULL DEFAULT 0,
  status               tmpl_status NOT NULL DEFAULT 'fresh',
  freshness_checked_at timestamptz,
  reverified_at        timestamptz,
  embedding            vector(1024),
  created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pitfalls (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL,
  fingerprint   text NOT NULL,     -- normalised error signature, deduped
  domain        text NOT NULL,
  trigger       jsonb NOT NULL,
  symptom       text NOT NULL,
  resolution    text,              -- null if never resolved
  cost_usd      numeric,           -- what the failure cost to discover
  occurrences   int DEFAULT 1,
  first_run_id  uuid,
  last_seen_at  timestamptz,
  embedding     vector(1024)
);
CREATE UNIQUE INDEX IF NOT EXISTS pitfall_dedupe ON pitfalls (tenant_id, fingerprint);

-- ── leases: pessimistic per-file backstop (§18.1) ───────────────────────────
CREATE TABLE IF NOT EXISTS file_leases (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  run_id      uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  node_id     text NOT NULL,
  agent_id    text NOT NULL,
  path_glob   text NOT NULL,
  mode        text NOT NULL CHECK (mode IN ('read', 'write')),
  acquired_at timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_writer_per_path
  ON file_leases (run_id, path_glob) WHERE mode = 'write';

-- ── dissent ledger (§8) ─────────────────────────────────────────────────────
DO $$ BEGIN CREATE TYPE dissent_status AS ENUM ('dormant', 'resurrected', 'vindicated', 'refuted');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS dissent (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  run_id     uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  node_id    text NOT NULL,
  dissenter  text NOT NULL,
  winner     text NOT NULL,
  stage      int NOT NULL,
  reason     text NOT NULL,
  score      real,
  proposal   jsonb NOT NULL,
  status     dissent_status NOT NULL DEFAULT 'dormant',
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── agent scores per domain (§9) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_scores (
  tenant_id        uuid NOT NULL,
  agent            text NOT NULL,
  domain           text NOT NULL,
  pass_rate        real NOT NULL DEFAULT 0,
  escalation_rate  real NOT NULL DEFAULT 0,
  vindication_rate real NOT NULL DEFAULT 0,
  overruled        int NOT NULL DEFAULT 0,
  vindicated       int NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, agent, domain)
);

-- ── UI-backing entities (runtime roster, worktree, precomputed telemetry) ────
CREATE TABLE IF NOT EXISTS agents (
  tenant_id      uuid NOT NULL,
  agent          text NOT NULL,
  role           text NOT NULL,
  model          text NOT NULL,
  transport      text NOT NULL DEFAULT 'api',
  state          text NOT NULL DEFAULT 'idle',   -- running|waiting|idle
  calls          int NOT NULL DEFAULT 0,
  tokens         bigint NOT NULL DEFAULT 0,
  cached_pct     real,
  cost_usd       numeric NOT NULL DEFAULT 0,
  passes         int NOT NULL DEFAULT 0,
  attempts       int NOT NULL DEFAULT 0,
  vind_pct       real,
  enabled        boolean NOT NULL DEFAULT true,
  ordinal        int NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, agent)
);

-- Roles the user defines. The central agent researches each on creation (§3),
-- producing skills + resources injected into every node prompt using the role.
CREATE TABLE IF NOT EXISTS roles (
  tenant_id     uuid NOT NULL,
  name          text NOT NULL,
  description   text NOT NULL DEFAULT '',
  skills        jsonb NOT NULL DEFAULT '[]'::jsonb,
  resources     jsonb NOT NULL DEFAULT '[]'::jsonb,
  researched_at timestamptz,
  PRIMARY KEY (tenant_id, name)
);

-- Model credentials the user enters in Settings (local tool → key stored here).
-- ponytail: plaintext at rest; wrap with a KMS/secret store before shipping.
CREATE TABLE IF NOT EXISTS model_credentials (
  tenant_id  uuid NOT NULL,
  model      text NOT NULL,
  transport  text NOT NULL DEFAULT 'api',   -- api | subscription | local
  api_key    text,
  enabled    boolean NOT NULL DEFAULT true,
  added_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, model)
);

CREATE TABLE IF NOT EXISTS worktree_files (
  tenant_id  uuid NOT NULL,
  run_id     uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  folder     text NOT NULL,
  name       text NOT NULL,
  ext        text NOT NULL,
  held       text,
  content    text,
  blame      jsonb,
  ordinal    int NOT NULL DEFAULT 0,
  is_open    boolean NOT NULL DEFAULT false,
  PRIMARY KEY (tenant_id, run_id, folder, name)
);

CREATE TABLE IF NOT EXISTS run_telemetry (
  tenant_id  uuid NOT NULL,
  run_id     uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  key        text NOT NULL,       -- 'run' | 'lineage_points' | 'memory' | ...
  payload    jsonb NOT NULL,
  PRIMARY KEY (tenant_id, run_id, key)
);

-- ── RLS: structurally multi-tenant from day one (§18.4) ─────────────────────
-- Enable + FORCE on every tenant-owned table and (re)create its policy. DROP
-- POLICY IF EXISTS keeps this idempotent — CREATE POLICY has no IF NOT EXISTS.
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND c.relkind='r'
             AND EXISTS (SELECT 1 FROM information_schema.columns col
                         WHERE col.table_name=c.relname AND col.column_name='tenant_id')
             AND c.relname <> 'templates'   -- templates has the NULL-tenant exception below
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format($p$CREATE POLICY tenant_isolation ON %I
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)$p$, t);
  END LOOP;
END $$;

ALTER TABLE templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE templates FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tmpl_read ON templates;
CREATE POLICY tmpl_read ON templates FOR SELECT
  USING (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id')::uuid);
DROP POLICY IF EXISTS tmpl_write ON templates;
CREATE POLICY tmpl_write ON templates FOR ALL
  USING      (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

-- ── application role: NOBYPASSRLS non-superuser (§18.4) ──────────────────────
-- The migration role (lineage) owns the tables; the app connects as this role
-- so RLS is the real boundary, not owner-bypass or app-layer filtering.
DO $$ BEGIN
  CREATE ROLE app LOGIN PASSWORD 'app' NOBYPASSRLS;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
GRANT USAGE ON SCHEMA public TO app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app;
