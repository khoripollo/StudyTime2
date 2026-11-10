"""Upload limits and the manual generation triggers for documents.

Complements test_documents.py / test_summary.py / test_flashcard_generation.py:
the 20 MB backstop, a missing filename, manual-flashcard boundaries, and
the POST /documents/{id}/generate-* endpoints (their auth, ownership,
missing-text and success paths).
"""

import asyncio
import uuid
from io import BytesIO
from unittest.mock import patch

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from app.api.documents import MAX_UPLOAD_BYTES, upload_document
from app.db import SessionLocal
from app.main import app
from app.models.document import Document
from app.models.flashcard import Flashcard
from app.models.note import Note
from app.models.practice_test import PracticeTest, TestQuestion
from app.models.review_log import ReviewLog
from app.models.summary import Summary
from app.models.user import User
from app.services.flashcard_generation import FlashcardBatch, FlashcardContent
from app.services.summary import SummaryContent

client = TestClient(app)

TEST_PASSWORD = "TestPassword123!"
FAKE_PDF_BYTES = b"%PDF-1.4\n%fake pdf content for tests\n"


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
        test_ids = [
            t.id
            for t in db.query(PracticeTest).filter(
                PracticeTest.document_id.in_(doc_ids)
            )
        ]
        if test_ids:
            db.query(TestQuestion).filter(
                TestQuestion.practice_test_id.in_(test_ids)
            ).delete(synchronize_session=False)
            db.query(PracticeTest).filter(
                PracticeTest.id.in_(test_ids)
            ).delete(synchronize_session=False)
        db.query(Flashcard).filter(
            Flashcard.document_id.in_(doc_ids)
        ).delete(synchronize_session=False)
        db.query(Note).filter(Note.document_id.in_(doc_ids)).delete(
            synchronize_session=False
        )
        db.query(Summary).filter(Summary.document_id.in_(doc_ids)).delete(
            synchronize_session=False
        )
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


def _make_document(user_id: int, *, extracted_text=None) -> int:
    db = SessionLocal()
    document = Document(
        user_id=user_id,
        filename="test.pdf",
        storage_path=f"{uuid.uuid4().hex}.pdf",
        status="extracted" if extracted_text else "pending",
        extracted_text=extracted_text,
    )
    db.add(document)
    db.commit()
    document_id = document.id
    db.close()
    return document_id


# ============================================================
# Upload validation
# ============================================================


def test_upload_rejects_file_larger_than_the_limit(user_and_headers):
    _, headers = user_and_headers
    oversized = b"x" * (MAX_UPLOAD_BYTES + 1)

    response = client.post(
        "/documents",
        files={"file": ("big.pdf", oversized, "application/pdf")},
        headers=headers,
    )

    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()


def test_upload_handler_falls_back_to_a_stored_name_when_filename_is_missing(
    user_and_headers,
):
    """The upload handler is defensive about a missing original filename.

    A multipart part with no filename is parsed by Starlette as a plain
    form field, so FastAPI rejects it with 422 before the handler runs -
    that path can't be driven through the HTTP client. This calls the
    handler directly to pin its own fallback: the stored row uses the
    generated storage name rather than an empty filename.
    """
    user_id, _headers = user_and_headers
    upload = UploadFile(
        file=BytesIO(FAKE_PDF_BYTES),
        filename=None,
        size=len(FAKE_PDF_BYTES),
        headers=Headers({"content-type": "application/pdf"}),
    )

    db = SessionLocal()
    user = db.get(User, user_id)
    try:
        document = asyncio.run(
            upload_document(file=upload, current_user=user, db=db)
        )
        assert document.filename
        assert document.filename == document.storage_path
        assert document.filename.endswith(".pdf")
    finally:
        db.close()


# ============================================================
# Manual flashcard creation boundaries
# ============================================================


def test_create_manual_flashcard_rejects_empty_back(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)

    response = client.post(
        f"/documents/{document_id}/flashcards",
        json={"front": "Q", "back": ""},
        headers=headers,
    )

    assert response.status_code == 422


def test_create_manual_flashcard_accepts_max_length_front(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)
    front = "x" * 2000

    response = client.post(
        f"/documents/{document_id}/flashcards",
        json={"front": front, "back": "A"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["front"] == front


def test_create_manual_flashcard_rejects_over_max_length_front(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)

    response = client.post(
        f"/documents/{document_id}/flashcards",
        json={"front": "x" * 2001, "back": "A"},
        headers=headers,
    )

    assert response.status_code == 422


# ============================================================
# GET /documents/{id}/summaries - ownership gate
# ============================================================


def test_list_summaries_404s_for_nonexistent_document(user_and_headers):
    _, headers = user_and_headers

    response = client.get("/documents/999999999/summaries", headers=headers)

    assert response.status_code == 404


def test_list_summaries_404s_for_other_users_document(user_and_headers):
    _, headers = user_and_headers
    other_id, _other_token = _create_user_and_token()
    document_id = _make_document(other_id, extracted_text="some text")

    try:
        response = client.get(
            f"/documents/{document_id}/summaries", headers=headers
        )
        assert response.status_code == 404
    finally:
        _cleanup_user(other_id)


# ============================================================
# POST /documents/{id}/generate-summaries
# ============================================================


def test_generate_summaries_requires_auth():
    response = client.post("/documents/1/generate-summaries")

    assert response.status_code == 401


def test_generate_summaries_404s_for_nonexistent_document(user_and_headers):
    _, headers = user_and_headers

    response = client.post("/documents/999999999/generate-summaries", headers=headers)

    assert response.status_code == 404


def test_generate_summaries_404s_for_other_users_document(user_and_headers):
    _, headers = user_and_headers
    other_id, _other_token = _create_user_and_token()
    document_id = _make_document(other_id, extracted_text="some text")

    try:
        response = client.post(
            f"/documents/{document_id}/generate-summaries", headers=headers
        )
        assert response.status_code == 404
    finally:
        _cleanup_user(other_id)


def test_generate_summaries_requires_extracted_text(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)

    response = client.post(
        f"/documents/{document_id}/generate-summaries", headers=headers
    )

    assert response.status_code == 400


def test_generate_summaries_starts_and_persists_generation(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id, extracted_text="some study material")

    with patch("app.services.summary.generate_structured") as mock_generate:
        mock_generate.return_value = SummaryContent(text="a generated summary")

        response = client.post(
            f"/documents/{document_id}/generate-summaries", headers=headers
        )
        assert response.status_code == 202

    listed = client.get(f"/documents/{document_id}/summaries", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 3
    assert {s["content"] for s in listed.json()} == {"a generated summary"}


# ============================================================
# POST /documents/{id}/generate-flashcards
# ============================================================


def test_generate_flashcards_requires_auth():
    response = client.post("/documents/1/generate-flashcards")

    assert response.status_code == 401


def test_generate_flashcards_404s_for_nonexistent_document(user_and_headers):
    _, headers = user_and_headers

    response = client.post("/documents/999999999/generate-flashcards", headers=headers)

    assert response.status_code == 404


def test_generate_flashcards_404s_for_other_users_document(user_and_headers):
    _, headers = user_and_headers
    other_id, _other_token = _create_user_and_token()
    document_id = _make_document(other_id, extracted_text="some text")

    try:
        response = client.post(
            f"/documents/{document_id}/generate-flashcards", headers=headers
        )
        assert response.status_code == 404
    finally:
        _cleanup_user(other_id)


def test_generate_flashcards_requires_extracted_text(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)

    response = client.post(
        f"/documents/{document_id}/generate-flashcards", headers=headers
    )

    assert response.status_code == 400


def test_generate_flashcards_starts_and_persists_generation(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id, extracted_text="some study material")

    with patch("app.services.flashcard_generation.generate_structured") as mock_generate:
        mock_generate.return_value = FlashcardBatch(
            cards=[FlashcardContent(front="What is SM-2?", back="A scheduler.")]
        )

        response = client.post(
            f"/documents/{document_id}/generate-flashcards", headers=headers
        )
        assert response.status_code == 202

    listed = client.get(f"/documents/{document_id}/flashcards", headers=headers)
    assert listed.status_code == 200
    cards = listed.json()
    assert len(cards) == 1
    assert cards[0]["front"] == "What is SM-2?"
    assert cards[0]["source"] == "ai_generated"
