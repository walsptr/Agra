"""Repo hygiene (PR 12): no tracked file is hidden by .gitignore, secrets stay
ignored, and the docs kept local for now (AGENTS.md, contexts/, docs/) are
never committed."""
from __future__ import annotations

import shutil
import subprocess

import pytest

from agra.constants import PROJECT_ROOT as REPO_ROOT

REQUIRED_TRACKED = ["LICENSE", "README.md"]
# Not published for now: they live only in the local working copy.
UNPUBLISHED = ["AGENTS.md", "contexts/RULES.md", "docs/index.md"]
SECRETS = ["etc/agra/passwords.yml", "etc/agra/passwords.yml.bak"]


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, check=False)


pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or _git("rev-parse", "--is-inside-work-tree").stdout.strip() != "true",
    reason="needs a git checkout",
)


def test_required_files_are_tracked():
    tracked = set(_git("ls-files", "--", *REQUIRED_TRACKED).stdout.split())
    assert sorted(set(REQUIRED_TRACKED) - tracked) == []


def test_no_tracked_file_is_gitignored():
    # An ignored path that is tracked still works today, but new files next to
    # it are silently left out of commits.
    ignored = _git("ls-files", "--cached", "--ignored", "--exclude-standard").stdout.split()
    assert ignored == []


@pytest.mark.parametrize("path", SECRETS)
def test_secrets_are_gitignored(path):
    assert _git("check-ignore", "--no-index", "-q", path).returncode == 0, f"{path} is not ignored"


@pytest.mark.parametrize("path", UNPUBLISHED)
def test_unpublished_docs_are_ignored_and_untracked(path):
    assert _git("check-ignore", "--no-index", "-q", path).returncode == 0, f"{path} is not ignored"
    assert _git("ls-files", "--", path.split("/")[0]).stdout == "", f"{path} is tracked"
