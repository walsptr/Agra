"""data_files untuk install non-editable (metadata lain ada di pyproject.toml).

`pip install .` / wheel hanya memasang package `agra/`; playbook, role,
ansible.cfg, inventory contoh dan template etc/agra dipasang ke
`<prefix>/share/agra/` dengan struktur yang sama seperti di repo —
agra.constants._find_data_root() mencarinya di sana (pola kolla-ansible).
"""
from __future__ import annotations

import os
from collections import defaultdict

from setuptools import setup

SHARE = os.path.join("share", "agra")
# File yang tidak boleh ikut terpasang: passwords.yml di repo bisa berisi
# nilai milik operator (gitignored) — yang dipasang hanya template .example.
EXCLUDE_NAMES = {"passwords.yml", "passwords.yml.bak"}
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache"}


def _tree(src: str):
    files = defaultdict(list)
    for root, dirs, names in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for name in sorted(names):
            if name in EXCLUDE_NAMES or name.endswith((".retry", ".pyc")):
                continue
            files[os.path.join(SHARE, root)].append(os.path.join(root, name))
    return list(files.items())


setup(
    data_files=[(SHARE, ["ansible.cfg"])]
    + _tree("ansible")
    + _tree("inventory")
    + _tree(os.path.join("etc", "agra")),
)
