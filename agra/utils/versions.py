"""Baca /etc/agra/.installed_versions.yml dan bandingkan major version tag."""
from __future__ import annotations
import re
from typing import Any, Dict, Optional

import yaml

from agra.constants import INSTALLED_VERSIONS_FILE
from agra.utils.paths import load_globals_file

# Service yang bisa di-rollback → nama variabel tag-nya.
SERVICE_TAG_VARS: Dict[str, str] = {
    "grafana": "grafana_tag",
    "prometheus": "prometheus_tag",
    "node_exporter": "node_exporter_tag",
    "nginx": "nginx_tag",
    "keepalived": "keepalived_tag",
}


def load_installed_versions() -> Dict[str, Any]:
    """Return isi file versi ({} jika belum ada). Raise PermissionError apa adanya."""
    if not INSTALLED_VERSIONS_FILE.exists():
        return {}
    with INSTALLED_VERSIONS_FILE.open() as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def entry_versions(data: Dict[str, Any], entry: str) -> Dict[str, str]:
    """Versions dict dari entry `current` / `previous`."""
    versions = (data.get(entry) or {}).get("versions") or {}
    return {k: str(v) for k, v in versions.items()}


def major_version(tag: str) -> Optional[int]:
    """'v2.53.0' → 2, '11.2.0' → 11, '1.27-alpine' → 1, 'latest' → None."""
    m = re.match(r"^v?(\d+)", str(tag).strip())
    return int(m.group(1)) if m else None


def globals_versions() -> Dict[str, str]:
    """Tag versi dari globals.yml — fallback `current` jika belum ada catatan versi."""
    data = load_globals_file()
    return {var: str(data[var]) for var in SERVICE_TAG_VARS.values() if var in data}
