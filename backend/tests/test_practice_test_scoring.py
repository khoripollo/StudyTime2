"""All-correct / all-wrong / foreign-id grading cases for practice tests.

Complements test_practice_test_taking.py with the ends of the score range,
an empty test, an unknown test id, foreign question references, and the
answer-length limit.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.document import Document
from app.models.practice_test import PracticeTest, TestQuestion
from app.models.user import User

client = TestClient(app)

TEST_PASSWORD = "TestPassword123!"


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
        extracted_text="some text",
    )
    db.add(document)
    db.commit()
    document_id = document.id
    db.close()
    return document_id


def _make_practice_test(
    document_id: int, questions: list[tuple[str, str]]
) -> tuple[int, list[int]]:
    db = SessionLocal()
    practice_test = PracticeTest(document_id=document_id)
    db.add(practice_test)
    db.flush()

    question_ids = []
    for question_text, correct_answer in questions:
        question = TestQuestion(
            practice_test_id=practice_test.id,
            question=question_text,
            correct_answer=correct_answer,
        )
        db.add(question)
        db.flush()
        question_ids.append(question.id)

    db.commit()
    practice_test_id = practice_test.id
    db.close()
    return practice_test_id, question_ids


def _cleanup_user(user_id: int) -> None:
    db = SessionLocal()
    doc_ids = [d.id for d in db.query(Document).filter(Document.user_id == user_id)]
    if doc_ids:
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


def _submit(practice_test_id: int, answers: list[dict], headers: dict):
    return client.post(
        f"/practice-tests/{practice_test_id}/submit",
        json={"answers": answers},
        headers=headers,
    )


def test_submit_all_correct_scores_full_marks(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)
    practice_test_id, question_ids = _make_practice_test(
        document_id,
        [("Q1", "A1"), ("Q2", "A2"), ("Q3", "A3")],
    )

    response = _submit(
        practice_test_id,
        [
            {"question_id": question_ids[0], "answer": "A1"},
            {"question_id": question_ids[1], "answer": "A2"},
            {"question_id": question_ids[2], "answer": "A3"},
        ],
        headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 3
    assert body["total"] == 3
    assert all(result["is_correct"] for result in body["results"])


def test_submit_all_incorrect_scores_zero(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)
    practice_test_id, question_ids = _make_practice_test(
        document_id, [("Q1", "A1"), ("Q2", "A2")]
    )

    response = _submit(
        practice_test_id,
        [
            {"question_id": question_ids[0], "answer": "wrong"},
            {"question_id": question_ids[1], "answer": "also wrong"},
        ],
        headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 0
    assert body["total"] == 2
    assert all(not result["is_correct"] for result in body["results"])
    # The results view still echoes the right answers back for review.
    assert {r["correct_answer"] for r in body["results"]} == {"A1", "A2"}


def test_submit_ignores_question_ids_from_another_test(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)
    practice_test_id, question_ids = _make_practice_test(
        document_id, [("Q1", "A1"), ("Q2", "A2")]
    )
    other_test_id, other_question_ids = _make_practice_test(
        document_id, [("Other Q", "Other A")]
    )

    response = _submit(
        practice_test_id,
        [
            {"question_id": question_ids[0], "answer": "A1"},
            {"question_id": question_ids[1], "answer": "wrong"},
            # Belongs to a different test - must not be scored as part of this one.
            {"question_id": other_question_ids[0], "answer": "Other A"},
        ],
        headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 1
    assert body["total"] == 2
    scored_ids = {result["question_id"] for result in body["results"]}
    assert scored_ids == set(question_ids)
    assert other_test_id != practice_test_id
    assert other_question_ids[0] not in scored_ids


def test_submit_empty_test_reports_zero_out_of_zero(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)
    practice_test_id, _ = _make_practice_test(document_id, [])

    response = _submit(practice_test_id, [], headers)

    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 0
    assert body["total"] == 0
    assert body["results"] == []


def test_submit_404s_for_nonexistent_test(user_and_headers):
    _, headers = user_and_headers

    response = _submit(999999999, [], headers)

    assert response.status_code == 404


def test_submit_rejects_an_answer_over_the_length_limit(user_and_headers):
    user_id, headers = user_and_headers
    document_id = _make_document(user_id)
    practice_test_id, question_ids = _make_practice_test(
        document_id, [("Q1", "A1")]
    )

    response = _submit(
        practice_test_id,
        [{"question_id": question_ids[0], "answer": "x" * 2001}],
        headers,
    )

    assert response.status_code == 422
