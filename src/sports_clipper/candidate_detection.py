from __future__ import annotations

from .models import ClipCandidate, TimelinePoint


def build_timeline(
    audio_scores: list[float],
    motion_scores: list[float],
    audio_weight: float = 0.55,
) -> list[TimelinePoint]:
    if not 0.0 <= audio_weight <= 1.0:
        raise ValueError("audio_weight must be between 0 and 1")

    length = max(len(audio_scores), len(motion_scores))
    motion_weight = 1.0 - audio_weight
    timeline: list[TimelinePoint] = []
    for second in range(length):
        audio = audio_scores[second] if second < len(audio_scores) else 0.0
        motion = motion_scores[second] if second < len(motion_scores) else 0.0
        timeline.append(
            TimelinePoint(
                second=second,
                audio_score=audio,
                motion_score=motion,
                combined_score=(audio * audio_weight) + (motion * motion_weight),
            )
        )
    return timeline


def _summarize_candidate(
    timeline: list[TimelinePoint],
    start: int,
    end: int,
) -> ClipCandidate:
    points = timeline[start:end]
    audio = [point.audio_score for point in points]
    motion = [point.motion_score for point in points]
    combined = [point.combined_score for point in points]
    return ClipCandidate(
        start_time=float(start),
        end_time=float(end),
        mean_audio=sum(audio) / len(audio),
        peak_audio=max(audio),
        mean_motion=sum(motion) / len(motion),
        peak_motion=max(motion),
        mean_combined=sum(combined) / len(combined),
        peak_combined=max(combined),
    )


def detect_candidates(
    timeline: list[TimelinePoint],
    threshold: float = 0.62,
    gap_tolerance: int = 2,
    padding_before: int = 5,
    padding_after: int = 3,
    minimum_duration: int = 10,
) -> list[ClipCandidate]:
    if not timeline:
        return []
    if minimum_duration <= 0:
        raise ValueError("minimum_duration must be positive")

    hot_seconds = [point.second for point in timeline if point.combined_score >= threshold]
    if not hot_seconds:
        peak = max(timeline, key=lambda item: item.combined_score).second
        hot_seconds = [peak]

    groups: list[tuple[int, int]] = []
    group_start = hot_seconds[0]
    previous = hot_seconds[0]
    for second in hot_seconds[1:]:
        if second - previous > gap_tolerance + 1:
            groups.append((group_start, previous + 1))
            group_start = second
        previous = second
    groups.append((group_start, previous + 1))

    candidates: list[ClipCandidate] = []
    timeline_end = len(timeline)
    for hot_start, hot_end in groups:
        start = max(0, hot_start - padding_before)
        end = min(timeline_end, hot_end + padding_after)
        if end - start < minimum_duration:
            missing = minimum_duration - (end - start)
            start = max(0, start - (missing // 2))
            end = min(timeline_end, end + (missing - missing // 2))
            if end - start < minimum_duration:
                start = max(0, end - minimum_duration)
        if end > start:
            candidates.append(_summarize_candidate(timeline, start, end))

    candidates.sort(key=lambda item: item.peak_combined, reverse=True)
    selected: list[ClipCandidate] = []
    for candidate in candidates:
        overlap = any(
            max(candidate.start_time, existing.start_time)
            < min(candidate.end_time, existing.end_time)
            for existing in selected
        )
        if not overlap:
            selected.append(candidate)
    return selected
