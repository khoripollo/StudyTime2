"""Boundary and progression cases for the pure SM-2 scheduler.

Complements test_sm2.py with the grade-0/grade-1 boundary, repeated
failures, the ease-factor floor, and interval progression. No database
and no HTTP here - review_flashcard is a pure function.
"""

from datetime import datetime, timedelta, timezone

from app.services.sm2 import (
    GRADE_AGAIN,
    GRADE_EASY,
    GRADE_GOOD,
    GRADE_HARD,
    MIN_EASE_FACTOR,
    PASSING_GRADE,
    review_flashcard,
)

# Naive UTC on purpose, matching how Flashcard.due_at is stored.
FIXED_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def _review(grade, ease_factor=2.5, interval_days=0, repetitions=0):
    return review_flashcard(
        grade=grade,
        ease_factor=ease_factor,
        interval_days=interval_days,
        repetitions=repetitions,
        reviewed_at=FIXED_NOW,
    )


def test_hard_is_the_smallest_passing_grade():
    assert PASSING_GRADE == GRADE_HARD

    hard = _review(GRADE_HARD)
    again = _review(GRADE_AGAIN)

    assert (hard.repetitions, hard.interval_days) == (1, 1)
    assert (again.repetitions, again.interval_days) == (0, 1)


def test_repeated_failures_never_grow_the_interval():
    repetitions = 5
    interval_days = 100
    ease_factor = 2.5

    for _ in range(3):
        result = _review(
            GRADE_AGAIN,
            ease_factor=ease_factor,
            interval_days=interval_days,
            repetitions=repetitions,
        )
        assert result.repetitions == 0
        assert result.interval_days == 1
        assert result.due_at == FIXED_NOW + timedelta(days=1)

        repetitions = result.repetitions
        interval_days = result.interval_days
        ease_factor = result.ease_factor


def test_ease_factor_never_falls_below_the_floor_on_repeated_failures():
    ease_factor = MIN_EASE_FACTOR

    for _ in range(5):
        result = _review(GRADE_AGAIN, ease_factor=ease_factor)
        assert result.ease_factor == MIN_EASE_FACTOR
        ease_factor = result.ease_factor


def test_ease_factor_is_lifted_to_the_floor_from_a_below_minimum_value():
    result = _review(GRADE_AGAIN, ease_factor=1.0)

    assert result.ease_factor == MIN_EASE_FACTOR


def test_hard_review_schedules_using_the_lowered_ease_factor():
    result = _review(
        GRADE_HARD, ease_factor=2.5, interval_days=6, repetitions=2
    )

    assert result.repetitions == 3
    assert result.ease_factor < 2.5
    assert result.interval_days == round(6 * result.ease_factor)


def test_easy_review_schedules_no_earlier_than_good():
    good = _review(GRADE_GOOD, interval_days=6, repetitions=2)
    easy = _review(GRADE_EASY, interval_days=6, repetitions=2)

    assert easy.ease_factor > good.ease_factor
    assert easy.interval_days >= good.interval_days
    assert easy.interval_days == round(6 * easy.ease_factor)


def test_interval_grows_with_each_passing_review():
    first = _review(GRADE_GOOD)
    second = _review(
        GRADE_GOOD,
        interval_days=first.interval_days,
        repetitions=first.repetitions,
        ease_factor=first.ease_factor,
    )
    third = _review(
        GRADE_GOOD,
        interval_days=second.interval_days,
        repetitions=second.repetitions,
        ease_factor=second.ease_factor,
    )

    assert first.interval_days == 1
    assert second.interval_days == 6
    assert third.interval_days > second.interval_days


def test_failing_review_honors_the_supplied_reviewed_at():
    result = _review(GRADE_AGAIN, interval_days=30, repetitions=9)

    assert result.due_at == FIXED_NOW + timedelta(days=1)


def test_easy_review_honors_the_supplied_reviewed_at():
    result = _review(GRADE_EASY, interval_days=6, repetitions=2)

    assert result.due_at == FIXED_NOW + timedelta(days=result.interval_days)
