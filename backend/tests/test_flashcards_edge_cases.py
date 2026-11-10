"""Review-flow edge cases for flashcards.

Complements test_flashcards.py with the due-now boundary, a failing review
on a mature card, grade 1/3 behaviour, auth enforcement on the review
endpoint, and persistence across more than one review.
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

client = TestClient(app)

TEST_PASSWORD = "TestPassword123!"


def now() -> datetime:
    # Naive UTC on purpose - matches Flashcard.due_at's storage format.
    return datetime.utcnow()  # noqa: DTZ003


def unique_email() -> str:
    return f"test-{uuid.uuid4().hex[:8]}@example.com"


def _create_user_and_token() -> tuple[int, str]:
    email = unique_email()
    client.post("/auth/signup", json={"email": email, "password": TEST_PASSWORD})
    login = client.post(
        "/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    token = login.json()["access_token"]

    db = SessionLocal()
    user_id = db.query(User).filter(User.email == email).first().id
    db.close()
    return user_id, token


def _make_document(user_id: int) -> int:
    db = SessionLocal()
    document = Document(
        user_id=user_id,
        filename="test.pdf",
        storage_path=f"{uuid.uuid4().hex}.pdf",
        status="extracted",
    )
    db.add(document)
    db.commit()
    document_id = document.id
    db.close()
    return document_id


def _make_flashcard(
    document_id: int,
    *,
    due_at: datetime,
    ease_factor: float = 2.5,
    interval_days: int = 0,
    repetitions: int = 0,
) -> int:
    db = SessionLocal()
    flashcard = Flashcard(
        document_id=document_id,
        front="Q",
        back="A",
        source=FlashcardSource.AI_GENERATED,
        ease_factor=ease_factor,
        interval_days=interval_days,
        repetitions=repetitions,
        due_at=due_at,
    )
    db.add(flashcard)
    db.commit()
    flashcard_id = flashcard.id
    db.close()
    return flashcard_id


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
def user_and_headers():
    user_id, token = _create_user_and_token()
    yield user_id, {"Authorization": f"Bearer {token}"}
    _cleanup_user(user_id)


def _review(flashcard_id: int, grade: int, headers: dict):
    return client.post(
        f"/flashcards/{flashcard_id}/review", json={"grade": grade}, headers=headers
    )


def test_due_flashcards_includes_card_due_exactly_now(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)
    _make_flashcard(document_id, due_at=now())

    response = client.get("/flashcards/due", headers=headers)

    assert response.status_code == 200
    ids = [card["id"] for card in response.json()]
    assert len(ids) == 1


def test_failing_review_resets_a_mature_card(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)
    flashcard_id = _make_flashcard(
        document_id,
        due_at=now() - timedelta(days=20),
        ease_factor=2.8,
        interval_days=15,
        repetitions=4,
    )

    response = _review(flashcard_id, 0, headers)

    assert response.status_code == 200
    body = response.json()
    assert body["repetitions"] == 0
    assert body["interval_days"] == 1
    assert body["ease_factor"] >= 1.3

    db = SessionLocal()
    logs = db.query(ReviewLog).filter(ReviewLog.flashcard_id == flashcard_id).all()
    assert len(logs) == 1
    assert logs[0].grade == 0
    db.close()


def test_hard_review_counts_as_a_pass(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)
    flashcard_id = _make_flashcard(document_id, due_at=now(), ease_factor=2.5)

    response = _review(flashcard_id, 1, headers)

    assert response.status_code == 200
    body = response.json()
    assert body["repetitions"] == 1
    assert body["interval_days"] == 1
    assert body["ease_factor"] < 2.5


def test_easy_review_increases_ease_factor(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)
    flashcard_id = _make_flashcard(document_id, due_at=now(), ease_factor=2.5)

    response = _review(flashcard_id, 3, headers)

    assert response.status_code == 200
    body = response.json()
    assert body["repetitions"] == 1
    assert body["ease_factor"] > 2.5


def test_review_requires_auth(user_and_headers):
    user_id, _headers = user_and_headers
    document_id = _make_document(user_id)
    flashcard_id = _make_flashcard(document_id, due_at=now())

    response = client.post(f"/flashcards/{flashcard_id}/review", json={"grade": 2})

    assert response.status_code == 401


def test_review_rejects_negative_grade(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)
    flashcard_id = _make_flashcard(document_id, due_at=now())

    response = _review(flashcard_id, -1, headers)

    assert response.status_code == 422


def test_second_review_builds_on_the_first_and_persists(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)
    flashcard_id = _make_flashcard(document_id, due_at=now())

    first = _review(flashcard_id, 2, headers)
    second = _review(flashcard_id, 2, headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["repetitions"] == 2
    assert second.json()["interval_days"] == 6

    db = SessionLocal()
    logs = db.query(ReviewLog).filter(ReviewLog.flashcard_id == flashcard_id).all()
    assert len(logs) == 2
    assert [log.grade for log in logs] == [2, 2]
    db.close()

    persisted = client.get(f"/documents/{document_id}/flashcards", headers=headers)
    assert persisted.status_code == 200
    card = persisted.json()[0]
    assert card["repetitions"] == 2
    assert card["interval_days"] == 6
