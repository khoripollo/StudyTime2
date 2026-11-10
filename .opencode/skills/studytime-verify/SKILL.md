---
name: studytime-verify
description: "Run StudyTime2 quality gates (pytest, 80% backend coverage, Ruff, frontend lint and build, requirement traceability) and produce docs/verification/verification-report.md with pass/fail status and recommended fixes. Use before submission, on a failing check, or when auditing test results and coverage."
license: CC-BY-4.0
---

# StudyTime2 Verify Skill

Procedural guide for the `@studytime-reviewer` agent. It defines the quality gates,
the exact commands, the evidence rules, and the report format used to verify
StudyTime2.

The output is a factual verification report plus a verdict. It is not a grade and
must never be presented as one.

## When to use

- Before packaging coursework for submission.
- After a change, to confirm all gates still pass.
- When `pytest`, coverage, Ruff, or the frontend build fails and the failure needs
  to be explained and triaged.
- When auditing whether tests actually cover the documented requirements.

## Permissions and write scope

| Path or action | Rule |
|----------------|------|
| `docs/verification/**` | write without asking (report and run logs) |
| `backend/app/**`, `backend/tests/**`, `frontend/**`, `backend/alembic/**`, `.github/**`, `backend/requirements.txt`, `.env` | read-only; recommend, never edit |
| `AGENTS.md`, `PHASE.md`, `opencode.json`, other agents and skills | never |
| `git commit`, `git push`, history rewrite | never |
| Running gates (`pytest`, `ruff`, `npm run lint`, `npm run build`) | allowed |
| Dependency installs and Docker lifecycle | request approval first |

Application fixes are recommendations. They are applied by `build`, and only after
the student approves through the `question` tool.

## Quality gates

All commands are relative to the repository root unless stated otherwise. Gates are
independent: a failure in one does not excuse skipping the others.

| ID | Gate | Command | Pass criterion |
|----|------|---------|----------------|
| G0 | Environment | preflight checks below | PostgreSQL reachable, schema present, backend deps importable, `frontend/node_modules` present |
| G1 | Tests pass | `python -m pytest -q` from `backend/` | exit 0, 0 failed, 0 errors |
| G2 | Backend coverage | `python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=80 -q` from `backend/` | total coverage of `app/` >= 80.0 percent |
| G3 | Ruff lint | `python -m ruff check .` from `backend/` | exit 0, 0 violations |
| G4 | Frontend lint and build | `npm ci` then `npm run lint` then `npm run build` from `frontend/` | both commands exit 0 |
| G5 | Requirement traceability | manual mapping, see below | 7/7 documented capabilities and every documented endpoint have test evidence |

### G0 - Environment preflight

```powershell
Test-Path .env
docker info --format "{{.ServerVersion}}"
docker compose version
Test-Path frontend\node_modules
```

Backend environment must match CI (`.github/workflows/ci.yml`):

```
DATABASE_URL=postgresql://studytime:studytime@localhost:5432/studytime
SECRET_KEY=<non-empty>
GEMINI_API_KEY=<non-empty; satisfies import-time reads only>
CELERY_TASK_ALWAYS_EAGER=true
```

The schema must exist before G1; tests never create tables. Run `alembic upgrade
head` first (from `backend/`), or use the container path below.

### Container path (preferred in this repo)

Local Python is 3.13/3.14 while the project targets 3.12, and
`psycopg2-binary==2.9.9` may not install on newer interpreters:

```powershell
# Whole backend gate chain in the Python 3.12 image
docker compose run --rm backend sh -c "alembic upgrade head && python -m pytest -q && python -m ruff check ."

# Coverage gate, installing the missing plugin into the throwaway container
docker compose run --rm backend sh -c "pip install -q pytest-cov && python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=80 -q"
```

`docker compose` requires `.env` to exist. Creating it is a configuration change and
requires approval. If it is absent, report G0 `FAIL` with that prerequisite and mark
G1-G3 `NOT RUN`.

## Software version expectations

| Component | Expected | Evidence source |
|---|---|---|
| Python | 3.12 | `backend/Dockerfile`, CI |
| PostgreSQL | 16 | `Docker-compose.yml`, CI service |
| Node | 20 | CI |
| Ruff config | `backend/ruff.toml`, target `py39` | repo file |
| Frontend lint | `oxlint` via `npm run lint` | `frontend/package.json` |
| Frontend build | `vite build` via `npm run build` | `frontend/package.json` |

Record the actual versions observed. A mismatch is an observation, not automatically
a gate failure, unless it explains a failing command.

## G5 - Requirement traceability

The repository has no formal user-story or acceptance-criteria document. Trace to the
two authoritative sections of `README.md` and record that limitation:

1. **Capabilities** - the seven numbered items in `README.md` section "What StudyTime
   Does": upload and extract, summarize at three levels, generate flashcards, review
   with SM-2, practice test and scoring, notes, progress dashboard. Deleting a
   document is stated in the following paragraph and counts as an eighth behavior to
   verify if present.
2. **Endpoints** - every route listed in `README.md` section "API Overview". Recount
   the table at run time; it currently lists 23 endpoints.

For each row, record the test that provides evidence, or `NO EVIDENCE`. A test that
calls the service directly is acceptable evidence for business logic; endpoint rows
require at least one HTTP-level test.

Known gaps to check explicitly (do not assume they are fixed):
- `POST /documents/{id}/generate-summaries` and `GET /documents/{id}/summaries` have
  no HTTP-level tests.
- `MAX_UPLOAD_BYTES` rejection, `AUTO_GENERATE_*` flags, and `GenerationError`
  propagation in `app/workers/tasks.py` are untested.
- Expired or wrong-secret JWT, and a token whose user was deleted, are untested.

Passing all tests while any documented endpoint has `NO EVIDENCE` is a G5 `FAIL`.
State that explicitly: the suite is green but coverage of the requirement is not.

## Evidence rules

- Every `PASS` needs a command, an exit code, and an output excerpt behind it.
- Round coverage to one decimal and cite the `TOTAL` line.
- Never infer a gate result from a previous run, a tester's summary, or green CI on
  `main`.
- Never mark a gate `PASS` because the failure looks unrelated.
- Anything not executed is `NOT RUN` with the reason. `NOT RUN` is not `PASS`.
- If the tester reported a different result for the same command, report both and
  keep your own execution as the evidence.

## Code and test quality review

Beyond the gates, inspect and report:

**Code quality**
- Ruff violations by rule and file; note whether they are new or pre-existing.
- Dead code, duplicated logic, and functions that mix responsibilities.
- Broad exception handling that hides failures.
- Ownership checks: every query scoped through the owning user.
- Secrets or credentials in source, fixtures, or committed files.

**Test quality**
- Independence: no test relies on another test's rows or on execution order.
- Determinism: wall-clock dependence (`datetime.utcnow`), unseeded randomness,
  ordering assumptions without `ORDER BY`.
- Over-mocking: tests that assert prompt strings or mock the function under test.
- Assertions that cannot fail (asserting only a status code when the contract is the
  response body).
- Missing error-path and boundary coverage for the six required areas.
- Cleanup correctness: rows deleted in foreign-key order; temp uploads isolated.

## Failure behavior

| Situation | Required behavior |
|---|---|
| Any gate fails | Record the command, exit code, and output. Add at least one fix recommendation. Overall verdict `FAIL`. |
| A gate cannot run | Mark `NOT RUN` with the missing prerequisite. Do not substitute a prior result. |
| A test fails and the cause is application code | Keep the evidence, request approval, and do not edit. |
| Approval denied | Mark the recommendation `DEFERRED`, keep the gate `FAIL`, and log the denial. |
| Requirements are undocumented | Trace to README and record the documentation gap as a finding. |
| Tooling is missing (for example `pytest-cov`) | Report the missing tool, install it only in an ephemeral container/venv with approval, and never edit `requirements.txt` without approval. |

## Report template

Write to `docs/verification/verification-report.md`. Create the directory if needed.
Use the current date and time in the heading.

~~~~markdown
# Verification Report - StudyTime2 - <YYYY-MM-DD HH:mm>

Branch: <branch>  |  Commit: <short sha>  |  Reviewer: @studytime-reviewer

## 1. Verdict

**Overall: PASS | FAIL | NOT RUN**

| Gate | Status | Evidence |
|------|--------|----------|
| G0 Environment | PASS/FAIL/NOT RUN | <one line> |
| G1 Tests | ... | <x passed, y failed, z skipped> |
| G2 Coverage | ... | <total>% vs 80% |
| G3 Ruff | ... | <n> violations |
| G4 Frontend | ... | lint exit <n>, build exit <n> |
| G5 Requirements | ... | <capabilities>/7, <endpoints>/<total> |

## 2. Environment

- Python: <version and how it was run (host or container)>
- PostgreSQL: <version, database name>
- Node/npm: <versions>
- Tooling: pytest <version>, coverage <version>, ruff <version>
- Preflight notes: <missing .env, missing node_modules, etc.>

## 3. Gate results

### G1 - Tests
Command: `<command>`
Exit code: `<n>`
Output:
```
<key lines>
```

### G2 - Coverage
Command: `<command>`
Exit code: `<n>`
```
TOTAL <n> <n> <pct>%
```

### G3 - Ruff
Command: `<command>`
Exit code: `<n>`
```
<output or "All checks passed!">
```

### G4 - Frontend
Commands and exit codes: `npm ci` -> <n>, `npm run lint` -> <n>, `npm run build` -> <n>
Notable warnings: <...>

## 4. Coverage detail

| Module | Statements | Missed | Cover |
|--------|-----------|--------|-------|
| app/services/sm2.py | ... | ... | ... |
| ... | | | |

Lowest-value uncovered behavior: <file:line and why it matters>

## 5. Requirement traceability (G5)

### Capabilities (README "What StudyTime Does")
| # | Capability | Evidence | Status |
|---|------------|----------|--------|
| 1 | Upload PDF and extract text | tests/test_documents.py, test_extraction.py | COVERED |
| ... | | | |

### Endpoints (README "API Overview")
| Endpoint | Evidence | Status |
|----------|----------|--------|
| POST /auth/signup | test_auth.py::test_signup_success | COVERED |
| POST /documents/{id}/generate-summaries | - | NO EVIDENCE |
| ... | | |

## 6. Failures and recommended fixes

```
V-01 [Blocker] <path>:<line> - <one-line symptom>
Expected: <...>
Actual:   <...>
Cause:    <root cause>
Fix:      <minimal recommendation>
Test:     <proving test>
Approval: required | not required
```

## 7. Code-quality observations

- <Ruff rule/file, smell, or ownership risk>

## 8. Test-suite quality

- Independence: <finding>
- Determinism: <finding>
- Over-mocking: <finding>
- Missing error-path coverage: <finding>

## 9. Approval log

| Time | Request | Decision | Notes |
|------|---------|----------|-------|
| ... | ... | granted/denied/pending | ... |

## 10. Residual risks and next actions

1. <highest-priority action, with owner: @studytime-tester, build, or student>
2. ...
~~~~

Per-run evidence logs are optional; when asked to keep history, write
`docs/verification/runs/<YYYY-MM-DD>-<area>.md` with the same structure.

## Output contract

Return to the caller:

```
Verification verdict: PASS | FAIL | NOT RUN
Report: docs/verification/verification-report.md
G0 Environment: ...  G1 Tests: ...  G2 Coverage: ...  G3 Ruff: ...  G4 Frontend: ...  G5 Requirements: ...
Top failures:
  V-01 [Blocker] <file:line> - <cause> -> <fix>
Approvals requested: <id> -> <granted|denied|pending>
Not run: <what and why>
```

## Do not

- Mark a gate as passing without running the command in this session.
- Edit application code, tests, migrations, dependency files, or course templates.
- Present the verdict as a grade, or promise that a submission will be accepted.
- Omit a failure because it is inconvenient or looks pre-existing; label it as
  pre-existing instead.
- Rewrite the threshold, the gate definition, or the report format to fit the result.
