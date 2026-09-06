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
    specificity: int = 0


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
                specificity=c.specificity,
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
                specificity=c.specificity,
            )
            for c in raw_candidates
        ]

    if not candidates or candidates[0].support_score < min_support:
        return DiagnosisResult(
            diagnosis="unknown",
            confidence=0.0 if not candidates else candidates[0].support_score,
            candidates=tuple(candidates),
            review_required=True,
            reason="all candidate signatures fell below minimum confidence threshold",
            ranked_probabilities=tuple((c.fault_type, c.probability) for c in candidates),
        )

    ranked_probabilities = tuple((c.fault_type, c.probability) for c in candidates)

    leader = candidates[0]
    runner_up = candidates[1] if len(candidates) > 1 else None
    ambiguous = False
    
    if runner_up is not None:
        margin = leader.support_score - runner_up.support_score
        
        # Priority 1: High Absolute Confidence Overrides Ambiguity
        if leader.support_score >= 0.55 and margin >= 0.10:
            ambiguous = False
        # Priority 2: Standard Margin Check
        elif margin < ambiguity_margin:
            # TIE-BREAKER: Structural Specificity overrides numerical ties
            if runner_up.specificity > leader.specificity:
                candidates = list(candidates)
                candidates[0], candidates[1] = candidates[1], candidates[0]
                leader = candidates[0]
                runner_up = candidates[1]
                ambiguous = False
            elif leader.specificity > runner_up.specificity:
                ambiguous = False
            else:
                ambiguous = True

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
    
    if signature.inverted:
        # For 'normal', a single highly deviated sensor means the machine is NOT normal.
        # We must penalize based on the maximum deviation, not the average of quiet sensors.
        max_dev = 0.0
        for feature in signature.evidence_features:
            value = features.get(feature)
            if isinstance(value, (int, float)) and value == value:
                dev = abs(float(value))
                max_dev = max(max_dev, dev)
                evidence.append(EvidenceSupport(feature, float(value), dev, "RULE_DERIVED_EVIDENCE"))
        
        # Collapse support to 0 if max deviation exceeds 4.0 Z-scores (slower decay to prevent noise FP)
        score = max(0.0, 1.0 - max_dev / 4.0)
    else:
        weighted_support = 0.0
        for feature in signature.evidence_features:
            value = features.get(feature)
            weight = signature.weights[feature]
            if isinstance(value, (int, float)) and value == value:
                if feature.endswith("_sig") or feature.startswith("is_"):
                    # Binary / indicator flag features (0.0 to 1.0)
                    support = min(1.0, max(0.0, float(value)))
                else:
                    val_f = float(value)
                    expected_sign = (signature.signs or {}).get(feature, 0)
                    if expected_sign != 0:
                        # Directional mismatch completely zeroes out the support for this feature
                        if (expected_sign == 1 and val_f < 0) or (expected_sign == -1 and val_f > 0):
                            support = 0.0
                        else:
                            support = abs(val_f) / 3.0
                    else:
                        support = abs(val_f) / 3.0
                
                contribution = support * weight
                weighted_support += contribution
                evidence.append(EvidenceSupport(feature, float(value), contribution, "RULE_DERIVED_EVIDENCE"))
        score = weighted_support
        
        # Enforce sensor_drift constraint: only one sensor can deviate, others must be nominal
        if signature.fault_type == "sensor_drift":
            deviating_sensors = 0
            for f_name, f_val in features.items():
                if f_name.endswith("_robust_z") and isinstance(f_val, (int, float)) and f_val == f_val:
                    if abs(f_val) >= 0.8:
                        deviating_sensors += 1
            if deviating_sensors > 1:
                score = 0.0
                
        # Enforce Hydraulic Mass Balance Coupling for seal_leakage
        # If BOTH pressure and flow deviate negatively, sensor_drift and pressure_loss are disqualified.
        p_z = float(features.get("pressure_robust_z", 0.0) or 0.0)
        q_z = float(features.get("flow_robust_z", 0.0) or 0.0)
        if p_z <= -1.3 and q_z <= -1.3:
            if signature.fault_type in ("sensor_drift", "pressure_loss"):
                score = 0.0
                
    # Calculate Specificity (number of active physical domains for multi-sensor faults)
    specificity = 0
    if not signature.inverted:
        all_active = True
        for feature in signature.evidence_features:
            val = features.get(feature)
            # Increase baseline threshold to 1.5 to prevent process turbulence from falsely activating tie-breakers
            if val is None or abs(float(val)) < 1.5:
                all_active = False
                break
        if all_active:
            specificity = len(signature.evidence_features)
        
    return DiagnosisCandidate(
        signature.fault_type,
        score,
        signature.likely_cause,
        tuple(evidence),
        signature.candidate_actions,
        signature.guardrails,
        probability=0.0,
        specificity=specificity,
    )
