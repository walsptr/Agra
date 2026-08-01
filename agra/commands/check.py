"""`agra check` / `agra precheck` — jalankan precheck.yml."""
from __future__ import annotations
import argparse
from agra.utils.run_playbook import run_playbook


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p: argparse.ArgumentParser = subparsers.add_parser(
        "check", aliases=["precheck", "verify"],
        help="Run preflight validation (playbook precheck.yml) — pre-check sebelum deploy/upgrade",
        description="Validasi topologi inventory, grafana DB connectivity, versi variabel, TLS expiry, passwords plaintext warning.",
    )
    p.add_argument("-i", "--inventory", help="Inventory file path (override AGRA_INVENTORY env / default all-in-one)")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Ansible verbosity (-v to -vvvv)")
    p.set_defaults(func=run_check)
    return p


def run_check(args: argparse.Namespace) -> int:
    return run_playbook(
        "precheck",
        inventory=args.inventory,
        verbosity=args.verbose,
        description="Preflight Validation (agra check)",
        abort_on_nonzero=False,
    )
