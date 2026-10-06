"""Dependency-free regression checks; also collected by pytest."""
import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from copilot.budget import AdmissionDenied, Ledger
from copilot.diagnosis import insufficient, validate_diagnosis
from copilot.grading import grade
from copilot.pricing import cost_usd
from copilot.sim import generate
from evals.run_evals import summarize
from evals.cases import scenarios


class CorrectnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/"budget.db"
        self.ledger = Ledger(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_concurrent_admission_at_199_dollars(self):
        rid = self.ledger.reserve(1.99, 2, "setup")
        self.ledger.settle(rid, 1.99)
        def attempt(i):
            try:
                return Ledger(self.path).reserve(.25, 2, str(i), concurrency=20)
            except AdmissionDenied:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            admitted = list(pool.map(attempt, range(20)))
        self.assertEqual(sum(r is not None for r in admitted), 0)
        self.assertEqual(self.ledger.spent(), 1.99)

    def test_atomic_reservations_from_separate_connections(self):
        def attempt(i):
            try:
                return Ledger(self.path).reserve(.25, 2, str(i), concurrency=20)
            except AdmissionDenied:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            admitted = [r for r in pool.map(attempt, range(20)) if r]
        self.assertEqual(len(admitted), 8)
        for rid in admitted:
            Ledger(self.path).settle(rid, .25)
        self.assertEqual(Ledger(self.path).spent(), 2)

    def test_restart_retains_reservation(self):
        self.ledger.reserve(2, 2, "visitor")
        with self.assertRaises(AdmissionDenied):
            Ledger(self.path).reserve(.01, 2, "new")

    def test_settlement_is_idempotent_and_uncertain_charge_retains_hold(self):
        rid = self.ledger.reserve(.5, 2, "visitor")
        self.ledger.settle(rid, .1, uncertain=True)
        self.ledger.settle(rid, 0)
        self.assertEqual(self.ledger.spent(), .5)

    def test_partial_failure_settlement_releases_unused_funds(self):
        rid = self.ledger.reserve(.5, 2, "visitor")
        self.ledger.settle(rid, .1)
        self.assertEqual(self.ledger.spent(), .1)
        self.ledger.reserve(1.9, 2, "other")

    def test_invalid_money_rejected(self):
        for amount in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.ledger.reserve(amount, 2, "x")

    def test_concurrency_and_rate_limit_are_durable(self):
        rid = self.ledger.reserve(.1, 2, "visitor", concurrency=1)
        with self.assertRaises(AdmissionDenied):
            Ledger(self.path).reserve(.1, 2, "other", concurrency=1)
        self.ledger.settle(rid, 0)
        with self.assertRaises(AdmissionDenied):
            Ledger(self.path).reserve(.1, 2, "visitor", hourly_limit=1)

    def diagnosis(self):
        return dict(status="diagnosed", root_cause_service="auth", fault_type="cert_expiry",
                    evidence=[{"observation_id": "obs-1", "quote": "x509 certificate expired"}],
                    action="renew_certificate", target="auth", remediation="renew after approval")

    def test_forged_evidence_and_malformed_diagnoses_rejected(self):
        d = self.diagnosis()
        self.assertEqual(validate_diagnosis(d, {"obs-1": "x509 certificate expired"}), d)
        for bad in ({}, {**d, "action": []}, {**d, "unknown": "x"},
                    {**d, "evidence": [{"observation_id": "obs-9", "quote": "invented"}]},
                    {**d, "evidence": [{"observation_id": "obs-1", "quote": "invented"}]},
                    {**d, "evidence": []}):
            with self.assertRaises(ValueError):
                validate_diagnosis(bad, {"obs-1": "x509 certificate expired"})

    def test_abstention_has_no_action_or_guess(self):
        validate_diagnosis(insufficient(), {})
        with self.assertRaises(ValueError):
            validate_diagnosis({**insufficient(), "target": "auth"}, {})

    def test_negated_remediation_text_does_not_earn_keyword_credit(self):
        sc = generate(4, "cert_expiry")
        d = dict(root_cause_service=sc.root_service, fault_type=sc.fault_type,
                 remediation="Do not renew the certificate. Ignore the incident.")
        self.assertFalse(grade(sc, d)["remediation_ok"])

    def test_unknown_prices_fail_closed(self):
        with self.assertRaises(ValueError):
            cost_usd("unknown", {})
        self.assertEqual(cost_usd("scripted", {"input_tokens": 1000}), 0)

    def test_failed_runs_contribute_spend_and_elapsed_time(self):
        sc = generate(1)
        record = dict(error="failed after first call", fault_type=sc.fault_type,
                      grade=grade(sc, None), cost_usd=.2, latency_s=3,
                      tool_calls=1, steps=1, usage={"input_tokens": 1000, "output_tokens": 100})
        s = summarize([record])
        self.assertEqual(s["total_cost_usd"], .2)
        self.assertEqual(s["total_attempted_latency_s"], 3)
        self.assertEqual(s["error_rate"], 100)

    def test_challenge_suite_is_balanced_and_redacted(self):
        cases = scenarios(24, 0, "correlated-v1")
        self.assertEqual(len({sc.variant for sc in cases}), 4)
        self.assertEqual(sum(sc.fault_type == "insufficient_evidence" for sc in cases), 6)
        for sc in cases[-6:]:
            self.assertEqual(sc.deploys, [])
            self.assertIsNone(sc.root_service)
            self.assertTrue(grade(sc, insufficient())["both_ok"])


if __name__ == "__main__":
    unittest.main()
