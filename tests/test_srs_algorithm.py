"""Unit tests for the SM-2 spaced repetition algorithm."""

from datetime import date, timedelta

import pytest

from quizzer.srs.algorithm import CardState, apply_review, initial_state


def test_initial_state_defaults():
    state, due = initial_state(today=date(2026, 1, 1))
    assert state.ease_factor == 2.5
    assert state.interval_days == 0
    assert state.repetitions == 0
    assert due == date(2026, 1, 1)


def test_first_correct_answer_gives_one_day_interval():
    state = CardState(ease_factor=2.5, interval_days=0, repetitions=0)
    new_state, due = apply_review(state, rating=5, today=date(2026, 1, 1))
    assert new_state.interval_days == 1
    assert new_state.repetitions == 1
    assert due == date(2026, 1, 2)


def test_second_correct_answer_gives_six_day_interval():
    state = CardState(ease_factor=2.5, interval_days=1, repetitions=1)
    new_state, due = apply_review(state, rating=5, today=date(2026, 1, 1))
    assert new_state.interval_days == 6
    assert new_state.repetitions == 2
    assert due == date(2026, 1, 7)


def test_third_correct_uses_ease_factor():
    state = CardState(ease_factor=2.5, interval_days=6, repetitions=2)
    new_state, due = apply_review(state, rating=5, today=date(2026, 1, 1))
    expected_interval = max(1, round(6 * 2.5))  # 15
    assert new_state.interval_days == expected_interval
    assert new_state.repetitions == 3


def test_wrong_answer_resets_repetitions_and_interval():
    state = CardState(ease_factor=2.5, interval_days=15, repetitions=3)
    new_state, due = apply_review(state, rating=0, today=date(2026, 1, 1))
    assert new_state.repetitions == 0
    assert new_state.interval_days == 1
    assert due == date(2026, 1, 2)


def test_wrong_answer_does_not_change_ease_factor():
    state = CardState(ease_factor=2.5, interval_days=6, repetitions=2)
    new_state, _ = apply_review(state, rating=0, today=date(2026, 1, 1))
    assert new_state.ease_factor == 2.5


def test_perfect_answer_increases_ease_factor():
    state = CardState(ease_factor=2.5, interval_days=1, repetitions=1)
    new_state, _ = apply_review(state, rating=5, today=date(2026, 1, 1))
    assert new_state.ease_factor > 2.5


def test_hesitant_answer_decreases_ease_factor():
    state = CardState(ease_factor=2.5, interval_days=1, repetitions=1)
    new_state, _ = apply_review(state, rating=3, today=date(2026, 1, 1))
    assert new_state.ease_factor < 2.5


def test_ease_factor_never_drops_below_1_3():
    # Repeated hesitant reviews should floor at 1.3
    state = CardState(ease_factor=1.3, interval_days=1, repetitions=1)
    new_state, _ = apply_review(state, rating=3, today=date(2026, 1, 1))
    assert new_state.ease_factor >= 1.3


def test_rating_3_still_advances_interval():
    state = CardState(ease_factor=2.5, interval_days=0, repetitions=0)
    new_state, due = apply_review(state, rating=3, today=date(2026, 1, 1))
    assert new_state.interval_days == 1
    assert new_state.repetitions == 1


def test_invalid_rating_raises():
    state = CardState(ease_factor=2.5, interval_days=0, repetitions=0)
    with pytest.raises(ValueError):
        apply_review(state, rating=2)
    with pytest.raises(ValueError):
        apply_review(state, rating=4)
    with pytest.raises(ValueError):
        apply_review(state, rating=-1)


def test_streak_grows_interval_over_multiple_reviews():
    state = CardState(ease_factor=2.5, interval_days=0, repetitions=0)
    today = date(2026, 1, 1)
    for _ in range(5):
        state, due = apply_review(state, rating=5, today=today)
        today = due  # advance to next due date
    assert state.interval_days > 6  # well past the second-review interval
