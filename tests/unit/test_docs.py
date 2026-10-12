"""Docs describe the agra that exists (PR 11): every `agra ...` command in the
docs parses with the real CLI, every var they name has a SCHEMA.md row and is
not removed, and relative links resolve."""
from __future__ import annotations

import contextlib
import io
import re
import shlex
from pathlib import Path

import pytest

from agra.cli import build_parser
from agra.constants import PROJECT_ROOT as REPO_ROOT, REMOVED_KEYS

# docs/ and contexts/ are not published (PR 12); a clone without them has nothing to check.
if not (REPO_ROOT / "contexts" / "SCHEMA.md").exists() or not (REPO_ROOT / "docs").is_dir():
    pytest.skip("docs/ and contexts/ are not in this checkout", allow_module_level=True)

USER_DOCS = sorted(
    [REPO_ROOT / "README.md"]
    + list((REPO_ROOT / "docs").glob("*.md"))
    + list((REPO_ROOT / "ansible" / "roles").glob("*/README.md"))
)
ALL_DOCS = USER_DOCS + [REPO_ROOT / "AGENTS.md"] + sorted((REPO_ROOT / "contexts").glob("*.md"))

SCHEMA_ROWS = set(re.findall(r"^\|\s*`([a-z_][a-z0-9_]*)`", (REPO_ROOT / "contexts" / "SCHEMA.md").read_text(), re.M))
VAR_PREFIX = re.compile(
    r"^(?:enable|grafana|prometheus|node_exporter|nginx|keepalived|tls|backup|common|monitoring|expose)_[a-z0-9_]*[a-z0-9]$"
)
FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.M | re.S)
INLINE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
LINK = re.compile(r"\]\(([^)\s]+)\)")
# Things agra no longer has: the site playbook, native mode, group_vars
# loading, ansible-vault, upgrade --no-backup, Grafana under the /grafana/ subpath.
STALE = re.compile(r"site\.yml|native\.yml|group_vars|ansible-vault|--no-backup|(?:https?://\S*|[\s`(])/grafana\b")


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _commands(text: str):
    """`agra ...` invocations from code blocks (backslash continuations joined) and inline code."""
    for block in FENCE.findall(text):
        for line in block.replace("\\\n", " ").splitlines():
            line = re.sub(r"^\s*(?:\S*\$\s+)?", "", line)
            if line.startswith("agra "):
                yield re.split(r"\s+#", line)[0].strip()
    for span in INLINE.findall(FENCE.sub("", text)):
        if span.startswith("agra "):
            yield span.strip()


def _argv(command: str):
    """None for usage synopses (`[--force]`, `{a | b}`); placeholders `<x>` become a word."""
    if re.search(r"[\[\]{}]|\s\|\s|\.\.\.", command):
        return None
    return shlex.split(re.sub(r"<[^>]+>", "X", command))[1:]


CASES = sorted({(_rel(doc), cmd) for doc in ALL_DOCS for cmd in _commands(doc.read_text()) if _argv(cmd) is not None})


@pytest.mark.parametrize("doc,command", CASES)
def test_documented_command_parses(doc, command):
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            build_parser().parse_args(_argv(command))
    except SystemExit as exc:
        # A bare command name in prose (`agra restore`) names the command; it
        # is not an invocation, so only its required options may be missing.
        naming_only = not any(a.startswith("-") for a in _argv(command)) and re.search(r"(?:is|are) required", err.getvalue()) is not None
        assert exc.code == 0 or naming_only, f"{doc}: `{command}` is not a valid agra command:\n{err.getvalue()}"


def test_command_extraction_finds_commands():
    assert len(CASES) > 50
    assert {c for _, c in CASES} >= {"agra deploy -i inventory/all-in-one", "agra backup list --json"}


# docs/add-new-role.md builds a hypothetical role; its vars are not agra's.
EXAMPLE_VAR = re.compile(r"alertmanager")


def _var_mentions(text: str):
    names = [re.split(r"[=:\s|]", span.strip(), maxsplit=1)[0] for span in INLINE.findall(text)]
    for block in FENCE.findall(text):
        names += re.findall(r"^#?\s*([a-z][a-z0-9_]*)\s*:", block, re.M)
    return [n for n in names if VAR_PREFIX.match(n) and not EXAMPLE_VAR.search(n)]


VAR_CASES = sorted({(_rel(doc), var) for doc in USER_DOCS for var in _var_mentions(doc.read_text())})


@pytest.mark.parametrize("doc,var", VAR_CASES)
def test_documented_var_exists(doc, var):
    assert var not in REMOVED_KEYS, f"{doc} documents removed var {var}: {REMOVED_KEYS[var]}"
    assert var in SCHEMA_ROWS, f"{doc} documents {var}, which has no row in contexts/SCHEMA.md"


def test_var_extraction_finds_vars():
    assert {v for _, v in VAR_CASES} >= {"grafana_tag", "monitoring_vip", "backup_control_node_dir"}


@pytest.mark.parametrize("doc", USER_DOCS, ids=_rel)
def test_no_stale_features(doc):
    found = [m.group(0) for m in STALE.finditer(doc.read_text())]
    assert not found, f"{_rel(doc)} mentions {found}"


@pytest.mark.parametrize("doc", ALL_DOCS, ids=_rel)
def test_relative_links_resolve(doc):
    broken = []
    for target in LINK.findall(doc.read_text()):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        if not (doc.parent / target.split("#")[0]).exists():
            broken.append(target)
    assert not broken, f"{_rel(doc)}: broken links {broken}"
