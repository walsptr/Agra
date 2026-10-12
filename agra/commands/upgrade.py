"""agra upgrade - Rolling upgrade monitoring stack (DESIGN §7).

Alur: precheck → backup (WAJIB, RULES §10 — tidak ada flag skip) → rolling
upgrade (node_exporter-only → standby → master terakhir, serial 1, health gate
per host) → catat versi ke /etc/agra/.installed_versions.yml.
"""
from __future__ import annotations
import argparse
from typing import Dict, Any
from agra.utils.colors import warn, info, error, section
from agra.utils.cli_args import add_inventory_argument
from agra.utils.run_playbook import check_extra_vars_conflicts, run_playbook


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "upgrade", aliases=["update", "bump"],
        help="Rolling upgrade monitoring stack (backup dulu, standby first, master last — DESIGN §7)",
        description="Precheck → backup otomatis (wajib) → rolling upgrade serial 1 (node_exporter-only → standby → MASTER groups['monitoring'][0] terakhir) dengan health gate per host. 1 node gagal = upgrade ABORT. Versi lama dicatat untuk `agra rollback`.",
    )
    add_inventory_argument(p)
    p.add_argument("-l", "--limit", help="Limit host subset. (TIDAK DISARANKAN untuk upgrade — gunakan default seluruh group monitoring)")
    p.add_argument("-e", "--extra-vars", action="append", default=[], help="Extra vars mis. pin versi: -e prometheus_tag=v2.54.0 -e grafana_tag=11.3.0")
    p.add_argument(
        "--prometheus-tag",
        help="Shortcut set prometheus tag versi (setara -e prometheus_tag=X; jangan dipakai bersamaan).",
    )
    p.add_argument(
        "--grafana-tag",
        help="Shortcut set grafana tag versi.",
    )
    p.add_argument(
        "--node-exporter-tag",
        help="Shortcut set node_exporter tag versi.",
    )
    p.add_argument("-t", "--tags", action="append", default=[])
    p.add_argument("--skip-tags", action="append", default=[])
    p.add_argument(
        "--precheck",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="precheck",
        help="Jalankan precheck SEBELUM upgrade (default: TRUE / precheck aktif). "
             "Untuk bypass: --no-precheck (TIDAK DISARANKAN production)."
    )
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.set_defaults(func=run_upgrade)
    return p


def _shortcut_flags_to_evars(args: argparse.Namespace) -> Dict[str, Any]:
    ev: Dict[str, Any] = {}
    for attr, varname in [
        ("prometheus_tag", "prometheus_tag"),
        ("grafana_tag", "grafana_tag"),
        ("node_exporter_tag", "node_exporter_tag"),
    ]:
        val = getattr(args, attr, None)
        if val:
            ev[varname] = val
    return ev


def run_upgrade(args: argparse.Namespace) -> int:
    # --<service>-tag dan -e <service>_tag untuk service yang sama = ambigu.
    check_extra_vars_conflicts(args.extra_vars, _shortcut_flags_to_evars(args))
    tags_flat = []
    for t in args.tags or []:
        tags_flat.extend([x.strip() for x in t.split(",") if x.strip()])
    skip_flat = []
    for t in args.skip_tags or []:
        skip_flat.extend([x.strip() for x in t.split(",") if x.strip()])

    precheck_enabled = getattr(args, "precheck", True)
    if precheck_enabled:
        from agra.commands.check import run_check
        rc = run_check(args)
        if rc != 0:
            error(f"Precheck FAILED (rc={rc}). Upgrade DIBATALKAN untuk mencegah bad state.")
            warn("Untuk bypass precheck: `agra upgrade --no-precheck` (TIDAK DISARANKAN production).")
            return rc

    # Backup WAJIB sebelum upgrade (RULES §10). Tanpa --limit/--tags user dan
    # tanpa -e versi baru: backup harus selalu dari master dengan versi saat ini.
    section("BACKUP SEBELUM UPGRADE (RULES §10)")
    rc = run_playbook(
        "backup",
        inventory=args.inventory,
        extra_vars_raw=["_agra_cli_inventory_explicit_confirmed=true"],
        verbosity=args.verbose,
        description="Backup otomatis sebelum upgrade",
        abort_on_nonzero=False,
    )
    if rc != 0:
        error(f"Backup GAGAL (rc={rc}). Upgrade DIBATALKAN — tidak ada upgrade tanpa backup.")
        return rc

    extra_vars = _shortcut_flags_to_evars(args)

    section("ROLLING UPGRADE (standby first → master last — DESIGN §7)")
    warn("  Urutan: node_exporter-only → standby groups[1..] → MASTER groups[0] terakhir, health gate per host.")
    warn("  max_fail_percentage=0: SATU node gagal = SELURUH upgrade ABORT (tidak lanjut ke node berikutnya).")
    if extra_vars:
        info("Versi shortcut flags di-set: " + ", ".join(f"{k}={v}" for k, v in extra_vars.items()))

    user_evar = args.extra_vars or []
    if isinstance(user_evar, str):
        user_evar = [user_evar]
    merged_evar = ["_agra_cli_inventory_explicit_confirmed=true"] + list(user_evar)

    return run_playbook(
        "upgrade",
        inventory=args.inventory,
        tags=tags_flat or None,
        skip_tags=skip_flat or None,
        limit=args.limit,
        extra_vars=extra_vars if extra_vars else None,
        extra_vars_raw=merged_evar or None,
        verbosity=args.verbose,
        description="Rolling Upgrade Monitoring",
        abort_on_nonzero=False,
    )
