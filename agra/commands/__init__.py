"""Agra CLI command modules. Setiap command module expose setup_parser(subparsers) dan run_(name)(args) return int rc."""
from __future__ import annotations
from typing import List, Callable, Any, TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

COMMAND_MODULES: List[str] = [
    "agra.commands.check",
    "agra.commands.genpwd",
    "agra.commands.deploy",
    "agra.commands.upgrade",
    "agra.commands.rollback",
    "agra.commands.destroy",
    "agra.commands.backup",
    "agra.commands.restore",
    "agra.commands.tls",
]


def register_all_commands(subparsers: "argparse._SubParsersAction") -> None:
    """Import each module in COMMAND_MODULES, panggil setup_parser(subparsers)."""
    import importlib
    for mod_name in COMMAND_MODULES:
        mod = importlib.import_module(mod_name)
        mod.setup_parser(subparsers)
