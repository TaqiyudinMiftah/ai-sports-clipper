from __future__ import annotations

from .models import ClipCandidate


def score_candidate(candidate: ClipCandidate) -> ClipCandidate:
    score = 0.0
    reasons: list[str] = []

    score += candidate.mean_combined * 35.0
    score += candidate.peak_combined * 20.0
    score += candidate.peak_audio * 15.0
    score += candidate.peak_motion * 15.0

    if candidate.duration >= 10:
        score += 5.0
        reasons.append("meets the 10-second minimum")
    if candidate.duration >= 15:
        score += 5.0
        reasons.append("sustained sequence")
    if candidate.peak_audio >= 0.8:
        reasons.append("strong crowd, commentary, or impact audio")
    if candidate.peak_motion >= 0.8:
        reasons.append("high visual movement")
    if candidate.mean_combined >= 0.6:
        reasons.append("continuous audio and motion intensity")

    candidate.score = round(min(score, 100.0), 2)
    candidate.reasons = reasons or ["highest available activity window"]
    return candidate


def rank_candidates(candidates: list[ClipCandidate]) -> list[ClipCandidate]:
    scored = [score_candidate(candidate) for candidate in candidates]
    return sorted(scored, key=lambda item: item.score, reverse=True)
