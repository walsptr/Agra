"""Argumen argparse yang dipakai bersama oleh banyak command.

Opsi yang boleh ditulis di beberapa level (`agra -i X deploy`, `agra deploy -i X`,
`agra backup -i X create`) hanya punya default di level TERLUAR. Level di dalamnya
memakai `default=argparse.SUPPRESS`: subparser argparse mem-parse ke namespace
baru lalu menyalin semua atributnya ke namespace induk, sehingga default di level
dalam akan menimpa nilai yang sudah diberikan user di level luar.
"""
from __future__ import annotations

import argparse

class AgraArgumentParser(argparse.ArgumentParser):
    """ArgumentParser tanpa singkatan opsi panjang.

    Default argparse menerima prefix unik: `--yes` / `--yes-i` akan terbaca
    sebagai `--yes-i-really-mean-it` dan melewati konfirmasi destruktif
    (RULES §8). Semua parser agra — termasuk subparser bertingkat, yang
    mewarisi class induknya — memakai class ini.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)


INVENTORY_HELP = (
    "Inventory file. Path relatif dihitung dari direktori kerja saat ini. "
    "Tanpa -i: env AGRA_INVENTORY, lalu inventory/all-in-one repo."
)


def add_inventory_argument(parser: argparse.ArgumentParser, help: str = INVENTORY_HELP) -> None:
    """`-i/--inventory` untuk command/subcommand — default milik parser global `agra`."""
    parser.add_argument("-i", "--inventory", dest="inventory", default=argparse.SUPPRESS, help=help)


def positive_int(value: str) -> int:
    """argparse type: integer >= 1 (e.g. a count where 0 or less would delete everything)."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"bukan bilangan bulat: {value!r}") from None
    if n < 1:
        raise argparse.ArgumentTypeError(f"minimal 1, bukan {n}")
    return n
