"""Error yang ditujukan ke operator — dicetak sebagai pesan oleh cli.main, bukan traceback."""
from __future__ import annotations


class AgraUserError(Exception):
    """Kesalahan input/lingkungan yang bisa diperbaiki operator (exit code 2)."""


class InventoryNotFoundError(AgraUserError, FileNotFoundError):
    """Inventory dari -i / AGRA_INVENTORY tidak ada — tidak pernah fallback diam-diam."""


class PlaybookNotFoundError(AgraUserError, FileNotFoundError):
    """Playbook yang diminta command tidak ada (instalasi agra tidak lengkap)."""


class ExtraVarsConflictError(AgraUserError):
    """-e user mencoba menimpa var yang nilainya ditentukan (dan dikonfirmasi) CLI."""
