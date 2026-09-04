"""Traceable explanations and Evidence Cards."""

from dataclasses import dataclass
from typing import Optional

from decision.diagnosis import DiagnosisResult, EvidenceSupport
from features.engineering import BaselineProfile, FEATURE_DEFINITIONS


EVIDENCE_TYPES = (
    "MODEL_DERIVED_EVIDENCE",
    "RULE_DERIVED_EVIDENCE",
    "DOMAIN_KNOWLEDGE",
    "SIMULATION_ASSUMPTION",
    "MODEL-DERIVED",
    "RULE-DERIVED",
    "DOMAIN KNOWLEDGE",
    "SIMULATION ASSUMPTION",
)


@dataclass(frozen=True)
class EvidenceItem:
    feature: str
    value: float
    baseline: Optional[float]
    deviation: Optional[float]
    units: str
    contribution: Optional[float]
    evidence_type: str
    trace: str


@dataclass(frozen=True)
class EvidenceCard:
    title: str
    what_happened: str
    diagnosis: str
    confidence: Optional[float]
    evidence: tuple[EvidenceItem, ...]
    alternatives: tuple[tuple[str, float], ...]
    likely_cause: Optional[str]
    recommended_actions: tuple[str, ...]
    assumptions: tuple[str, ...]
    review_required: bool
    timestamp: object
    run_id: str
    pump_id: str


class EvidenceValidationError(ValueError):
    """Raised when an evidence card cannot be traced to supplied features."""


def build_evidence_card(
    features: dict[str, object],
    diagnosis: DiagnosisResult,
    baseline: BaselineProfile,
    *,
    timestamp: object,
    run_id: str,
    pump_id: str,
    model_contributions: Optional[dict[str, float]] = None,
    assumptions: tuple[str, ...] = (),
) -> EvidenceCard:
    """Build a card using actual feature values and labeled evidence sources."""
    leader = diagnosis.candidates[0] if diagnosis.candidates else None
    evidence = list(_rule_evidence(features, leader.evidence if leader else (), baseline))
    if model_contributions:
        for feature, contribution in model_contributions.items():
            value = features.get(feature)
            if not isinstance(value, (int, float)):
                continue
            evidence.append(
                EvidenceItem(
                    feature=feature,
                    value=float(value),
                    baseline=baseline.medians.get(feature),
                    deviation=_deviation(float(value), baseline, feature),
                    units=_units(feature),
                    contribution=float(contribution),
                    evidence_type="MODEL_DERIVED_EVIDENCE",
                    trace=f"features[{feature}]",
                )
            )
    card = EvidenceCard(
        title=f"{diagnosis.diagnosis.upper()} evidence",
        what_happened=_what_happened(diagnosis),
        diagnosis=diagnosis.diagnosis,
        confidence=diagnosis.confidence,
        evidence=tuple(evidence),
        alternatives=tuple((candidate.fault_type, candidate.support_score) for candidate in diagnosis.candidates[:3]),
        likely_cause=leader.likely_cause if leader and diagnosis.diagnosis not in {"unknown", "ambiguous"} else None,
        recommended_actions=leader.candidate_actions if leader and not diagnosis.review_required else (),
        assumptions=assumptions,
        review_required=diagnosis.review_required,
        timestamp=timestamp,
        run_id=run_id,
        pump_id=pump_id,
    )
    validate_evidence_card(card, features)
    return card


def validate_evidence_card(card: EvidenceCard, features: dict[str, object]) -> None:
    """Verify every evidence value is present and numerically identical."""
    for item in card.evidence:
        if item.evidence_type in ("DOMAIN_KNOWLEDGE", "DOMAIN KNOWLEDGE", "SIMULATION_ASSUMPTION", "SIMULATION ASSUMPTION"):
            if item.evidence_type not in EVIDENCE_TYPES:
                raise EvidenceValidationError(f"unknown evidence type: {item.evidence_type}")
            if item.feature in features:
                value = features.get(item.feature)
                if isinstance(value, (int, float)) and float(value) != item.value:
                    raise EvidenceValidationError(f"untraceable evidence feature value: {item.feature}")
            continue
        value = features.get(item.feature)
        if not isinstance(value, (int, float)) or float(value) != item.value:
            raise EvidenceValidationError(f"untraceable evidence feature: {item.feature}")
        if item.evidence_type not in EVIDENCE_TYPES:
            raise EvidenceValidationError(f"unknown evidence type: {item.evidence_type}")
        if item.feature not in features:
            raise EvidenceValidationError(f"missing feature: {item.feature}")


def extract_model_contributions(model: object, features: dict[str, object], top_k: int = 3) -> dict[str, float]:
    """Extract model feature importances directly grounded in the trained estimator."""
    classifier = getattr(model, "classifier", model)
    feature_names = getattr(model, "feature_names", None)
    if not hasattr(classifier, "feature_importances_"):
        return {}
    importances = classifier.feature_importances_
    if feature_names is None:
        try:
            from models.baseline import NUMERIC_FEATURES
            feature_names = list(NUMERIC_FEATURES)
        except ImportError:
            return {}
    if len(feature_names) != len(importances):
        return {}
    paired = []
    for name, imp in zip(feature_names, importances):
        if name in features and isinstance(features[name], (int, float)):
            paired.append((name, float(imp)))
    paired.sort(key=lambda x: x[1], reverse=True)
    return dict(paired[:top_k])


def format_evidence_card(card: EvidenceCard) -> str:
    """Format a concise human-readable card without adding unsupported claims."""
    lines = [
        f"{card.title}",
        f"What happened: {card.what_happened}",
        f"Diagnosis: {card.diagnosis}",
        f"Confidence: {card.confidence if card.confidence is not None else 'UNKNOWN'}",
    ]
    for item in card.evidence:
        baseline = "UNKNOWN" if item.baseline is None else str(item.baseline)
        deviation = "UNKNOWN" if item.deviation is None else str(item.deviation)
        lines.append(f"Evidence [{item.evidence_type}]: {item.feature}={item.value} {item.units}; baseline={baseline}; deviation={deviation}")
    if card.likely_cause:
        lines.append(f"Likely cause [DOMAIN_KNOWLEDGE]: {card.likely_cause}")
    if card.assumptions:
        for asm in card.assumptions:
            lines.append(f"Assumption [SIMULATION_ASSUMPTION]: {asm}")
    if card.review_required:
        lines.append("Decision: HUMAN REVIEW REQUIRED")
    return "\n".join(lines)


def _rule_evidence(features: dict[str, object], supports: tuple[EvidenceSupport, ...], baseline: BaselineProfile) -> tuple[EvidenceItem, ...]:
    return tuple(
        EvidenceItem(
            feature=support.feature,
            value=support.value,
            baseline=baseline.medians.get(support.feature.replace("_robust_z", "")),
            deviation=_deviation(support.value, baseline, support.feature),
            units=_units(support.feature),
            contribution=support.contribution,
            evidence_type=support.evidence_type,
            trace=f"features[{support.feature}]",
        )
        for support in supports
        if support.feature in features
    )


def _deviation(value: float, baseline: BaselineProfile, feature: str) -> Optional[float]:
    if feature in baseline.medians:
        return value - baseline.medians[feature]
    raw_feature = feature.replace("_robust_z", "")
    if raw_feature in baseline.medians:
        return value
    return None


def _units(feature: str) -> str:
    for definition in FEATURE_DEFINITIONS:
        if definition.name == feature:
            return definition.units
    return "unknown"


def _what_happened(diagnosis: DiagnosisResult) -> str:
    if diagnosis.review_required:
        return "Evidence is insufficient or competing fault signatures are present."
    return f"Feature evidence supports a {diagnosis.diagnosis} condition."
