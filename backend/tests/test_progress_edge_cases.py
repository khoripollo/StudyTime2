"""Accuracy rounding, the today boundary, and empty-state serialization.

Complements test_progress.py, which covers the main aggregations and
streak rules.
"""

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.document import Document
from app.models.flashcard import Flashcard, FlashcardSource
from app.models.review_log import ReviewLog
from app.models.user import User
from app.services.progress import compute_progress_stats

client = TestClient(app)

TEST_PASSWORD = "TestPassword123!"
NOW = datetime.utcnow()  # noqa: DTZ003


def unique_email() -> str:
    return f"test-{uuid.uuid4().hex[:8]}@example.com"


def _make_user() -> int:
    db = SessionLocal()
    user = User(email=unique_email(), hashed_password="not-a-real-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    return user_id


def _make_document(user_id: int) -> int:
    db = SessionLocal()
    document = Document(
        user_id=user_id,
        filename="lecture.pdf",
        storage_path=f"{uuid.uuid4().hex}.pdf",
        status="extracted",
    )
    db.add(document)
    db.commit()
    document_id = document.id
    db.close()
    return document_id


def _make_flashcard(document_id: int, *, due_at: datetime) -> int:
    db = SessionLocal()
    flashcard = Flashcard(
        document_id=document_id,
        front="Q",
        back="A",
        source=FlashcardSource.AI_GENERATED,
        due_at=due_at,
    )
    db.add(flashcard)
    db.commit()
    flashcard_id = flashcard.id
    db.close()
    return flashcard_id


def _make_review(flashcard_id: int, grade: int, reviewed_at: datetime) -> None:
    db = SessionLocal()
    db.add(
        ReviewLog(flashcard_id=flashcard_id, grade=grade, reviewed_at=reviewed_at)
    )
    db.commit()
    db.close()


def _cleanup_user(user_id: int) -> None:
    db = SessionLocal()
    doc_ids = [d.id for d in db.query(Document).filter(Document.user_id == user_id)]
    if doc_ids:
        card_ids = [
            f.id
            for f in db.query(Flashcard).filter(Flashcard.document_id.in_(doc_ids))
        ]
        if card_ids:
            db.query(ReviewLog).filter(
                ReviewLog.flashcard_id.in_(card_ids)
            ).delete(synchronize_session=False)
        db.query(Flashcard).filter(
            Flashcard.document_id.in_(doc_ids)
        ).delete(synchronize_session=False)
        db.query(Document).filter(Document.id.in_(doc_ids)).delete(
            synchronize_session=False
        )
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    db.close()


@pytest.fixture
def user_id():
    uid = _make_user()
    yield uid
    _cleanup_user(uid)


@pytest.fixture
def user_and_headers():
    """A real signup/login user, so GET /progress can be exercised."""
    email = unique_email()
    client.post("/auth/signup", json={"email": email, "password": TEST_PASSWORD})
    login = client.post(
        "/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    token = login.json()["access_token"]

    db = SessionLocal()
    uid = db.query(User).filter(User.email == email).first().id
    db.close()

    yield uid, {"Authorization": f"Bearer {token}"}
    _cleanup_user(uid)


def _db():
    return SessionLocal()


def test_accuracy_is_zero_when_every_recent_review_failed(user_id):
    document_id = _make_document(user_id)
    card_id = _make_flashcard(document_id, due_at=NOW)
    for days_ago in range(3):
        _make_review(card_id, grade=0, reviewed_at=NOW - timedelta(days=days_ago))

    stats = compute_progress_stats(_db(), user_id)

    assert stats.reviews_last_7_days == 3
    # 0.0, not None - a failed review is still evidence of activity.
    assert stats.accuracy_last_7_days == 0.0


@pytest.mark.parametrize(
    ("passing", "total", "expected"),
    [(1, 3, 33.3), (2, 3, 66.7)],
)
def test_accuracy_rounds_to_one_decimal(user_id, passing, total, expected):
    document_id = _make_document(user_id)
    card_id = _make_flashcard(document_id, due_at=NOW)

    for i in range(total):
        grade = 2 if i < passing else 0
        _make_review(card_id, grade=grade, reviewed_at=NOW - timedelta(hours=i))

    stats = compute_progress_stats(_db(), user_id)

    assert stats.reviews_last_7_days == total
    assert stats.accuracy_last_7_days == expected


def test_reviews_today_includes_a_review_at_the_start_of_today(user_id):
    document_id = _make_document(user_id)
    card_id = _make_flashcard(document_id, due_at=NOW)
    start_of_today = datetime.combine(NOW.date(), datetime.min.time())
    _make_review(card_id, grade=2, reviewed_at=start_of_today)

    stats = compute_progress_stats(_db(), user_id)

    assert stats.reviews_today == 1


def test_streak_ignores_another_users_reviews(user_id):
    document_id = _make_document(user_id)
    card_id = _make_flashcard(document_id, due_at=NOW)
    _make_review(card_id, grade=0, reviewed_at=NOW)

    other_id = _make_user()
    try:
        other_doc = _make_document(other_id)
        other_card = _make_flashcard(other_doc, due_at=NOW)
        _make_review(other_card, grade=2, reviewed_at=NOW - timedelta(days=1))
        _make_review(other_card, grade=2, reviewed_at=NOW - timedelta(days=2))

        stats = compute_progress_stats(_db(), user_id)

        assert stats.current_streak_days == 1
        assert stats.reviews_last_7_days == 1
        assert stats.accuracy_last_7_days == 0.0
    finally:
        _cleanup_user(other_id)


# ============================================================
# GET /progress serialization
# ============================================================


def test_get_progress_returns_zeros_and_null_accuracy_for_new_user(user_and_headers):
    _, headers = user_and_headers

    response = client.get("/progress", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total_documents"] == 0
    assert body["total_flashcards"] == 0
    assert body["reviews_last_7_days"] == 0
    assert body["accuracy_last_7_days"] is None
    assert body["current_streak_days"] == 0


def test_get_progress_serializes_zero_accuracy_as_zero(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)
    card_id = _make_flashcard(document_id, due_at=NOW)
    _make_review(card_id, grade=0, reviewed_at=NOW)

    response = client.get("/progress", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["reviews_last_7_days"] == 1
    assert body["accuracy_last_7_days"] == 0.0
