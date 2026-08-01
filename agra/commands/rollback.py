"""agra rollback - Rollback ke versi sebelumnya.

Sebenarnya implementasi sama seperti upgrade tapi pakai playbook rollback.yml + user provide versi lama via --*-tag / -e var.
Safety: precheck jalan dulu, prompt konfirmasi jika interactive.
"""
from __future__ import annotations
import argparse
import os
import sys
from typing import Dict, Any
from agra.utils.colors import warn, info, error, section, BOLD, RESET, RED, YELLOW
from agra.utils.run_playbook import run_playbook


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "rollback", aliases=["revert", "downgrade"],
        help="Rollback ke versi sebelumnya (sediakan versi via --prometheus-tag atau -e flag).",
        description="Rollback: pin versi ke tag/native_version yang diinginkan. Playbook rollback.yml serial 1 standby-first master-last untuk keamanan.",
    )
    p.add_argument("-i", "--inventory")
    p.add_argument("-l", "--limit")
    p.add_argument("-e", "--extra-vars", action="append", default=[])
    p.add_argument("--prometheus-tag")
    p.add_argument("--grafana-tag")
    p.add_argument("--node-exporter-tag")
    p.add_argument("--prometheus-native-version")
    p.add_argument("--grafana-native-version")
    p.add_argument("--node-exporter-native-version")
    p.add_argument("-t", "--tags", action="append", default=[])
    p.add_argument("--skip-tags", action="append", default=[])
    p.add_argument("--precheck/--no-precheck", default=True)
    p.add_argument("--yes", action="store_true", help="Skip rollback confirmation prompt (untuk CI, set juga AGRA_NON_INTERACTIVE=1).")
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.set_defaults(func=run_rollback)
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


def run_rollback(args: argparse.Namespace) -> int:
    tags_flat = []
    for t in args.tags or []:
        tags_flat.extend([x.strip() for x in t.split(",") if x.strip()])
    skip_flat = []
    for t in args.skip_tags or []:
        skip_flat.extend([x.strip() for x in t.split(",") if x.strip()])

    extra_vars = _shortcut_flags_to_evars(args)

    if not extra_vars and not args.extra_vars:
        warn("⚠️ TIDAK ada versi pin spesifik diberikan via --prometheus-tag / --grafana-tag / -e ... → rollback = re-apply state idempotent TANPA perubahan versi. Lanjutkan?")

    if not args.yes and os.environ.get("AGRA_NON_INTERACTIVE", "") != "1":
        section("ROLLBACK CONFIRMATION")
        warn(f"{BOLD}Rollback BERSIFAT DESTRUKTIF{RESET} — akan memodifikasi container/versi service monitoring.")
        try:
            resp = input(f"{YELLOW}Ketik '{BOLD}ROLLBACK{RESET}{YELLOW}' (huruf besar) untuk melanjutkan, atau Ctrl+C untuk batal: ").strip()
        except (EOFError, KeyboardInterrupt):
            error("\nRollback dibatalkan user.")
            return 1
        if resp != "ROLLBACK":
            error(f"Konfirmasi SALAH (input={resp}). Rollback dibatalkan.")
            return 1
        info("Konfirmasi OK. Lanjut rollback.")

    if args.precheck:
        from agra.commands.check import run_check
        rc = run_check(args)
        if rc != 0:
            error("Precheck FAILED — rollback dibatalkan. --no-precheck untuk bypass.")
            return rc

    return run_playbook(
        "rollback",
        inventory=args.inventory,
        tags=tags_flat or None,
        skip_tags=skip_flat or None,
        limit=args.limit,
        extra_vars=extra_vars if extra_vars else None,
        extra_vars_raw=args.extra_vars or None,
        verbosity=args.verbose,
        description="Rollback Monitoring ke Versi Sebelumnya",
        abort_on_nonzero=False,
    )
