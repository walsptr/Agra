"""Static checks that enforce contexts/RULES.md mechanically."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from agra.constants import ANSIBLE_DIR, PER_HOST_KEYS, PROJECT_ROOT as REPO_ROOT, ROLES_DIR, SECRET_KEYS

MOLECULE_DIR = REPO_ROOT / "tests" / "molecule"


def _yaml_files(*roots: Path):
    for root in roots:
        yield from sorted(p for p in root.rglob("*.yml") if "/templates/" not in str(p))


def _walk(node):
    """Yield every mapping in a parsed YAML document."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _load(path: Path):
    return list(yaml.safe_load_all(path.read_text()))


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def test_no_ignore_errors():
    """RULES §16.1 — applies to tests too: a verify step that cannot fail tests nothing."""
    offenders = [
        _rel(p) for p in _yaml_files(ANSIBLE_DIR, MOLECULE_DIR)
        if any("ignore_errors" in m for m in _walk(_load(p)))
    ]
    assert offenders == []


def test_no_shell_or_true():
    """RULES §16.2 (comments that mention the pattern are fine)."""
    pattern = re.compile(r"\|\|\s*true\b")
    offenders = [
        f"{_rel(p)}:{n}" for p in _yaml_files(ANSIBLE_DIR)
        for n, line in enumerate(p.read_text().splitlines(), 1)
        if pattern.search(line) and not line.lstrip().startswith("#")
    ]
    assert offenders == []


def test_no_meta_end_host_in_roles():
    """In a multi-role play (upgrade/rollback) end_host skips every later role and the health gate."""
    offenders = [
        _rel(p) for p in _yaml_files(ROLES_DIR)
        if any(m.get("ansible.builtin.meta", m.get("meta")) == "end_host" for m in _walk(_load(p)))
    ]
    assert offenders == []


def test_playbooks_never_load_globals_or_passwords():
    """RULES §13.3 / §15.2 — both files only arrive as CLI extra-vars."""
    target = re.compile(r"(globals|passwords)\.ya?ml")
    offenders = []
    for p in _yaml_files(ANSIBLE_DIR):
        for m in _walk(_load(p)):
            for key in ("vars_files", "include_vars", "ansible.builtin.include_vars"):
                if key in m and target.search(str(m[key])):
                    offenders.append(f"{_rel(p)}: {key}")
    assert offenders == []


def test_globals_template_has_no_secrets_or_per_host_keys():
    """RULES §7 / §14.6."""
    data = yaml.safe_load((REPO_ROOT / "etc" / "agra" / "globals.yml").read_text()) or {}
    assert sorted(set(data) & set(SECRET_KEYS + PER_HOST_KEYS)) == []


@pytest.mark.parametrize("role", sorted(p.name for p in ROLES_DIR.iterdir() if p.is_dir()))
def test_role_layout(role):
    """RULES §1 — router main.yml, defaults, README."""
    base = ROLES_DIR / role
    for rel in ("README.md", "defaults/main.yml", "tasks/main.yml"):
        assert (base / rel).is_file(), f"{role}: missing {rel}"
