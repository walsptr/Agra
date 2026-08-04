"""`agra genpwd [--force]` — generate random password, tulis etc/agra/passwords.yml.
Safety: TIDAK overwrite jika file SUDAH ADA dan TERISI kecuali --force (sesuai playbook genpwd.yml safety).
"""
from __future__ import annotations
import argparse
from agra.utils.colors import info, warn, error
from agra.utils.run_playbook import run_playbook


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p: argparse.ArgumentParser = subparsers.add_parser(
        "genpwd", aliases=["generate-passwords", "gen-passwords"],
        help="Generate random passwords for secrets file etc/agra/passwords.yml",
        description="Generate 6 random passwords 14 karakter URL-safe ke etc/agra/passwords.yml (plaintext chmod 0600). Tidak overwrite existing non-empty kecuali --force.",
    )
    p.add_argument("--force", action="store_true", help="Force overwrite existing passwords file (akan dibuatkan backup .bak-epoch dulu)")
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.set_defaults(func=run_genpwd)
    return p


def run_genpwd(args: argparse.Namespace) -> int:
    import sys
    from agra.constants import PASSWORDS_FILE

    evars = {"genpwd_force": bool(args.force)}

    rc = run_playbook(
        "genpwd",
        extra_vars=evars,
        verbosity=args.verbose,
        description="Generate Random Passwords (agra genpwd)",
        abort_on_nonzero=False,
    )
    if rc == 0:
        info("Passwords generated OK di " + str(PASSWORDS_FILE), bold=True)
    return rc
