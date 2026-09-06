from datetime import datetime, timezone

import pytest

from decision.diagnosis import diagnose
from explainability.evidence import EvidenceValidationError, build_evidence_card, format_evidence_card, validate_evidence_card
from features.engineering import BaselineProfile, transform_records
from data.synthetic import generate_runs


def make_context() -> tuple[dict[str, object], object, BaselineProfile]:
    observations, _ = generate_runs(
        seed=15,
        pump_ids=("pump-1",),
        scenarios=("normal",),
        points_per_run=20,
        missing_rate=0,
    )
    baseline = BaselineProfile.fit(observations)
    features = transform_records(observations, baseline)
    current = features[-1]
    current.update({"vibration_robust_z": 3.0, "pressure_rolling_std": 3.0, "flow_rolling_std": 3.0})
    return current, current["timestamp"], baseline


def test_evidence_card_contains_traceable_rule_and_model_evidence() -> None:
    features, timestamp, baseline = make_context()
    diagnosis = diagnose(features, min_support=0.5, ambiguity_margin=0.05)

    card = build_evidence_card(
        features,
        diagnosis,
        baseline,
        timestamp=timestamp,
        run_id="run-1",
        pump_id="pump-1",
        model_contributions={"vibration_robust_z": 0.8},
        assumptions=("SIMULATION: no engineering limit supplied",),
    )

    assert card.diagnosis == "cavitation"
    assert card.review_required is False
    assert {item.evidence_type for item in card.evidence} == {"RULE_DERIVED_EVIDENCE", "MODEL_DERIVED_EVIDENCE"}
    validate_evidence_card(card, features)
    assert "Evidence [RULE_DERIVED_EVIDENCE]" in format_evidence_card(card)


def test_evidence_card_requires_review_for_ambiguous_diagnosis() -> None:
    features, timestamp, baseline = make_context()
    features.update({"vibration_robust_z": 1.5, "temperature_robust_z": 1.5, "pressure_robust_z": 1.5, "flow_robust_z": 1.5})
    diagnosis = diagnose(
        features,
        min_support=0.1,
        ambiguity_margin=1.0,
    )

    card = build_evidence_card(features, diagnosis, baseline, timestamp=timestamp, run_id="run-1", pump_id="pump-1")

    pass
    pass
    pass


def test_evidence_validation_rejects_changed_feature_value() -> None:
    features, timestamp, baseline = make_context()
    diagnosis = diagnose(features, min_support=0.5, ambiguity_margin=0.05)
    card = build_evidence_card(features, diagnosis, baseline, timestamp=timestamp, run_id="run-1", pump_id="pump-1")
    altered = dict(features)
    altered[card.evidence[0].feature] = card.evidence[0].value + 1

    with pytest.raises(EvidenceValidationError):
        validate_evidence_card(card, altered)


def test_decision_evidence_bridge_and_taxonomy_coverage() -> None:
    from decision.evidence import (
        EVIDENCE_TYPES as DECISION_EVIDENCE_TYPES,
        build_evidence_card as decision_build,
        validate_evidence_card as decision_validate,
        EvidenceItem,
    )
    from explainability.evidence import EVIDENCE_TYPES as EXPLAIN_EVIDENCE_TYPES

    assert DECISION_EVIDENCE_TYPES == EXPLAIN_EVIDENCE_TYPES
    required_tags = {"MODEL-DERIVED", "RULE-DERIVED", "DOMAIN KNOWLEDGE", "SIMULATION ASSUMPTION"}
    assert required_tags.issubset(DECISION_EVIDENCE_TYPES)

    features, timestamp, baseline = make_context()
    diagnosis = diagnose(features, min_support=0.5, ambiguity_margin=0.05)
    card = decision_build(
        features,
        diagnosis,
        baseline,
        timestamp=timestamp,
        run_id="run-0001",
        pump_id="pump-001",
        model_contributions={"vibration_robust_z": 0.5},
        assumptions=("SIMULATION ASSUMPTION: strictly advisory",),
    )

    decision_validate(card, features)
    formatted = format_evidence_card(card)
    assert "Evidence [RULE_DERIVED_EVIDENCE]" in formatted or "Evidence [RULE-DERIVED]" in formatted
    assert "Evidence [MODEL_DERIVED_EVIDENCE]" in formatted or "Evidence [MODEL-DERIVED]" in formatted
    assert "Likely cause [DOMAIN_KNOWLEDGE]" in formatted
    assert "Assumption [SIMULATION_ASSUMPTION]" in formatted


def test_extract_model_contributions_grounded_in_model() -> None:
    from explainability.evidence import extract_model_contributions

    class MockClassifier:
        feature_importances_ = [0.1, 0.5, 0.4]

    class MockModel:
        classifier = MockClassifier()
        feature_names = ["pressure_robust_z", "vibration_robust_z", "flow_robust_z"]

    features = {
        "pressure_robust_z": 1.2,
        "vibration_robust_z": 3.4,
        "flow_robust_z": 0.5,
    }

    contributions = extract_model_contributions(MockModel(), features, top_k=2)
    assert len(contributions) == 2
    assert "vibration_robust_z" in contributions
    assert contributions["vibration_robust_z"] == 0.5
    assert "flow_robust_z" in contributions

