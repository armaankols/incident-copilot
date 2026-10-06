import json
from pathlib import Path
from copilot.retrieval import RUNBOOK_DIR, load_chunks
from evals.recovery_eval import read_policy


def test_recovery_profiles_disallow_unsafe_generic_actions():
    chunks = load_chunks(RUNBOOK_DIR/"recovery")
    orders = read_policy("orders", "v4", chunks)["policy"]
    assert orders["action"] == "rollforward" and not orders["limits"]["rollback_allowed"]
    payments = read_policy("payments", "v3", chunks)["policy"]
    assert payments["steps"].index("release_leader_lease") < payments["steps"].index("restart_one_replica")
    inventory = read_policy("inventory", "v2", chunks)["policy"]
    assert inventory["limits"]["pool_max_per_replica"] == 8
    assert inventory["limits"]["global_connection_limit"] == 40


def test_policy_reader_abstains_without_exact_version_or_with_conflict():
    chunks = load_chunks(RUNBOOK_DIR/"recovery")
    assert read_policy("orders", "v8", chunks)["status"] == "insufficient_evidence"
    assert read_policy("orders", "v4", [])["status"] == "insufficient_evidence"
    assert read_policy("orders", "v4", chunks+chunks)["status"] == "insufficient_evidence"


def test_recovery_golden_cases_cover_each_service_version_once():
    cases = json.loads(Path("evals/recovery_cases.json").read_text())
    chunks = load_chunks(RUNBOOK_DIR/"recovery")
    assert len({c["case_id"] for c in cases}) == 15
    for case in cases:
        assert read_policy(case["service"], case["version"], chunks)["policy"] == case["expect"]
