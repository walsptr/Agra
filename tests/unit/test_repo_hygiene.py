"""Repo hygiene (PR 12): no tracked file is hidden by .gitignore, secrets stay
ignored, and the docs kept local for now (AGENTS.md, contexts/, docs/) are
never committed — nor pointed at by what is published (PR 20)."""
from __future__ import annotations

import ast
import re
import shutil
import subprocess

import pytest

from agra.constants import PROJECT_ROOT as REPO_ROOT

REQUIRED_TRACKED = ["LICENSE", "README.md", "CHANGELOG.md"]
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


# A link or "see DESIGN §4" in something a reader of the published repo sees
# (docs, templates rendered onto hosts, operator files, CLI and playbook
# messages) would point at a file they do not have. Code comments may cite them.
UNPUBLISHED_REF = re.compile(r"(?:^|[\s(\[`'\"])(?:\.{1,2}/)?(?:contexts|docs)/|AGENTS\.md|\b(?:PRD|ARCHITECTURE|DESIGN|RULES|SCHEMA)(?:\.md)?\s*§")
WHOLE_FILE = re.compile(r"(?:\.md|\.j2|^etc/agra/.*|^inventory/.*|^install\.sh)$")


def _python_strings(text: str):
    tree = ast.parse(text)
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)}
    return "\n".join(n.value for n in ast.walk(tree)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings)


def _yaml_without_comments(text: str):
    return "\n".join(re.split(r"\s#\s", line)[0] for line in text.splitlines() if not line.lstrip().startswith("#"))


def _reader_facing(path: str, text: str):
    if WHOLE_FILE.search(path):
        return text
    if path.startswith("agra/") and path.endswith(".py"):
        return _python_strings(text)
    if path.startswith("ansible/") and path.endswith(".yml"):
        return _yaml_without_comments(text)
    return ""


def test_published_files_do_not_point_at_unpublished_docs():
    found = []
    for path in _git("ls-files").stdout.split():
        if path.startswith("tests/") or not (REPO_ROOT / path).is_file():
            continue
        text = _reader_facing(path, (REPO_ROOT / path).read_text(errors="replace"))
        found += [f"{path}: {m.group(0)!r}" for m in UNPUBLISHED_REF.finditer(text)]
    assert found == []


def test_unpublished_ref_check_catches_each_form():
    assert _reader_facing("README.md", "[x](./docs/commands.md)")
    assert UNPUBLISHED_REF.search(_reader_facing("README.md", "see [x](./docs/commands.md)"))
    assert UNPUBLISHED_REF.search(_reader_facing("ansible/roles/x/README.md", "Desain: contexts/DESIGN.md §5."))
    assert UNPUBLISHED_REF.search(_reader_facing("agra/commands/x.py", 'error("diblokir (RULES §8)")'))
    assert UNPUBLISHED_REF.search(_reader_facing("ansible/playbooks/x.yml", "  fail_msg: >-\n    kosong (ARCHITECTURE.md §4)."))
    assert UNPUBLISHED_REF.search(_reader_facing("ansible/roles/x/templates/a.conf.j2", "# health (DESIGN.md §4)"))
    # Comments and docstrings for developers are fine; so is a URL path.
    assert not UNPUBLISHED_REF.search(_reader_facing("agra/commands/x.py", '"""x (DESIGN §7)."""\n# RULES §8\nA = 1'))
    assert not UNPUBLISHED_REF.search(_reader_facing("ansible/playbooks/x.yml", "# RULES §8\n- name: x  # DESIGN §4"))
    assert not UNPUBLISHED_REF.search(_reader_facing("README.md", "https://grafana.com/docs/grafana/"))
