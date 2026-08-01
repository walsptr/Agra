"""agra upgrade - Rolling upgrade monitoring stack.

Urutan: STANDBY FIRST (idx 1++) → MASTER LAST (idx 0) — DESIGN §7.
serial:1, max_fail_percentage:0 → playbook sudah enforce ini.
"""
from __future__ import annotations
import argparse
from typing import Dict, Any
from agra.utils.colors import warn, info, error, section, BOLD, RESET, YELLOW
from agra.utils.run_playbook import run_playbook


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "upgrade", aliases=["update", "bump"],
        help="Rolling upgrade monitoring stack (standby first, master last — DESIGN §7)",
        description="Rolling upgrade dengan serial 1. Urutan: standby nodes groups['monitoring'][1:] duluan, MASTER groups['monitoring'][0] TERAKHIR. max_fail_percentage=0: 1 node gagal = upgrade ABORT.",
    )
    p.add_argument("-i", "--inventory")
    p.add_argument("-l", "--limit", help="Limit host subset. (TIDAK DISARANKAN untuk upgrade — gunakan default seluruh group monitoring)")
    p.add_argument("-e", "--extra-vars", action="append", default=[], help="Extra vars mis. pin versi: -e prometheus_tag=v2.54.0 -e grafana_tag=11.3.0")
    p.add_argument(
        "--prometheus-tag",
        help="Shortcut set prometheus tag versi (equivalent -e prometheus_tag=X)",
    )
    p.add_argument(
        "--grafana-tag",
        help="Shortcut set grafana tag versi.",
    )
    p.add_argument(
        "--node-exporter-tag",
        help="Shortcut set node_exporter tag versi.",
    )
    p.add_argument(
        "--prometheus-native-version",
        help="Shortcut set prometheus native version (mode native).",
    )
    p.add_argument(
        "--grafana-native-version",
        help="Shortcut set grafana native version (mode native).",
    )
    p.add_argument(
        "--node-exporter-native-version",
        help="Shortcut set node_exporter native version (mode native).",
    )
    p.add_argument("-t", "--tags", action="append", default=[])
    p.add_argument("--skip-tags", action="append", default=[])
    p.add_argument("--precheck/--no-precheck", default=True, help="Jalankan precheck sebelum upgrade (default on).")
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.set_defaults(func=run_upgrade)
    return p


def _shortcut_flags_to_evars(args: argparse.Namespace) -> Dict[str, Any]:
    ev: Dict[str, Any] = {}
    for attr, varname in [
        ("prometheus_tag", "prometheus_tag"),
        ("grafana_tag", "grafana_tag"),
        ("node_exporter_tag", "node_exporter_tag"),
        ("prometheus_native_version", "prometheus_native_version"),
        ("grafana_native_version", "grafana_native_version"),
        ("node_exporter_native_version", "node_exporter_native_version"),
    ]:
        val = getattr(args, attr, None)
        if val:
            ev[varname] = val
    return ev


def run_upgrade(args: argparse.Namespace) -> int:
    tags_flat = []
    for t in args.tags or []:
        tags_flat.extend([x.strip() for x in t.split(",") if x.strip()])
    skip_flat = []
    for t in args.skip_tags or []:
        skip_flat.extend([x.strip() for x in t.split(",") if x.strip()])

    if args.precheck:
        from agra.commands.check import run_check
        rc = run_check(args)
        if rc != 0:
            error("Precheck FAILED — upgrade dibatalkan. Gunakan --no-precheck untuk bypass (TIDAK DISARANKAN).")
            return rc

    extra_vars = _shortcut_flags_to_evars(args)

    section("ROLLING UPGRADE (standby first → master last — DESIGN §7)")
    warn("  Urutan aktual akan diplaybook: groups[1..] standby dulu → group[0] MASTER terakhir.")
    warn("  max_fail_percentage=0: SATU node gagal = SELURUH upgrade ABORT (tidak lanjut ke node berikutnya).")
    if extra_vars:
        info("Versi shortcut flags di-set: " + ", ".join(f"{k}={v}" for k, v in extra_vars.items()))

    return run_playbook(
        "upgrade",
        inventory=args.inventory,
        tags=tags_flat or None,
        skip_tags=skip_flat or None,
        limit=args.limit,
        extra_vars=extra_vars if extra_vars else None,
        extra_vars_raw=args.extra_vars or None,
        verbosity=args.verbose,
        description="Rolling Upgrade Monitoring",
        abort_on_nonzero=False,
    )
