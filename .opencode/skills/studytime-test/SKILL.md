---
name: studytime-test
description: "Generate and run StudyTime2 backend unit and integration tests, including edge cases and error handling. Use when writing pytest tests, raising backend coverage, reproducing a defect with a failing test, or verifying a fix for auth, uploads, flashcards, SM-2, practice tests, or progress."
license: CC-BY-4.0
---

# StudyTime2 Test Skill

Procedural guide for the `@studytime-tester` agent. It defines how to inspect the
StudyTime2 backend, write tests that match the existing suite, run them, measure
coverage, and report failures without ever hiding a red gate.

StudyTime2 is a FastAPI + SQLAlchemy backend with Celery workers, PostgreSQL, and a
React frontend. The backend test suite lives in `backend/tests/` and runs against a
real PostgreSQL database with all Gemini calls mocked.

## When to use

- Adding unit or integration tests for a StudyTime2 feature.
- Raising backend coverage toward the 80 percent gate.
- Reproducing a reported defect as a failing test before any fix.
- Confirming a fix with a test that would have caught the regression.

## Quality gates this skill produces evidence for

| Gate | Measurement | Pass criterion |
|------|-------------|----------------|
| G1 Tests pass | `python -m pytest -q` | exit 0, 0 failed, 0 errors |
| G2 Backend coverage | `python -m pytest --cov=app --cov-fail-under=80` | total coverage of `app/` >= 80.0 percent |
| G3 Ruff lint | `python -m ruff check .` | exit 0, 0 violations |
| G5 Traceability input | the per-area checklist below | every documented endpoint and capability in the area has at least one test |

G4 (frontend lint and build) belongs to `@studytime-reviewer`. Run it only when the
change touches frontend code, and report it as supporting evidence, not as a gate you
own.

## Permissions

| Path or action | Rule |
|----------------|------|
| `backend/tests/**` | write without asking |
| `backend/app/**`, `frontend/**`, `backend/alembic/**`, `.github/**`, `backend/requirements.txt`, `.env` | request approval with the `question` tool first |
| `AGENTS.md`, `PHASE.md`, `opencode.json`, other agents and skills | never |
| `git commit`, `git push`, history rewrite | never |
| Dependency installs, Docker lifecycle, database resets | request approval first |

## Non-negotiables

1. Run from `backend/` (the `app` package must be importable). Use the shell's
   working-directory option rather than `cd`.
2. Never call the live Gemini API. Patch `app.services.*.generate_structured` or
   `app.workers.tasks.<task>`.
3. Never weaken, skip, or delete an existing test to make a gate green.
4. Never lower `--cov-fail-under`, add coverage exclusions, or mark lines
   `# pragma: no cover` to reach the threshold.
5. Never edit application code without approval from the `question` tool.
6. Never report a result you did not execute. Unavailable means `NOT RUN`.

## Step 1 - Environment preflight (blocking)

Run these checks before writing a test. The suite needs PostgreSQL, a schema, and
four environment variables; `conftest.py` handles only `UPLOAD_DIR`.

```powershell
# Repository and tooling
Test-Path backend\tests
Test-Path .env
docker info --format "{{.ServerVersion}}"
docker compose version
```

Required backend environment (matches `.github/workflows/ci.yml`):

```
DATABASE_URL=postgresql://studytime:studytime@localhost:5432/studytime
SECRET_KEY=<any non-empty value>
GEMINI_API_KEY=<any non-empty value>   # only satisfies import-time reads
CELERY_TASK_ALWAYS_EAGER=true          # runs .delay() inline, no Redis needed
```

The database must already contain the schema. Tests do not create tables:

```powershell
alembic upgrade head
```

If any prerequisite is missing, stop and return:

```
Environment: blocked: <missing prerequisite>
Gates: G1 NOT RUN | G2 NOT RUN | G3 NOT RUN
Recommended prerequisite: <exact command or file the student must provide>
```

### Preferred execution path in this repo

Local Python is 3.13/3.14 while the project targets 3.12, and
`psycopg2-binary==2.9.9` may not have wheels for the newer interpreters. Prefer the
Python 3.12 container, which also installs the pinned test dependencies:

```powershell
# Requires .env (creating it is an approval-gated change)
docker compose run --rm backend sh -c "alembic upgrade head && python -m pytest -q"
```

Local fallback, only when a compatible 3.12 environment already exists:

```powershell
# from backend/
python -m pytest -q
```

## Step 2 - Repo map

| Area | Production code | Existing tests |
|---|---|---|
| Authentication | `app/api/auth.py`, `app/api/deps.py`, `app/services/auth.py` | `tests/test_auth.py` |
| PDF upload and extraction | `app/api/documents.py`, `app/workers/tasks.py`, `app/storage.py` | `tests/test_documents.py`, `test_extraction.py`, `test_delete_document.py` |
| Flashcards | `app/api/flashcards.py`, `app/services/flashcard_generation.py` | `tests/test_flashcards.py`, `test_document_flashcards.py`, `test_flashcard_generation.py` |
| SM-2 | `app/services/sm2.py` | `tests/test_sm2.py` |
| Practice tests | `app/api/practice_tests.py`, `app/services/practice_test_generation.py` | `tests/test_practice_test_generation.py`, `test_practice_test_taking.py` |
| Progress | `app/api/progress.py`, `app/services/progress.py` | `tests/test_progress.py` |
| Cross-cutting | `app/db.py`, `app/main.py`, `app/schemas/**`, `app/models/**` | covered indirectly only |

## Step 3 - Follow the existing conventions

These patterns are already established in the suite. Match them rather than
introducing a second style.

```python
import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def unique_email() -> str:
    # Every test creates its own user, then deletes its rows in FK order.
    return f"tester-{uuid.uuid4().hex[:8]}@example.com"
```

- Get tokens from the real endpoints (`POST /auth/signup`, then `POST /auth/login`)
  and send `{"Authorization": f"Bearer {token}"}`. Do not forge JWTs unless the
  test is specifically about token validation.
- Insert rows for setup only when no endpoint can create them (for example a
  `Flashcard` with a chosen `due_at`); otherwise go through the API.
- Mock generation at the service boundary and assert on the persisted result:

```python
from unittest.mock import patch

with patch("app.services.flashcard_generation.generate_structured") as generate:
    generate.return_value = <a batch object shaped like the existing tests>
```

Copy the exact batch/model shapes from the existing test file you are extending;
do not invent constructor names.
- Use `CELERY_TASK_ALWAYS_EAGER=true` so `.delay()` executes inline. Never require
  a Redis broker.
- Clean up in foreign-key order in a fixture teardown: `ReviewLog`, `TestQuestion`,
  `PracticeTest`, `Flashcard`, `Note`, `Summary`, `Document`, `User`.

## Step 4 - Test-design checklist (edge cases and error handling)

### Authentication
- Signup success returns `201` and never leaks `hashed_password` or `password`.
- Duplicate email returns `400`; email comparison behavior is asserted explicitly.
- Wrong password, unknown user, missing token, malformed token: `401`.
- Expired token and token signed with the wrong secret: `401`.
- Validly signed token whose subject user no longer exists: `401`, not `500`.
- `/auth/me` returns the caller's own identity only.

### PDF upload and extraction
- `401` without a token.
- Non-PDF content type: `400`.
- Empty file: `400`.
- File larger than `MAX_UPLOAD_BYTES` (20 MB in `app/api/documents.py`): `400`.
- Successful upload: `201`, `status == "pending"`, and `storage_path` is not exposed.
- Missing `filename`: falls back to the stored path without crashing.
- Extraction outcomes: `extracted`, `no_text_found`, `extraction_failed` for corrupt
  or missing files, and no exception for a missing document.
- Deleting a document removes every related row and the file on disk, and tolerates
  a file that is already gone.
- Another user's document is always `404`, never `403` and never readable.

### Flashcards
- Due list includes a card due exactly now, excludes a future card, excludes other
  users' cards.
- Review accepts grades 0-3 and updates `repetitions`, `interval_days`, and `due_at`;
  grade 7 returns `422`.
- Every review writes exactly one `ReviewLog` with the submitted grade.
- Manual creation defaults to `repetitions == 0`, `ease_factor == 2.5`, source
  `manual`; empty front or back returns `422`.
- Regenerating flashcards replaces AI-generated cards and preserves manual cards.
- Missing document or missing extracted text does not raise.

### SM-2 (`app/services/sm2.py`, pure function - no database)
- Grade 0 resets `repetitions` to 0 and `interval_days` to 1.
- First passing review: repetitions 1, interval 1. Second: repetitions 2, interval 6.
- Third and later: `interval = round(previous_interval * new_ease_factor)`.
- Ease increases for Easy, decreases for Hard, and never drops below 1.3.
- `reviewed_at` is honored when supplied and defaults to now when omitted.
- Boundary: grade 0 fails and grade 1 passes (`PASSING_GRADE`).

### Practice tests
- GET returns questions without `correct_answer`.
- Submit scores correct and incorrect answers and reports the expected total.
- Grading normalizes case and surrounding whitespace.
- A missing answer counts as incorrect rather than erroring.
- Question IDs that belong to a different practice test are not scored.
- Regeneration replaces the previous test and its questions.
- Another user's test returns `404`.
- Generation outside the 404/400 paths still surfaces `GenerationError`.

### Progress
- A new user gets all zeros and `accuracy_last_7_days is None`.
- Accuracy is `0.0` when reviews exist but all failed; `None` only when there are
  no reviews.
- Accuracy rounds to one decimal (check `1/3` and `2/3`).
- `reviews_today` includes a review at exactly the start of today.
- Streak counts consecutive days including today; stays alive if the last review was
  yesterday; breaks on a gap; is 0 with no reviews.
- `cards_mastered` uses the `repetitions >= 3` threshold.
- No count ever includes another user's data.

### Background workers (`app/workers/tasks.py`)
- Missing document: returns quietly.
- No extracted text: no generator call and no rows written.
- `GenerationError` from the generator: assert the chosen behavior (propagate or
  record failure) and pin it with a test.
- `AUTO_GENERATE_*` flags: document current behavior and test the enabled path.

## Step 5 - Run

```powershell
# from backend/

# Targeted first
python -m pytest tests/test_sm2.py -q

# Full suite
python -m pytest -q

# Coverage gate (equal to G2)
python -m pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=80 -q

# Lint gate (G3)
python -m ruff check .

# Frontend gates (G4) - only when in scope; run from frontend/
npm ci
npm run lint
npm run build
```

## Step 6 - Triage failures

For each failure, answer three questions before changing anything:

1. Is the expected behavior documented (README, route code, schema)?
2. Does the test express that behavior, or an implementation detail?
3. If the product is wrong, what is the smallest change that makes the test pass
   without breaking the contract?

| Verdict | Action |
|---|---|
| Test bug (wrong expectation, bad setup, shared state) | Fix in `backend/tests/**`. Allowed immediately. |
| Product bug | Keep the failing test. Write a recommendation. Request approval. |
| Flaky test | Reproduce at least twice, report both outcomes, remove the source of non-determinism. |
| Environment defect | Report `NOT RUN` with the missing prerequisite. |

If coverage is below 80 percent, produce the list of high-value uncovered lines from
`--cov-report=term-missing` and add tests for behavior, not just for line execution.

## Step 7 - Output

Return the tester result block defined by `@studytime-tester`, including every
command's exit code. For each failure, use this format:

```
V-01 [Blocker|High|Medium|Low] <path>:<line> - <one-line symptom>
Expected: <...>
Actual:   <...>
Cause:    <root cause>
Fix:      <minimal recommendation>
Test:     <test that proves the fix>
Approval: required | not required
```

## Do not

- Add a test that passes for the wrong reason (for example asserting only a `200`
  when the contract is about the response body).
- Assert a Gemini prompt string as the primary evidence; assert stored and returned
  behavior instead.
- Share mutable state between tests or rely on execution order.
- Create tables, drop tables, or truncate shared tables inside a test.
- Touch `backend/uploads/` or any real user data.
- Report a gate as passing because CI passes on `main`; this run's evidence is what
  counts.
