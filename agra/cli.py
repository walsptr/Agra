"""Main CLI entry point - argparse setup & dispatch."""
from __future__ import annotations
import argparse
from typing import List, Optional

from agra import __version__
from agra.errors import AgraUserError
from agra.utils.cli_args import INVENTORY_HELP, AgraArgumentParser
from agra.utils.colors import error, section
from agra.commands import register_all_commands


def build_parser() -> argparse.ArgumentParser:
    parser = AgraArgumentParser(
        prog="agra",
        description="agra: Ansible wrapper untuk deployment & lifecycle monitoring stack "
                    "(Grafana, Prometheus, Node Exporter + HA Keepalived). "
                    "Adopsi pola Kolla-Ansible: layered config, CLI wrapper, versioning terkontrol.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Quickstart:
  1. agra genpwd                                # Generate random secrets
  2. agra certificates generate                 # Self-signed cert (enable_https)
  3. agra check -i inventory/multinode          # Validasi + bootstrap node
  4. agra deploy -i inventory/multinode         # Deploy

-i boleh ditulis sebelum atau sesudah command: `agra -i X deploy` = `agra deploy -i X`.
""",
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    # Satu-satunya default untuk inventory; -i di level command memakai SUPPRESS
    # (agra/utils/cli_args.py) supaya tidak menimpa nilai ini.
    parser.add_argument("-i", "--inventory", dest="inventory", default=None, help=INVENTORY_HELP)

    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        required=True,
        parser_class=AgraArgumentParser,
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

    # Output machine-readable (mis. `backup list --json`): stdout hanya data.
    if not getattr(args, "json", False):
        section(f"agra v{__version__}")

    if not hasattr(args, "func") or args.func is None:
        parser.print_help()
        return 0

    try:
        rc = args.func(args)
    except AgraUserError as e:
        error(str(e))
        return 2
    return rc if isinstance(rc, int) else 0
