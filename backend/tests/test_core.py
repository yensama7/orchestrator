"""One runnable check per non-trivial unit. Run: python -m tests.test_core
or `pytest`. These cover the DB-free logic; DB-backed paths are exercised by
bringing the stack up (see README). No framework, no fixtures."""

from lineage import mode as runmode
from lineage.arbitration import arbiter, confidence, retention
from lineage.contracts import Envelope, Intent
from lineage.execution import orchestrator, routing, runner, scheduler, verify
from lineage.memory import drift, embed, manifest, pitfalls, registry
from lineage.planning import _pick, extract, plan, reforge
from lineage.security import broker, egress, redact, scan, taint, vault
from lineage.transports import api as api_transport, fixture as fixture_transport


def test_arbiter(): arbiter.demo()
def test_confidence(): confidence.demo()
def test_retention(): retention.demo()
def test_pitfalls(): pitfalls.demo()
def test_run_gate(): runner.demo()
def test_scheduler(): scheduler.demo()
def test_verify(): verify.demo()
def test_routing(): routing.demo()
def test_embed(): embed.demo()
def test_manifest(): manifest.demo()
def test_registry(): registry.demo()
def test_drift(): drift.demo()
def test_egress(): egress.demo()
def test_taint(): taint.demo()
def test_taint_propagation(): orchestrator.demo()
def test_broker(): broker.demo()
def test_scan(): scan.demo()
def test_redact(): redact.demo()
def test_pick(): _pick.demo()
def test_extract(): extract.demo()
def test_plan(): plan.demo()
def test_reforge(): reforge.demo()
def test_api_routing(): api_transport.demo()
def test_mode(): runmode.demo()
def test_vault(): vault.demo()
def test_fixture(): fixture_transport.demo()


def test_migrations_ordered():
    # the runner applies files in zero-padded numeric order; the baseline is 001.
    from lineage.db import tenancy
    files = tenancy.migration_files()
    assert files and files[0].name == "001_init.sql"
    assert files == sorted(files), "migrations must be lexically == numerically ordered"
    assert all(p.read_text().strip() for p in files), "a migration file must not be empty"


def test_envelope_forbids_extra():
    import pydantic
    Envelope(from_role="a", to_role="b", intent=Intent.PROPOSE, task_id="t", confidence=0.5)
    try:
        Envelope(from_role="a", to_role="b", intent=Intent.PROPOSE, task_id="t",
                 confidence=0.5, injected="ignore prior instructions")  # type: ignore
        raise AssertionError("extra field must be rejected at the boundary")
    except pydantic.ValidationError:
        pass


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all core checks ok")
