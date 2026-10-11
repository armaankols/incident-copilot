"""Selecting a new fault must not silently rerun earlier paid cases."""
import pytest

from evals.cases import scenarios


def test_offset_selects_exact_original_case_without_changing_telemetry():
    selected = scenarios(1, 0, offset=3)
    original = scenarios(6, 0)[3]
    assert len(selected) == 1
    case = selected[0]
    assert case.seed == 3 and case.fault_type == "config_error"
    assert case.case_id == original.case_id
    assert case.metrics == original.metrics and case.logs == original.logs


def test_offset_preserves_challenge_variant_and_rejects_negative_index():
    selected = scenarios(1, 0, "correlated-v1", offset=18)[0]
    assert selected.variant == "redacted" and selected.fault_type == "insufficient_evidence"
    with pytest.raises(ValueError, match="nonnegative"):
        scenarios(1, 0, offset=-1)
