# Verification Report — StudyTime2 — 2026-11-10 16:29 (America/New_York)

Branch: `verification-agents` | Commit: `a42db0c` (`a42db0c8803142a7f1fe2d0df005ec3408338a61`, "Final README")
Reviewer: `@studytime-reviewer` | Executed: 2026-11-10, locally, in throwaway Docker containers.

Working tree at start and end of run (`git status --porcelain`, identical both times):

```
?? .opencode/
?? AGENTS.md
?? PHASE.md
?? backend/tests/test_auth_edge_cases.py
?? backend/tests/test_documents_edge_cases.py
?? backend/tests/test_extraction_autogenerate.py
?? backend/tests/test_flashcards_edge_cases.py
?? backend/tests/test_practice_test_scoring.py
?? backend/tests/test_progress_edge_cases.py
?? backend/tests/test_sm2_edge_cases.py
?? opencode.json
```

The seven untracked `backend/tests/test_*_edge_cases.py` / `test_extraction_autogenerate.py` /
`test_practice_test_scoring.py` files pre-date this run (they are the previous `studytime-test`
work). Nothing under `backend/app/`, `backend/tests/`, or `frontend/src/` was modified by this run.

Report path note: the caller requested `docs/verification-report.md`, which is outside this
agent's configured write scope (`docs/verification/**` only). The caller approved writing to
`docs/verification/verification-report.md` instead (approval R-01). No other file was written.

---

## 1. Verdict

**Overall: FAIL**

| Gate | Status | Evidence |
|------|--------|----------|
| G1 Tests | **FAIL** | `python -m pytest -q` → exit 1; **196 passed, 1 failed, 0 skipped**; failure `test_me_rejects_signed_token_with_non_numeric_subject` (`500 != 401`) |
| G2 Coverage | **PASS** | `TOTAL 801 0 100%`; `coverage report --fail-under=80` → exit 0 (100.0% vs 80%) |
| G3 Ruff | **FAIL** | `ruff 0.17.4 check .` → exit 1; 1 violation: `RUF100` at `app/services/progress.py:147` |
| G4 Frontend | **PASS** | `npm ci` 0, `npm run lint` 0 (2 warnings), `npm run build` 0 (vite 8.3.0) |
| G5 Requirements | **FAIL** | 23/23 README endpoints have HTTP-level evidence; 6/7 capabilities fully evidenced — capability 5 is documented as "multiple-choice" but implemented as short-answer, and no test exercises a retake |

Nothing is `COULD NOT BE EVALUATED`; all five gates were executed in this session.

---

## 2. Environment

| Component | Observed | How |
|---|---|---|
| Host OS | Windows (win32) | — |
| Host Python | 3.14.5 (also 3.13 installed) — **not used** (project targets 3.12; `psycopg2-binary==2.9.9` is not installable on 3.14) | `python --version`, `py -0p` |
| Backend Python | **3.12.16** | `python:3.12-slim` via `backend/Dockerfile` |
| Backend image | `studytime-verify-backend` built from `backend/Dockerfile` | `docker build -t studytime-verify-backend backend` |
| PostgreSQL | **16** (`postgres:16`, digest `sha256:f9a7b9eb…`), database `studytime` | disposable container on a private bridge network |
| Node / npm | **v20.20.1 / 10.8.2** (matches CI's Node 20) | host |
| pytest | 8.3.3 (pinned in `backend/requirements.txt`) | container |
| pytest-cov / coverage | 7.1.0 / 7.17.2 — **installed ephemeral in the container** (absent from `requirements.txt`) | `pip install -q pytest-cov` |
| ruff | **0.17.4** (latest at run time) — installed ephemeral; also tested 0.14.0 and 0.6.9 for version sensitivity | `pip install -q ruff` |
| Other backend deps | exactly `backend/requirements.txt` (fastapi 0.115.0, sqlalchemy 2.0.35, psycopg2-binary 2.9.9, …) | image build |

Environment variables used for every backend command (same shape as `.github/workflows/ci.yml`):

```
DATABASE_URL=postgresql://studytime:studytime@studytime-verify-pg:5432/studytime
SECRET_KEY=verify-secret-key-not-for-production
GEMINI_API_KEY=fake-key-tests-are-mocked
CELERY_TASK_ALWAYS_EAGER=true
UPLOAD_DIR=/tmp/uploads
REDIS_URL=redis://localhost:6379/0
```

Schema created before tests, from `backend/` inside the container:

```
alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> eec4795a0846, initial schema
INFO  [alembic.runtime.migration] Running upgrade eec4795a0846 -> bb2950df8057, add created_at and storage_path to documents
```

`psql \dt` confirmed: `alembic_version, documents, flashcards, notes, practice_tests, review_logs, summaries, test_questions, users`.

Preflight limitations:

- **No `.env` and no `.env.example` at repo root**, so `docker compose` (which reads `.env` via
  `env_file`) could not be used. The direct `docker build`/`docker run` path was used instead.
  This is a reproducibility gap for anyone following README "Run it" step 2 (README says
  `cp .env.example .env`, but `.env.example` does not exist in this checkout).
- `frontend/node_modules` was absent, so `npm ci` was required (see G4).
- No host backend dependency install was attempted (Python 3.14 incompatible with the pinned
  `psycopg2-binary==2.9.9`).

---

## 3. Gate results

### G1 — All unit tests pass — **FAIL**

Command (working directory `/app`, image built from `backend/`):

```
python -m pytest -q
```

Exit code: **1**

Output (tail):

```
................F....................................................... [ 36%]
........................................................................ [ 73%]
.....................................................                    [100%]
...
FAILED tests/test_auth_edge_cases.py::test_me_rejects_signed_token_with_non_numeric_subject
1 failed, 196 passed in 108.92s (0:01:48)
```

Failure body:

```
def test_me_rejects_signed_token_with_non_numeric_subject(account):
    forged = _forge_token({"sub": "not-a-user-id"})
    response = client_without_raise.get("/auth/me", headers=_auth(forged))
>   assert response.status_code == 401
E   assert 500 == 401
tests/test_auth_edge_cases.py:170: AssertionError
```

Warnings: 431 (when warnings are enabled), dominated by `DeprecationWarning: datetime.datetime.utcnow()`
from Python 3.12 and `PytestCollectionWarning` for `TestQuestion` model/schema classes.

Independent confirmation of the tester's claim: **exact match** — 196 passed, 1 failed, 0 skipped.

### G2 — Backend coverage ≥ 80% — **PASS**

Command:

```
python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=80 -q
```

Exit code: **1** (because of the G1 test failure). Coverage verdict from the tool's own message:

```
Name                                       Stmts   Miss  Cover   Missing
...
app/api/deps.py                               16      0   100%
app/services/progress.py                      43      0   100%
app/workers/tasks.py                          87      0   100%
------------------------------------------------------------------------
TOTAL                                        801      0   100%
Required test coverage of 80% reached. Total coverage: 100.00%
1 failed, 196 passed, 431 warnings in 128.65s (0:02:08)
```

To avoid attributing the pytest exit code to coverage, the threshold was re-checked in isolation
against the same `.coverage` data:

```
python -m coverage report --fail-under=80
TOTAL  801  0  100%
COVFAILUNDER_EXIT=0
```

**PASS** on the stated criterion (100.0% ≥ 80.0%). The combined pytest command's exit 1 is the G1
failure, not a coverage shortfall.

Caveats that matter for interpreting "100%":

- Coverage is **line-only** (`--cov-branch` not used). `app/api/deps.py:33` is counted as covered
  even though the line raises `ValueError` for a non-numeric `sub` and returns 500. 100% line
  coverage does not mean all paths are correct.
- Tests run in-process with `CELERY_TASK_ALWAYS_EAGER=true`; no real Celery worker/broker process
  is exercised. Redis is never contacted.
- The only backend module with a non-trivial uncovered *branch* is `app/services/progress.py:147`:
  the `datetime.strptime(d, "%Y-%m-%d")` branch is unreachable on PostgreSQL (dates come back as
  `datetime.date`), so the string-normalization path is never executed by this suite.
- Coverage tooling is not a project dependency and CI does not measure coverage (`ci.yml:76` runs
  bare `pytest`), so this gate cannot be reproduced from `requirements.txt` alone.

### G3 — Ruff linting passes without errors — **FAIL**

Command (working directory `/app`):

```
python -m ruff check .
```

ruff version: **0.17.4**. Exit code: **1**.

```
RUF100 [*] Unused `noqa` directive (non-enabled: `DTZ007`)
   --> app/services/progress.py:147:55
    |
145 |         d
146 |         if isinstance(d, date)
147 |         else datetime.strptime(d, "%Y-%m-%d").date()  # noqa: DTZ007
    |                                                       ^^^^^^^^^^^^^^
148 |         for d in review_dates
149 |     }
help: Remove unused `noqa` directive
    |
Found 1 error.
[*] 1 fixable with `--fix`.
```

This confirms the flagged concern: `app/services/progress.py:147` reports `RUF100` under ruff 0.17.4.

**Mode artifact that must not be reported as a product defect.** The first container run also
reported 64 `EXE002` ("file is executable but no shebang") findings, one per Python file, because
Docker's `COPY` from a Windows host assigns mode 0755 to every copied file. The git index records
**all 65 tracked backend files as mode `100644`** (`git ls-files -s backend` → 65 × `100644`,
`core.fileMode=false`). After normalizing modes to 0644 inside the throwaway container
(`find /app -type f -exec chmod 644 {} +`), the run produced exactly the 1 `RUF100` error shown
above. A Linux CI checkout would see 0644 files and would not report `EXE002`.

**Version sensitivity (root cause: unpinned ruff).** `ci.yml:63` installs `pip install -r requirements.txt ruff`
with no version pin, and `backend/requirements.txt` does not list ruff. Results by version, same tree:

| ruff | Exit | Finding |
|---|---|---|
| 0.17.4 (latest, what CI installs today) | 1 | `RUF100` `app/services/progress.py:147:55` |
| 0.14.0 | 1 | `E402` `tests/conftest.py:29` (`import pytest` after `os.environ["UPLOAD_DIR"] = …`) |
| 0.6.9 | 1 | `E402` `tests/conftest.py:29` (same) |

So the lint gate **fails on every version tested**, but for different reasons: newer ruff's default
rule set enables `RUF100` (and `EXE002`) while no longer enabling `E402`; older sets enable `E402`
and not `RUF100`. `ruff.toml` has no explicit `select`, only `ignore = ["FA100"]`, so the effective
ruleset is whatever ruff's changing defaults are. Because `# noqa: DTZ007` suppresses a rule that
is not enabled, `RUF100` is a legitimate finding, not a false positive.

The `E402` at `tests/conftest.py:29` is intentional behavior (the env var must be set before
`app.storage` is imported), but it is still an unannotated lint violation under older defaults.
Both violations are pre-existing at commit `a42db0c`; neither is introduced by the new test files.

### G4 — Frontend lint and build — **PASS**

Scripts taken from `frontend/package.json` (not invented): `lint` = `oxlint`, `build` = `vite build`.

Because `frontend/node_modules` was absent and this agent cannot write under `frontend/`, the
frontend directory was copied verbatim to a temp directory (`%TEMP%\opencode\st2-frontend`) and the
repo's own scripts run there. `package-lock.json` was present and `npm ci` used it, matching CI.

| Command | Exit | Evidence |
|---|---|---|
| `npm ci` | **0** | `added 28 packages in 4s` |
| `npm run lint` (`oxlint`) | **0** | 2 warnings, 0 errors (below) |
| `npm run build` (`vite build`) | **0** | `✓ 46 modules transformed`, `dist/assets/index-C_xXiYM_.js 289.43 kB │ gzip: 89.12 kB`, `✓ built in 410ms` |

Lint output:

```
src/pages/Notes.jsx:22:5: warning react(immutability): Cannot access variable while it is being initialized ... `refreshNotes` is read while its declaration is still being initialized.
src/pages/Notes.jsx:22:5: warning react-hooks(exhaustive-deps): React Hook useEffect has a missing dependency: 'refreshNotes'
```

Tool versions: Node 20.20.1, npm 10.8.2, oxlint 1.83.0, vite 8.3.0, react 19.3.0,
@vitejs/plugin-react 6.1.1.

Assessment of the two warnings (they do not change the gate verdict):

- `react(immutability)` is a false positive for a hoisted `function` declaration
  (`Notes.jsx:25`); the effect callback executes after the declaration is initialized.
- `react-hooks(exhaustive-deps)` is a real (minor) warning. Behavior is still correct because
  `refreshNotes` closes over `documentId`, which is in the dependency array; adding it would
  require memoizing the function. No user-visible defect established.

There is no frontend test suite in the repo, so G4 covers lint/build only, as specified.

### G5 — Tests cover key user stories and acceptance criteria — **FAIL**

Requirement artifact limitation: the repo has **no user-story, acceptance-criteria,
`requirements.md`, or `docs/requirements/` artifact**. Traceability was performed against the two
authoritative README sections, per the skill:

- `README.md` §"What StudyTime Does" (7 numbered capabilities, plus the delete-document paragraph)
- `README.md` §"API Overview" (endpoint table, recounted at run time: **23 endpoints**)

#### Capabilities

| # | Capability (README) | Test evidence | Status |
|---|---|---|---|
| 1 | Upload a PDF; text extracted in the background | `tests/test_documents.py::test_upload_success` (201, status floored to `pending`), `tests/test_extraction.py::test_upload_triggers_extraction_end_to_end` (eager task → `extracted`), `test_extract_no_text_found`, `extraction_failed` cases at `tests/test_extraction.py:131-162` | COVERED |
| 2 | Summarize at three difficulty levels | `tests/test_summary.py` parametrized over `DifficultyLevel` (3), `test_generate_summary_uses_different_instructions_per_level`; HTTP: `tests/test_documents_edge_cases.py::test_generate_summaries_starts_and_persists_generation` asserts 3 persisted rows | COVERED |
| 3 | Generate flashcards, or write your own | `tests/test_flashcard_generation.py` (incl. `test_generate_flashcards_task_replaces_only_ai_generated_cards`), `tests/test_document_flashcards.py::test_create_manual_flashcard_returns_created_card` | COVERED |
| 4 | Review due cards with SM-2; each grade reschedules | `tests/test_sm2.py`, `tests/test_sm2_edge_cases.py` (pure-function boundaries incl. ease floor), `tests/test_flashcards.py`, `tests/test_flashcards_edge_cases.py` (`repetitions`/`interval_days`/`due_at` transitions, `review_logs` rows) | COVERED |
| 5 | Practice with an AI-generated **multiple-choice** test, scored instantly, retakeable | Generation: `tests/test_practice_test_generation.py::test_trigger_practice_test_generation_starts_task_when_text_is_ready`; scoring: `tests/test_practice_test_taking.py::test_submit_scores_correct_and_incorrect_answers`, `tests/test_practice_test_scoring.py` (all-correct/all-wrong/foreign-id/empty/length limit). **No test submits the same test twice (retake).** **README says "multiple-choice"; implementation is short-answer** (`app/services/practice_test_generation.py:35-50`, `frontend/src/pages/PracticeTest.jsx:86` renders "short answer"). | **PARTIAL** |
| 6 | Take notes on any document | `tests/test_notes.py` — create/list/update/delete + ownership 404s | COVERED |
| 7 | Progress dashboard (7 metrics incl. 7-day accuracy and streak) | `tests/test_progress.py` (all metrics, other-user isolation, streak), `tests/test_progress_edge_cases.py` (zero/None accuracy serialization) | COVERED |
| 8 | Delete a document and everything generated from it (paragraph after the list) | `tests/test_delete_document.py::test_delete_document_removes_every_related_row` asserts 7 tables return to zero; file-on-disk removal; missing-file tolerance | COVERED |

Capability count: **6 fully covered + 1 partial = 6/7**, plus the extra delete behavior covered.

#### Endpoints (23 recounted from README §API Overview, all confirmed present in `app/api/*.py`)

| # | Endpoint | HTTP-level test evidence | Status |
|---|---|---|---|
| 1 | `POST /auth/signup` | `test_auth.py::test_signup_success`; `test_auth_edge_cases.py::test_signup_rejects_invalid_email` | COVERED |
| 2 | `POST /auth/login` | `test_auth.py::test_login_success`, `test_login_wrong_password_rejected` | COVERED |
| 3 | `GET /auth/me` | `test_auth.py::test_me_returns_current_user`; 5 rejection cases in `test_auth_edge_cases.py` | COVERED |
| 4 | `POST /documents` | `test_documents.py::test_upload_success`, `test_upload_rejects_non_pdf`, `test_upload_rejects_empty_file`; oversize `test_documents_edge_cases.py::test_upload_rejects_file_larger_than_the_limit` | COVERED |
| 5 | `GET /documents` | `test_documents.py::test_list_documents_only_returns_own` | COVERED |
| 6 | `GET /documents/{id}` | `test_documents.py::test_get_document_returns_own_document`, `..._404s_for_other_users_document` | COVERED |
| 7 | `DELETE /documents/{id}` | `test_delete_document.py::test_delete_document_removes_every_related_row` | COVERED |
| 8 | `POST /documents/{id}/generate-summaries` | `test_documents_edge_cases.py::test_generate_summaries_starts_and_persists_generation` (+ auth/404/400 cases) | COVERED |
| 9 | `GET /documents/{id}/summaries` | `test_documents_edge_cases.py::test_generate_summaries_starts_and_persists_generation` (asserts 3 rows) + two ownership 404 tests | COVERED |
| 10 | `GET /documents/{id}/flashcards` | `test_document_flashcards.py::test_list_flashcards_returns_cards_for_document` | COVERED |
| 11 | `POST /documents/{id}/flashcards` | `test_document_flashcards.py::test_create_manual_flashcard_returns_created_card` | COVERED |
| 12 | `POST /documents/{id}/generate-flashcards` | `test_documents_edge_cases.py::test_generate_flashcards_starts_and_persists_generation`; `test_flashcard_generation.py::test_trigger_flashcard_generation_starts_task_when_text_is_ready` | COVERED |
| 13 | `GET /flashcards/due` | `test_flashcards.py::test_due_flashcards_includes_overdue_card`, `excludes_future_card`, `excludes_other_users_cards` | COVERED |
| 14 | `POST /flashcards/{id}/review` | `test_flashcards.py::test_submit_review_updates_scheduling_state`, `test_submit_review_records_a_review_log`, `test_submit_review_rejects_out_of_range_grade` | COVERED |
| 15 | `POST /documents/{id}/generate-practice-test` | `test_practice_test_generation.py::test_trigger_practice_test_generation_starts_task_when_text_is_ready` | COVERED |
| 16 | `GET /documents/{id}/practice-tests` | `test_practice_test_generation.py::test_trigger_practice_test_generation_starts_task_when_text_is_ready` (line 384), `test_list_practice_tests_requires_auth` | COVERED |
| 17 | `GET /practice-tests/{id}` | `test_practice_test_taking.py::test_get_practice_test_returns_questions_without_answers` | COVERED |
| 18 | `POST /practice-tests/{id}/submit` | `test_practice_test_taking.py::test_submit_scores_correct_and_incorrect_answers`, `test_practice_test_scoring.py` (6 tests) | COVERED |
| 19 | `GET /documents/{id}/notes` | `test_notes.py::test_create_and_list_note` | COVERED |
| 20 | `POST /documents/{id}/notes` | `test_notes.py::test_create_and_list_note` | COVERED |
| 21 | `PUT /notes/{id}` | `test_notes.py::test_update_note` | COVERED |
| 22 | `DELETE /notes/{id}` | `test_notes.py::test_delete_note` | COVERED |
| 23 | `GET /progress` | `test_progress.py::test_get_progress_returns_stats_for_current_user`; `test_progress_edge_cases.py::test_get_progress_returns_zeros_and_null_accuracy_for_new_user` | COVERED |

Endpoint count: **23/23 COVERED at the HTTP level**.

Skill "known gaps" re-checked against the current tree:

| Known gap | Now? |
|---|---|
| `POST /documents/{id}/generate-summaries` and `GET …/summaries` have no HTTP tests | **Closed** — `test_documents_edge_cases.py:250-304` |
| `MAX_UPLOAD_BYTES` rejection untested | **Closed** — `test_documents_edge_cases.py:126` |
| `AUTO_GENERATE_*` flags untested | **Closed** — `test_extraction_autogenerate.py` (3 flags, no-text case) |
| `GenerationError` propagation in `app/workers/tasks.py` untested | **Still open** — `GenerationError` is only raised/tested in `app/services/generation.py` (`tests/test_generation.py`); no test makes `generate_summaries` / `generate_flashcards_task` / `generate_practice_test_task` raise and verifies rollback/partial-row behavior |
| Expired / wrong-secret JWT, deleted-user token untested | **Closed** — `test_auth_edge_cases.py:120-151` |

**Verdict rationale.** Every documented endpoint has HTTP-level evidence, and the test suite is
substantial and behavior-oriented. G5 is nevertheless **FAIL** because the pass criterion is
7/7 documented capabilities: capability 5 is only partially evidenced — the README promises a
multiple-choice test while the product (backend prompt/schema and the React page) implements
short-answer, and "tests can be retaken freely" is asserted nowhere in the backend suite. These
are requirement-conformance gaps, not endpoint gaps; they are recorded as V-03.

---

## 4. Failures and recommended fixes

All recommendations below are **NOT APPLIED**. This agent is read-only on application and test
code; the caller also explicitly instructed diagnose-only.

```
V-01 [Blocker] backend/app/api/deps.py:33
Symptom:  GET /auth/me returns 500 for a validly signed JWT whose "sub" is not numeric.
Expected: 401 "Could not validate credentials" (same as any other invalid token).
Actual:   500 Internal Server Error; pytest fails 500 != 401.
Cause:    `user = db.get(User, int(subject))` — int() raises ValueError outside the
          401 guard. Only decode_access_token()'s None is handled (deps.py:29-31).
Fix:      Wrap the coercion and treat failure as invalid credentials, e.g.
            try:
                user_id = int(subject)
            except (TypeError, ValueError):
                raise credentials_exception
            user = db.get(User, user_id)
          or perform the integer validation inside decode_access_token() so every caller
          inherits it.
Test:     tests/test_auth_edge_cases.py::test_me_rejects_signed_token_with_non_numeric_subject
          (already exists and is currently red — do not weaken it).
Approval: not requested; caller instructed diagnose-only. Owner: build.
```

```
V-02 [Blocker] Gate G3 — backend/ruff.toml + .github/workflows/ci.yml:63
Symptom:  `ruff check .` exits 1 under the currently installed ruff (0.17.4) and also under
          0.14.0 and 0.6.9 (different rule each time).
Cause:    (a) `app/services/progress.py:147` carries `# noqa: DTZ007` while DTZ007 is not
              enabled (ruff.toml has no `select`), so newer default rule sets report RUF100.
          (b) `tests/conftest.py:29` imports pytest after setting UPLOAD_DIR; older default
              rule sets report E402.
          (c) CI installs an unpinned `ruff`, and ruff's default rule set has changed between
              0.6.9, 0.14.0 and 0.17.4 — the lint gate is time-dependent.
Fix:      Pin the linter (e.g. `ruff==0.17.4` in requirements.txt or a requirements-dev.txt,
          installed by ci.yml), add an explicit `select = [...]` to backend/ruff.toml so the
          result does not depend on ruff defaults, delete the unused `# noqa: DTZ007`, and
          either annotate `tests/conftest.py:29` with `# noqa: E402` (documenting the deliberate
          ordering) or restructure via `importlib.import_module("pytest")`.
Test:     `python -m ruff check .` from backend/ must exit 0 on the pinned version.
Approval: not requested; diagnose-only. Owner: build.
```

```
V-03 [Medium] README.md:24 / app/services/practice_test_generation.py:35-50
Symptom:  README capability 5 says "AI-generated multiple-choice test"; the implementation
          generates short-answer questions (no options/distractors), and the UI labels it
          "short answer" (frontend/src/pages/PracticeTest.jsx:86). No backend test submits the
          same practice test twice, so "tests can be retaken freely" is unasserted.
Cause:    README text is stale relative to the shipped short-answer feature; retake is a
          frontend-only state reset (PracticeTest.jsx handleRetake), untested.
Fix:      Correct README to "short-answer" (or implement choices if multiple-choice is the
          intended requirement), and add a test that submits the same practice_test_id twice
          and asserts both submissions return 200 with independent scores and no persisted
          attempt rows.
Test:     new test, e.g. tests/test_practice_test_taking.py::test_practice_test_can_be_retaken.
Approval: not requested; diagnose-only. Owner: build (+ README edit by the team).
```

```
V-04 [Medium] backend/app/workers/tasks.py:89-126, 129-170, 173-228
Symptom:  No test covers a GenerationError raised inside a generation task.
Cause:    The tasks delete existing rows before calling Gemini, then commit. If generation
          raises, Session.close() rolls the transaction back — correct behavior, but unpinned
          by any test, so a future refactor could commit the delete and lose a user's
          summaries/flashcards/test.
Fix:      Add tests that patch app.workers.tasks.generate_summary (and generate_flashcards /
          generate_practice_test_questions) to raise GenerationError, call the task directly,
          and assert pytest.raises(GenerationError) plus the pre-existing rows still present.
Test:     new tests in tests/test_summary.py / test_flashcard_generation.py / test_practice_test_generation.py.
Approval: not requested; diagnose-only. Owner: @studytime-tester.
```

```
V-05 [Medium] backend/tests/test_progress.py:107, backend/tests/test_progress_edge_cases.py:24
Symptom:  Non-determinism around UTC midnight: `NOW = datetime.utcnow()` is evaluated at module
          import, while compute_progress_stats() evaluates "today" at call time. A run that
          crosses midnight between import and test_reviews_today_excludes_earlier_days can make
          a review created "now" fall outside "today" and fail the assertion.
Cause:    Wall-clock constant captured at import; no time injection in app/services/progress.py:41.
Fix:      Freeze time per test (monkeypatch datetime in app.services.progress, or pass now/today
          into compute_progress_stats) instead of a module-level constant. Same for the
          deprecation issue: `datetime.utcnow()` is deprecated in 3.12 (431 warnings this run)
          and should move to timezone-aware UTC or a DB-side `func.now()`.
Test:     existing tests must stay green when run with a patched clock at 23:59:59 UTC.
Approval: not requested; diagnose-only. Owner: @studytime-tester / build.
```

```
V-06 [Low] backend/requirements.txt (16 lines) + .github/workflows/ci.yml:63, 76
Symptom:  `pytest-cov` and `ruff` are not declared; CI installs ruff unpinned and never measures
          coverage. Reproducing G2 requires an undeclared `pip install pytest-cov`.
Confirmed: requirements.txt lists 16 packages, none of them ruff or pytest-cov.
Fix:      Add pinned `ruff` and `pytest-cov` (or a separate requirements-dev.txt), and add a CI
          step: `pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80`.
Approval: not requested; diagnose-only. Owner: build.
```

```
V-07 [Low] backend/ (whole app)
Symptom:  100% line coverage masks path gaps. deps.py:33 is "covered" while returning 500.
Cause:    --cov-branch is not enabled anywhere.
Fix:      Enable branch coverage in the CI step above; expect the progress.py:147 string branch
          and deps.py error path to surface.
Approval: not requested; diagnose-only. Owner: build.
```

```
V-08 [Low] backend/tests/ (suite-wide)
Symptom:  Rows accumulate across runs — the PostgreSQL instance held 3 users and 0 documents
          after the full suite. test_auth.py signup/login tests create users with no cleanup.
Cause:    No session-level table truncation or per-test cleanup in conftest.py; cleanup is
          implemented ad hoc in newer files only. Harmless today (all queries are user-scoped),
          but the DB is never returned to a known state.
Fix:      Add an autouse session/function fixture that deletes rows in FK order (or TRUNCATE ...
          CASCADE) after each test module; keep UPLOAD_DIR isolation as is.
Approval: not requested; diagnose-only. Owner: @studytime-tester.
```

```
V-09 [Low] backend/tests/test_*_edge_cases.py
Symptom:  ~60 lines of identical `unique_email` / `_create_user_and_token` / `_cleanup_user` /
          fixture boilerplate duplicated across 7 new test files.
Cause:    New files were written independently rather than sharing conftest fixtures.
Fix:      Move the helpers into tests/conftest.py as fixtures; keep file-local factories only
          for domain-specific rows.
Approval: not requested; diagnose-only. Owner: @studytime-tester.
```

```
V-10 [Low] frontend/src/pages/Notes.jsx:21-34
Symptom:  oxlint warns about `refreshNotes` in the useEffect dependency array (exhaustive-deps).
Cause:    Function declared in component scope; not memoized.
Fix:      Move `refreshNotes` inside the effect (or wrap in useCallback and list it), optionally
          returning a cancellation guard. Warning only; lint/build pass.
Approval: not requested; diagnose-only. Owner: build.
```

---

## 5. Code-quality observations

- **Ownership isolation:** every resource is scoped through the owning user. Documents check
  `document.user_id` at each handler (`app/api/documents.py:185, 220, 252, 286, 315, 345, 384`);
  flashcards and practice tests join through `Document.user_id`
  (`app/api/flashcards.py:33-35, 53-56`; `app/api/practice_tests.py:33-38`); notes go through
  `_get_owned_document` / `_get_owned_note` (`app/api/notes.py:15-46`). 404-not-403 is applied
  consistently. Tests assert the cross-user 404 for each area.
- **Auth defect:** `app/api/deps.py:33` is the one unguarded trust boundary (V-01). It is also the
  only place an application `500` was observed in this run.
- **Exception handling:** `app/services/generation.py` catches broad `Exception` but re-raises as
  a typed `GenerationError` with context — acceptable. `app/workers/tasks.py:46` catches only
  `PdfReadError`, `FileNotFoundError`, `OSError` — appropriately narrow.
- **Secrets:** no credentials in source or tests; tests use obvious placeholders and a separate
  fake signing secret. `.env` is absent and gitignored.
- **Lint debt:** `# noqa` directives are used with rule codes that are not enabled (`DTZ003`,
  `DTZ007`), which is precisely what `RUF100` flags; `app/api/flashcards.py:38`,
  `app/services/sm2.py:56`, `app/services/progress.py:41` all carry `# noqa: DTZ003` against a
  disabled rule. Fixing the ruff configuration and the noqa set together avoids a whack-a-mole
  cycle.
- **Deprecation:** widespread `datetime.utcnow()` (naive) usage in app and tests produces 431
  warnings on Python 3.12 and will break on a future interpreter. Not a gate failure today.

## 6. Test-suite quality

- **Independence:** good — each test creates its own user/document via UUID emails and asserts
  through its own token; no test depends on another test's rows or ordering. Cleanup fixtures run
  after `yield`. Residual: 3 users left behind per run (V-08).
- **Determinism:** mostly good — SM-2 tests inject a fixed `FIXED_NOW`; e2e tests use relative
  times. Weak spots: module-level `datetime.utcnow()` in the two progress test files (V-05), and
  `test_second_review_builds_on_the_first_and_persists` asserts `[log.grade for log in logs] ==
  [2, 2]` without an `ORDER BY` (harmless because both grades are equal, but it would not catch an
  ordering regression).
- **Over-mocking:** acceptable. Gemini is mocked at `generate_structured` / the SDK client
  boundary, and one test asserts that the source text reaches the prompt and that the three
  difficulty prompts differ — these are behavioral contracts, not implementation trivia. Celery
  tasks are mocked only when testing orchestration (`test_extraction_autogenerate.py`), where the
  task object is the boundary. No test mocks the function under test.
- **Assertion strength:** generally strong (status + body fields + DB rows). The status-only
  assertions in auth/404 cases are appropriate; the summary test asserts only the set of contents
  (`{"a generated summary"}`), so it would not catch wrong `difficulty_level` values on the three
  rows — a small gap.
- **Missing error-path coverage:** generation-task failure/rollback (V-04); retake (V-03);
  `ReviewLog` ordering. Branch coverage is not measured (V-07).

## 7. Approval log

| Time | Request | Decision | Notes |
|---|---|---|---|
| 2026-11-10 16:2x | R-01: write report to `docs/verification/verification-report.md` instead of the requested `docs/verification-report.md` (outside agent write scope) | **granted** | Caller selected the allowed path. |
| — | Application fixes V-01…V-10 | **not requested** | Caller instructed diagnose-only ("do not apply"); this agent has no write access to product or test code. |

## 8. Environment / reproducibility

Re-run recipe (from repo root), exactly as executed:

```powershell
docker network create studytime-verify-net
docker run -d --name studytime-verify-pg --network studytime-verify-net `
  -e POSTGRES_USER=studytime -e POSTGRES_PASSWORD=studytime -e POSTGRES_DB=studytime postgres:16
docker build -t studytime-verify-backend backend
docker run -d --name studytime-verify-runner --network studytime-verify-net `
  -e DATABASE_URL=postgresql://studytime:studytime@studytime-verify-pg:5432/studytime `
  -e SECRET_KEY=verify-secret-key-not-for-production `
  -e GEMINI_API_KEY=fake-key-tests-are-mocked `
  -e CELERY_TASK_ALWAYS_EAGER=true -e UPLOAD_DIR=/tmp/uploads `
  -e REDIS_URL=redis://localhost:6379/0 studytime-verify-backend sleep infinity

docker exec studytime-verify-runner alembic upgrade head
docker exec studytime-verify-runner python -m pytest -q                      # G1
docker exec studytime-verify-runner sh -lc "pip install -q pytest-cov; python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=80 -q"   # G2
docker exec studytime-verify-runner python -m coverage report --fail-under=80 # G2, isolated threshold
docker exec studytime-verify-runner sh -lc "pip install -q ruff; find /app -type f -exec chmod 644 {} +; python -m ruff check ."   # G3 (chmod replicates git 100644 modes)
```

Frontend (copy `frontend/` to a temp dir first, because `frontend/node_modules` is absent and
`frontend/` is outside this agent's write scope):

```powershell
npm ci; npm run lint; npm run build
```

Cleanup performed after evidence collection: containers `studytime-verify-runner` and
`studytime-verify-pg` removed with `docker rm -f -v`; image `studytime-verify-backend` removed;
network `studytime-verify-net` removed; temp frontend copy deleted. No coverage artifacts were
written to the host — `.coverage`, `.pytest_cache`, `.ruff_cache` in `backend/` were pre-existing
and gitignored (`.ruff_cache` self-ignores via its own `.gitignore`, which contains `*`) and were
not touched. The existing `backend/.ruff_cache/0.17.4` directory shows a prior host-side ruff
0.17.4 run, consistent with the tester's report.

## 9. Residual risks and next actions

1. **Fix V-01** (`app/api/deps.py:33`) and keep the existing red test as the regression proof —
   owner: build. Until then G1 is red and CI cannot pass.
2. **Pin and configure the linter, then clear both lint findings** (V-02/V-06) — owner: build.
   Assumption to confirm: the team's intended Python floor is 3.9 per `ruff.toml`, but runtime is
   3.12; the `target-version` comment is stale and should be revisited at the same time.
3. **Decide the practice-test requirement** — multiple-choice or short-answer — update README and
   add a retake test (V-03) — owner: team + build.
4. **Close the generation-error gap and the midnight flakiness** (V-04/V-05) — owner:
   `@studytime-tester`.
5. **Add coverage (branch) to CI** so G2 is enforced where it can be reproduced (V-06/V-07).
6. Documentation gap: `.env.example` is referenced by README but absent from the repo; anyone
   following the README cannot create `.env`. Recommend adding it (owner: team). This is not one
   of the five gates but blocks the documented setup path.
