"""`agra deploy` — jalankan playbook deploy.yml. Flags: tags, limit, extra-vars, inventory."""
from __future__ import annotations
import argparse
from typing import List, Dict, Any
from agra.utils.run_playbook import run_playbook


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p: argparse.ArgumentParser = subparsers.add_parser(
        "deploy", aliases=["apply", "install"],
        help="Deploy / re-deploy monitoring stack (idempotent) — playbook deploy.yml",
        description="Full deploy common, node_exporter, prometheus, grafana, nginx, keepalived (auto jika multi-node). Idempotent: run berulang OK.",
    )
    p.add_argument("-i", "--inventory", help="Inventory file (default: inventory/all-in-one)")
    p.add_argument("-t", "--tags", action="append", default=[], help="Run only tagged tasks. Repeatable: -t grafana -t nginx.")
    p.add_argument("--skip-tags", action="append", default=[], help="Skip tagged tasks.")
    p.add_argument("-l", "--limit", help="Limit run to subset inventory hosts (ansible --limit).")
    p.add_argument("-e", "--extra-vars", action="append", default=[], help="Extra vars ansible: KEY=VALUE or JSON string. Repeatable.")
    p.add_argument(
        "--precheck",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="precheck",
        help="Jalankan precheck SEBELUM deploy (default: TRUE / precheck aktif). "
             "Untuk bypass: --no-precheck (TIDAK DISARANKAN production)."
    )
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.set_defaults(func=run_deploy)
    return p


def _parse_extra_vars(raw_list: List[str]) -> Dict[str, Any]:
    """Parse list string KEY=VALUE jadi dict. Biarkan dict raw return empty jika gagal — masuk ke extra_vars_raw."""
    parsed: Dict[str, Any] = {}
    return parsed


def run_deploy(args: argparse.Namespace) -> int:
    tags_flat: List[str] = []
    for t in args.tags or []:
        tags_flat.extend([x.strip() for x in t.split(",") if x.strip()])
    skip_flat: List[str] = []
    for t in args.skip_tags or []:
        skip_flat.extend([x.strip() for x in t.split(",") if x.strip()])

    # Dapatkan nilai boolean precheck. Gunakan getattr dengan default True untuk defensive programming
    # (hindari AttributeError jika parser config berubah di masa depan).
    precheck_enabled = getattr(args, "precheck", True)
    rc_check = 0
    if precheck_enabled:
        # --- Jalankan precheck terlebih dahulu via command check wrapper ---
        # HATI-HATI: args.inventory diserahkan langsung ke run_check(). run_check()
        # sudah memvalidasi wajib -i / AGRA_INVENTORY env.
        from agra.commands.check import run_check
        rc_check = run_check(args)
        if rc_check != 0:
            from agra.utils.colors import error, warn
            error(f"Precheck FAILED (rc={rc_check}). Deploy DIBATALKAN untuk mencegah bad state.")
            warn("Untuk bypass precheck: `agra deploy --no-precheck` (TIDAK DISARANKAN production).")
            return rc_check

    user_evar = args.extra_vars or []
    if isinstance(user_evar, str):
        user_evar = [user_evar]
    merged_evar = ["_agra_cli_inventory_explicit_confirmed=true"] + list(user_evar)

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
