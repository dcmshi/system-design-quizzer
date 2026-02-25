"""SM-2 spaced repetition algorithm (pure functions, no I/O)."""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class CardState:
    ease_factor: float   # >= 1.3, starts at 2.5
    interval_days: int   # days until next review
    repetitions: int     # consecutive correct reviews


def initial_state(today: date | None = None) -> tuple[CardState, date]:
    """Return the default state for a brand-new card and its due date (today)."""
    state = CardState(ease_factor=2.5, interval_days=0, repetitions=0)
    due = today or date.today()
    return state, due


def apply_review(state: CardState, rating: int, today: date | None = None) -> tuple[CardState, date]:
    """Apply one SM-2 review cycle.

    rating:
        0 — wrong / complete blackout
        3 — correct but with significant difficulty / hesitation
        5 — perfect response

    Returns (updated_state, next_due_date).
    """
    if rating not in (0, 3, 5):
        raise ValueError(f"rating must be 0, 3, or 5; got {rating}")

    _today = today or date.today()

    if rating >= 3:
        # Correct answer — advance interval
        if state.repetitions == 0:
            interval = 1
        elif state.repetitions == 1:
            interval = 6
        else:
            interval = max(1, round(state.interval_days * state.ease_factor))

        new_ef = state.ease_factor + (
            0.1 - (5 - rating) * (0.08 + (5 - rating) * 0.02)
        )
        new_ef = max(1.3, new_ef)
        new_reps = state.repetitions + 1
    else:
        # Wrong answer — reset to day 1
        interval = 1
        new_ef = state.ease_factor  # SM-2 does not penalise EF on failure
        new_reps = 0

    due = _today + timedelta(days=interval)
    return CardState(ease_factor=new_ef, interval_days=interval, repetitions=new_reps), due
