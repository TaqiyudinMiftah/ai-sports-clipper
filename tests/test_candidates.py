from sports_clipper.candidate_detection import build_timeline, detect_candidates
from sports_clipper.scoring import rank_candidates


def test_build_timeline_combines_audio_and_motion() -> None:
    timeline = build_timeline([1.0], [0.0], audio_weight=0.6)
    assert timeline[0].combined_score == 0.6


def test_detect_candidates_adds_minimum_duration_padding() -> None:
    audio = [0.0] * 30
    motion = [0.0] * 30
    for second in range(12, 16):
        audio[second] = 1.0
        motion[second] = 1.0

    candidates = detect_candidates(build_timeline(audio, motion), threshold=0.6)
    assert len(candidates) == 1
    assert candidates[0].duration >= 10
    assert candidates[0].start_time <= 12
    assert candidates[0].end_time >= 16


def test_ranking_prefers_stronger_candidate() -> None:
    audio = [0.0] * 40
    motion = [0.0] * 40
    for second in range(5, 9):
        audio[second] = 0.7
        motion[second] = 0.7
    for second in range(25, 30):
        audio[second] = 1.0
        motion[second] = 1.0

    ranked = rank_candidates(
        detect_candidates(build_timeline(audio, motion), threshold=0.6)
    )
    assert ranked[0].peak_combined == 1.0
    assert ranked[0].score >= ranked[-1].score
