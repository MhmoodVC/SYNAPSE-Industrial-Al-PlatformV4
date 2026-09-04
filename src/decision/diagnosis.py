"""Transparent fault diagnosis from feature evidence."""

from dataclasses import dataclass
from typing import Optional

from .fault_knowledge import FAULT_KNOWLEDGE, FaultSignature


@dataclass(frozen=True)
class EvidenceSupport:
    feature: str
    value: float
    contribution: float
    evidence_type: str


@dataclass(frozen=True)
class DiagnosisCandidate:
    fault_type: str
    support_score: float
    likely_cause: str
    evidence: tuple[EvidenceSupport, ...]
    candidate_actions: tuple[str, ...]
    guardrails: tuple[str, ...]
    probability: float = 0.0


@dataclass(frozen=True)
class DiagnosisResult:
    diagnosis: str
    confidence: Optional[float]
    candidates: tuple[DiagnosisCandidate, ...]
    review_required: bool
    reason: str
    ranked_probabilities: tuple[tuple[str, float], ...] = ()


def diagnose(features: dict[str, object], *, min_support: float = 0.35, ambiguity_margin: float = 0.10) -> DiagnosisResult:
    """Rank rule-supported faults with normalized probability distribution."""
    if not 0 <= min_support <= 1:
        raise ValueError("min_support must be between 0 and 1")
    if ambiguity_margin < 0:
        raise ValueError("ambiguity_margin must not be negative")

    raw_candidates = [_score_signature(features, signature) for signature in FAULT_KNOWLEDGE.values()]
    raw_candidates.sort(key=lambda candidate: candidate.support_score, reverse=True)

    total_support = sum(c.support_score for c in raw_candidates)
    if total_support > 0:
        candidates = [
            DiagnosisCandidate(
                fault_type=c.fault_type,
                support_score=c.support_score,
                likely_cause=c.likely_cause,
                evidence=c.evidence,
                candidate_actions=c.candidate_actions,
                guardrails=c.guardrails,
                probability=round(c.support_score / total_support, 4),
            )
            for c in raw_candidates
        ]
    else:
        uniform_prob = round(1.0 / len(raw_candidates), 4) if raw_candidates else 0.0
        candidates = [
            DiagnosisCandidate(
                fault_type=c.fault_type,
                support_score=c.support_score,
                likely_cause=c.likely_cause,
                evidence=c.evidence,
                candidate_actions=c.candidate_actions,
                guardrails=c.guardrails,
                probability=uniform_prob,
            )
            for c in raw_candidates
        ]

    ranked_probabilities = tuple((c.fault_type, c.probability) for c in candidates)

    if not candidates or candidates[0].support_score < min_support:
        return DiagnosisResult(
            diagnosis="unknown",
            confidence=None,
            candidates=tuple(candidates),
            review_required=True,
            reason="insufficient rule evidence / low confidence",
            ranked_probabilities=ranked_probabilities,
        )

    leader = candidates[0]
    runner_up = candidates[1] if len(candidates) > 1 else None
    ambiguous = runner_up is not None and leader.support_score - runner_up.support_score < ambiguity_margin

    if ambiguous:
        return DiagnosisResult(
            diagnosis="ambiguous",
            confidence=None,
            candidates=tuple(candidates),
            review_required=True,
            reason="competing fault signatures have similar support",
            ranked_probabilities=ranked_probabilities,
        )

    return DiagnosisResult(
        diagnosis=leader.fault_type,
        confidence=leader.support_score,
        candidates=tuple(candidates),
        review_required=False,
        reason="leading rule signature has sufficient support",
        ranked_probabilities=ranked_probabilities,
    )


def _score_signature(features: dict[str, object], signature: FaultSignature) -> DiagnosisCandidate:
    evidence: list[EvidenceSupport] = []
    weighted_support = 0.0
    for feature in signature.evidence_features:
        value = features.get(feature)
        weight = signature.weights[feature]
        if isinstance(value, (int, float)) and value == value:
            if signature.inverted:
                # Inverted support: high support when sensor deviation is close to 0
                support = max(0.0, 1.0 - abs(float(value)) / 1.5)
            elif feature.endswith("_sig") or feature.startswith("is_"):
                # Binary / indicator flag features (0.0 to 1.0)
                support = min(1.0, max(0.0, float(value)))
            else:
                support = min(1.0, abs(float(value)) / 3.0)
            contribution = support * weight
            weighted_support += contribution
            evidence.append(EvidenceSupport(feature, float(value), contribution, "RULE_DERIVED_EVIDENCE"))
    score = weighted_support
    return DiagnosisCandidate(
        signature.fault_type,
        score,
        signature.likely_cause,
        tuple(evidence),
        signature.candidate_actions,
        signature.guardrails,
    )
