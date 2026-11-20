"""Shared pytest setup for the whole test suite.

pytest loads conftest.py files before it collects (imports) any test
module in the same directory - that ordering is what makes the env var
below actually work. app/storage.py reads UPLOAD_DIR from the
environment exactly once, at import time, to build its UPLOAD_DIR
constant. If this were set inside a fixture function instead of here
at module level, it would run too late: by the time any fixture
actually executes, every test file (and therefore app.storage, via
`from app.main import app`) has typically already been imported during
collection, so the constant would already be frozen to the real
"uploads" default.
"""

import os
import shutil
import tempfile
import pytest 

# Every test-created file (test_documents.py, test_extraction.py,
# test_notes.py, test_delete_document.py all write real files to
# UPLOAD_DIR) now lands in an isolated temp folder instead of the same
# backend/uploads/ directory real user uploads live in. No test needs
# its own file-cleanup logic anymore - nothing here can leak into real
# data, and the whole temp folder just gets deleted once, below, after
# the entire suite finishes.
_TEST_UPLOAD_DIR = tempfile.mkdtemp(prefix="studytime-test-uploads-")
os.environ["UPLOAD_DIR"] = _TEST_UPLOAD_DIR


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_upload_dir():
    """Deletes the whole temp folder once, after every test in the
    session has run. autouse=True means this applies automatically -
    no test file needs to request it.
    """
    yield
    shutil.rmtree(_TEST_UPLOAD_DIR, ignore_errors=True)