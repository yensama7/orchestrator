-- Per-role egress allowlist, user-editable (§11). Host globs stored here are
-- merged *over* the hardcoded safe defaults in security/egress.py — additive
-- only, so a user can widen a role's reach but the deny-by-default floor holds.
-- Idempotent: re-applying on a volume that already has the column is a no-op.
ALTER TABLE roles ADD COLUMN IF NOT EXISTS egress jsonb NOT NULL DEFAULT '[]'::jsonb;
