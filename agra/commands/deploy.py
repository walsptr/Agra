"""`agra deploy` — jalankan playbook deploy.yml. Flags: tags, limit, extra-vars, inventory."""
from __future__ import annotations
import argparse
from typing import List
import yaml

from agra.constants import INSTALLED_VERSIONS_FILE
from agra.utils.cli_args import add_inventory_argument
from agra.utils.colors import BOLD, MAGENTA, RESET, warn
from agra.utils.run_playbook import run_playbook
from agra.utils.versions import version_drift


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p: argparse.ArgumentParser = subparsers.add_parser(
        "deploy", aliases=["apply", "install"],
        help="Deploy / re-deploy monitoring stack (idempotent) — playbook deploy.yml",
        description="Deploy monitoring stack (Grafana/Prometheus/Node Exporter/Nginx/Keepalived) via Ansible playbooks. Jalankan validasi config terlebih dahulu dengan command terpisah jika diperlukan.",
    )
    add_inventory_argument(p)
    p.add_argument("-t", "--tags", action="append", default=[], help="Run only tagged tasks. Repeatable: -t grafana -t nginx.")
    p.add_argument("--skip-tags", action="append", default=[], help="Skip tagged tasks.")
    p.add_argument("-l", "--limit", help="Limit run to subset inventory hosts (ansible --limit).")
    p.add_argument("-e", "--extra-vars", action="append", default=[], help="Extra vars ansible: KEY=VALUE or JSON string. Repeatable.")
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.set_defaults(func=run_deploy)
    return p


def _warn_version_drift(extra_vars_raw: List[str]) -> None:
    """Deploy dengan tag baru = upgrade tanpa pengaman: semua host sekaligus,
    tanpa backup otomatis dan tanpa health gate. Tidak diblokir (deploy tetap
    cara menerapkan config), tapi operator harus tahu sebelum terjadi."""
    try:
        drift = version_drift(extra_vars_raw)
    except (OSError, yaml.YAMLError) as e:
        warn(f"Tidak bisa membandingkan versi dengan {INSTALLED_VERSIONS_FILE}: {e}")
        return
    if not drift:
        return
    warn(f"Versi yang akan di-deploy BERBEDA dari versi terpasang ({INSTALLED_VERSIONS_FILE}):")
    for var, (old, new) in sorted(drift.items()):
        warn(f"  {var}: {old} → {new}")
    warn("`agra deploy` mengganti versi di semua host SEKALIGUS, tanpa backup otomatis dan tanpa health gate. "
         f"Untuk ganti versi gunakan {MAGENTA}{BOLD}agra upgrade{RESET} (rolling, backup dulu, bisa di-rollback).")


def run_deploy(args: argparse.Namespace) -> int:
    tags_flat: List[str] = []
    for t in args.tags or []:
        tags_flat.extend([x.strip() for x in t.split(",") if x.strip()])
    skip_flat: List[str] = []
    for t in args.skip_tags or []:
        skip_flat.extend([x.strip() for x in t.split(",") if x.strip()])

    user_evar = args.extra_vars or []
    if isinstance(user_evar, str):
        user_evar = [user_evar]
    merged_evar = ["_agra_cli_inventory_explicit_confirmed=true"] + list(user_evar)
    _warn_version_drift(list(user_evar))

    return run_playbook(
        "deploy",
        inventory=args.inventory,
        tags=tags_flat or None,
        skip_tags=skip_flat or None,
        limit=args.limit,
        extra_vars_raw=merged_evar or None,
        verbosity=args.verbose,
        description="Deploy Monitoring Stack (agra deploy)",
        abort_on_nonzero=False,
    )
