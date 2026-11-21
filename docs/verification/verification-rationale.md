# Verification Agents and Skills: Rationale

**Project:** StudyTime2 — CS 3704 Project 2  
**Branch:** `verification-agents`  
**Verification date:** November 10, 2026  
**Evidence:** [Verification report](verification-report.md)

## Quality gates

The verification workflow separates test execution from the decision about whether StudyTime2 satisfies its quality goals. Gates use measurable results; a failed or unavailable check must be reported rather than assumed to pass. The environment preflight (G0) checks prerequisites before the five evaluated gates.

| Gate | What it checks | Pass criteria | If it fails | Why we added it |
|---|---|---|---|---|
| **G0 — Environment** | Python, PostgreSQL/schema, dependencies, and frontend tooling | Required test environment is usable | Report missing prerequisites; mark checks that cannot run **NOT RUN** | Prevent misleading results caused by setup problems |
| **G1 — Tests** | Backend pytest suite, including error paths and boundary cases | `python -m pytest -q` exits **0**, with no failures or errors | Reproduce and classify the failure; preserve valid failing tests and recommend fixes | Catch functional defects and regressions |
| **G2 — Coverage** | Backend `app/` line coverage | At least **80%** (`--cov-fail-under=80`) | Identify uncovered code and add meaningful tests; never lower the threshold | Reveal insufficiently tested application code |
| **G3 — Ruff** | Backend Python linting | `python -m ruff check .` exits **0**, with no violations | Report rule IDs and file locations; propose corrections | Enforce code-quality conventions and maintainability |
| **G4 — Frontend** | React frontend lint and production build | `npm run lint` and `npm run build` both exit **0** | Record errors and warnings; recommend changes | Catch frontend quality and build problems |
| **G5 — Requirements** | Test evidence for documented features and API routes | **7/7** README capabilities supported/evidenced, and every documented endpoint has an HTTP-level test | Identify untested requirements and documentation/implementation mismatches | Ensure tests demonstrate required behavior, not just executed lines |

## Skills

### `studytime-test` — `.opencode/skills/studytime-test/SKILL.md`

**Purpose and when to run:** Used by `@studytime-tester` to add unit/integration tests, investigate a defect, or check a fix. It covers authentication, PDF upload and extraction, flashcards, SM-2 scheduling, practice-test generation/scoring, progress tracking, and background-task errors.

**Workflow:** Check the environment and PostgreSQL schema; inventory missing tests; write isolated `pytest` cases under `backend/tests/` using unique users, mocked Gemini calls, and eager Celery; run targeted tests before the full suite; measure backend coverage; run Ruff; and triage failures without weakening existing tests. It provides evidence for **G1–G3** and the test mapping used by **G5**. Tests must not access live Gemini services or real user data.

**Output:** New or revised backend test files and a result summary with commands, exit codes, passing/failing counts, coverage, defects, and approval requests. StudyTime2 needs this skill to systematically test its API, database-backed behavior, and edge cases rather than relying on happy-path tests.

### `studytime-verify` — `.opencode/skills/studytime-verify/SKILL.md`

**Purpose and when to run:** Used by `@studytime-reviewer` after tests are generated, before a milestone, or when a quality check needs investigation.

**Workflow:** Perform environment checks, **independently rerun** the backend tests, coverage, Ruff, and frontend lint/build commands; map the seven README capabilities and listed API routes to actual tests; audit test independence, determinism, mocking, and ownership checks; then classify each gate **PASS**, **FAIL**, or **NOT RUN** with command evidence. It must not turn failed gates into passes or change the code under review.

**Output:** `docs/verification/verification-report.md`, including the gate-by-gate verdict, evidence, severity-ranked findings, recommendations, approval log, and residual risks. This provides a reproducible review separate from the agent that wrote the tests.

## Agents

### `@studytime-tester` — `.opencode/agents/studytime-tester.md`

**Role:** A **subagent** that generates and executes backend tests, measures coverage, and diagnoses failed cases. It loads the `studytime-test` skill first.

**Permissions and rationale:** It can read/search project files and **edit `backend/tests/**` without approval**, allowing it to improve the test suite. The declared permissions require approval for edits to **`backend/app/**`** and **`frontend/**`**; **`backend/alembic/**` is denied** in its permission block. Its instructions also prohibit editing course template files or committing/pushing. Normal test/lint/build commands are permitted, while Docker lifecycle and dependency installations require approval. This limits autonomous changes to tests and protects production code and project configuration.

### `@studytime-reviewer` — `.opencode/agents/studytime-reviewer.md`

**Role:** An independent, evidence-based **subagent** that runs the verification gates, reviews test quality and requirement conformance, and issues a verdict. It loads `studytime-verify` first rather than accepting the tester's summary as proof.

**Permissions and rationale:** It can read/search source and run test, Ruff, lint, and build commands, but its **only writable directory is `docs/verification/**`**. It cannot edit application code, tests, migrations, or course template files, and cannot commit or push. Other shell commands generally require approval. Read-only verification reduces the risk of an agent concealing defects by changing the code it is evaluating.

**Design distinction:** The tester creates evidence; the reviewer evaluates that evidence independently. Both agents have `task: deny` and must request appropriate approval rather than silently exceeding their roles. **Configuration detail to review:** the tester's prose says migration edits require approval, but its actual `backend/alembic/**` permission is `deny`. The stricter permission applies; the wording should be aligned if the team revises the agent later.

## Results and changes

The reviewer executed the gates locally on November 10, 2026. It used temporary Docker containers with **Python 3.12** and **PostgreSQL 16** for the backend and the repository's frontend commands. The overall verdict was **FAIL: two gates passed and three failed**. The reviewer did not change application or test code during its run.

| Gate | Verified outcome |
|---|---|
| **G1 — FAIL** | **196 passed, 1 failed, 0 skipped**. A signed JWT with a nonnumeric subject caused `/auth/me` to return HTTP **500** instead of **401** (`backend/app/api/deps.py:33`). |
| **G2 — PASS** | **100% backend line coverage** across 801 statements, above the 80% threshold. Branch coverage was **not** measured; line coverage did not prevent the authentication defect. |
| **G3 — FAIL** | Ruff **0.17.4** reported an unused `# noqa: DTZ007` directive (`RUF100`) in `backend/app/services/progress.py:147`. Different unpinned Ruff versions produced different findings. |
| **G4 — PASS** | Frontend install, lint, and build all exited **0**; lint produced **two nonblocking warnings** in `Notes.jsx`. |
| **G5 — FAIL** | **23/23** documented endpoints had HTTP-level test evidence, but only **6/7** README capabilities were fully supported/evidenced. The README promises multiple-choice practice tests although the implementation uses short answers, and retaking a test lacked coverage. |

The previous tester run added **seven backend test files** addressing authentication, documents, automatic extraction/generation, flashcards, SM-2, practice-test scoring, and progress edge cases. The reviewer independently reproduced the failing authentication test and checked the quality gates. A report-path question also arose: the requested `docs/verification-report.md` was outside the reviewer's write scope, so, **with approval**, the output was saved to `docs/verification/verification-report.md`.

**Recommended changes (not yet applied):** Handle invalid JWT subjects as 401 responses without weakening the regression test; pin/configure Ruff and clear lint violations; reconcile practice-test requirements with the implementation and test retakes; add generation-error rollback tests; and add branch-coverage checks to CI. Additional issues include midnight-sensitive progress tests, a missing `.env.example`, and undeclared test/coverage tools. These findings remain recommendations, not completed fixes.

**Assessment:** Compared with Task 3's prompt-only test generation, this agentic process inspected StudyTime2, produced executable tests, reran tooling, and documented real failures. Human review was still needed to approve permissions, interpret coverage correctly, and decide which recommended fixes to implement.
