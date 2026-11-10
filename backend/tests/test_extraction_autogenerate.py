"""AUTO_GENERATE_* chaining in app.workers.tasks.extract_document_text.

The extraction task optionally chains summarization / flashcard / practice
test generation after a successful extraction. These tests pin which flag
triggers which task and confirm nothing is generated when the PDF yields
no text. PdfReader is replaced with a tiny fake so no real PDF is needed;
the generation tasks themselves are mocked at the task boundary, so no
Gemini call can happen.
"""

import uuid
from unittest.mock import patch

import pytest

from app.db import SessionLocal
from app.models.document import Document
from app.models.user import User
from app.workers.tasks import extract_document_text

FLAG_NAMES = (
    "AUTO_GENERATE_SUMMARIES",
    "AUTO_GENERATE_FLASHCARDS",
    "AUTO_GENERATE_PRACTICE_TESTS",
)


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakeReader:
    """Stand-in for pypdf.PdfReader with one page of fixed text."""

    text = "Mitochondria are the powerhouse of the cell."

    def __init__(self, _path):
        self.pages = [_FakePage(self.text)]


class _FakeReaderWithoutText(_FakeReader):
    text = "   "


def unique_email() -> str:
    return f"test-{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture
def document():
    db = SessionLocal()
    user = User(email=unique_email(), hashed_password="not-a-real-hash")
    db.add(user)
    db.commit()
    db.refresh(user)

    doc = Document(
        user_id=user.id,
        filename="lecture.pdf",
        storage_path="not-read-by-the-fake.pdf",
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    yield doc

    db.query(Document).filter(Document.id == doc.id).delete()
    db.query(User).filter(User.id == user.id).delete()
    db.commit()
    db.close()


def _status(document_id: int) -> str:
    db = SessionLocal()
    status = db.get(Document, document_id).status
    db.close()
    return status


def _mock_tasks():
    return (
        patch("app.workers.tasks.generate_summaries"),
        patch("app.workers.tasks.generate_flashcards_task"),
        patch("app.workers.tasks.generate_practice_test_task"),
    )


def test_no_auto_generation_when_every_flag_is_off(document, monkeypatch):
    for name in FLAG_NAMES:
        monkeypatch.delenv(name, raising=False)

    summaries, flashcards, practice = _mock_tasks()
    with summaries as m_summaries, flashcards as m_flashcards, practice as m_practice, patch(
        "app.workers.tasks.PdfReader", _FakeReader
    ):
        extract_document_text(document.id)

    m_summaries.delay.assert_not_called()
    m_flashcards.delay.assert_not_called()
    m_practice.delay.assert_not_called()
    assert _status(document.id) == "extracted"


@pytest.mark.parametrize(
    ("flag", "task_attribute", "other_attributes"),
    [
        ("AUTO_GENERATE_SUMMARIES", "generate_summaries", ("generate_flashcards_task",)),
        ("AUTO_GENERATE_FLASHCARDS", "generate_flashcards_task", ("generate_summaries",)),
        (
            "AUTO_GENERATE_PRACTICE_TESTS",
            "generate_practice_test_task",
            ("generate_summaries", "generate_flashcards_task"),
        ),
    ],
)
def test_each_flag_triggers_only_its_own_generation(
    document, monkeypatch, flag, task_attribute, other_attributes
):
    for name in FLAG_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(flag, "true")

    summaries, flashcards, practice = _mock_tasks()
    with summaries as m_summaries, flashcards as m_flashcards, practice as m_practice:
        mocks = {
            "generate_summaries": m_summaries,
            "generate_flashcards_task": m_flashcards,
            "generate_practice_test_task": m_practice,
        }

        with patch("app.workers.tasks.PdfReader", _FakeReader):
            extract_document_text(document.id)

    mocks[task_attribute].delay.assert_called_once_with(document.id)
    for attribute in other_attributes:
        mocks[attribute].delay.assert_not_called()
    assert _status(document.id) == "extracted"


def test_flags_do_not_chain_generation_when_pdf_has_no_text(document, monkeypatch):
    for name in FLAG_NAMES:
        monkeypatch.setenv(name, "true")

    summaries, flashcards, practice = _mock_tasks()
    with summaries as m_summaries, flashcards as m_flashcards, practice as m_practice, patch(
        "app.workers.tasks.PdfReader", _FakeReaderWithoutText
    ):
        extract_document_text(document.id)

    m_summaries.delay.assert_not_called()
    m_flashcards.delay.assert_not_called()
    m_practice.delay.assert_not_called()
    assert _status(document.id) == "no_text_found"
