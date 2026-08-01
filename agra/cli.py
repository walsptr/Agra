"""Main CLI entry point - argparse setup & dispatch."""
from __future__ import annotations
import argparse
import sys
from typing import List, Optional

from agra import __version__
from agra.utils.colors import section, info, warn, error, BOLD, RESET
from agra.commands import register_all_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agra",
        description="agra: Ansible wrapper untuk deployment & lifecycle monitoring stack "
                    "(Grafana, Prometheus, Node Exporter + HA Keepalived). "
                    "Adopsi pola Kolla-Ansible: layered config, CLI wrapper, versioning terkontrol.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Quickstart:
  1. agra check                                 # Validasi precondition
  2. agra genpwd                                # Generate random secrets
  3. agra deploy -i inventory/multinode         # Deploy dengan inventory multi-node

Documentation: contexts/PRD.md, ARCHITECTURE.md, DESIGN.md, RULES.md, SCHEMA.md
""",
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--inventory", "-i",
        help="(GLOBAL, deprecated) Inventory file path — lebih tepat gunakan per-subcommand -i flag.",
        default=None,
    )

    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        required=True,
        parser_class=argparse.ArgumentParser,
        metavar="COMMAND",
    )
    subparsers.add_parser("help", help="Show this help message and exit").set_defaults(
        func=lambda args: (parser.print_help(), 0)[1]
    )

    register_all_commands(subparsers)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    section(f"agra v{__version__}")

    if not hasattr(args, "func") or args.func is None:
        parser.print_help()
        return 0

    rc = args.func(args)
    return rc if isinstance(rc, int) else 0
