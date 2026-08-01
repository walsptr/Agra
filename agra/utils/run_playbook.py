"""Jalankan ansible-playbook sebagai subprocess dengan STREAM OUTPUT REAL-TIME.

TIDAK pakai ansible_runner library agar dependency sedikit (hanya PyYAML).
User diharapkan sudah install ansible di system PATH.
"""
from __future__ import annotations
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional, Dict, List, Tuple

from agra.utils.colors import info, warn, error, section, debug, BOLD, RESET, MAGENTA
from agra.utils.paths import resolve_inventory, ansible_env
from agra.constants import PLAYBOOKS, REQUIRED_COMMANDS


def _check_ansible_available() -> None:
    """Abort sebelum apa pun jika `ansible-playbook` tidak ada di PATH."""
    import shutil
    missing = [cmd for cmd in REQUIRED_COMMANDS if shutil.which(cmd) is None]
    if missing:
        error(
            "Ansible TIDAK TERINSTALL di PATH (missing commands: "
            + ", ".join(missing)
            + "). Install terlebih dahulu: `pip install ansible` atau install sesuai OS package manager."
        )
        sys.exit(2)


def build_ansible_command(
    playbook: str,
    inventory: Optional[str] = None,
    tags: Optional[List[str]] = None,
    skip_tags: Optional[List[str]] = None,
    limit: Optional[str] = None,
    extra_vars: Optional[Dict[str, object]] = None,
    extra_vars_raw: Optional[List[str]] = None,
    verbosity: int = 0,
    extra_args: Optional[Iterable[str]] = None,
) -> Tuple[List[str], Path]:
    """Build list of argv untuk ansible-playbook command.

    Returns: (argv_list, resolved_inventory_path)
    """
    _check_ansible_available()

    pb_path: Path
    if playbook in PLAYBOOKS:
        pb_path = PLAYBOOKS[playbook]
    else:
        pb_path = Path(playbook).expanduser()
        if not pb_path.is_absolute():
            pb_path = (Path.cwd() / pb_path).resolve()

    if not pb_path.exists():
        raise FileNotFoundError(f"Playbook not found: {pb_path}")

    inv_path = resolve_inventory(inventory)

    argv: List[str] = ["ansible-playbook", str(pb_path)]
    argv += ["-i", str(inv_path)]

    if tags:
        argv += ["--tags", ",".join(tags)]
    if skip_tags:
        argv += ["--skip-tags", ",".join(skip_tags)]
    if limit:
        argv += ["--limit", limit]
    if verbosity > 0:
        argv += ["-" + ("v" * min(verbosity, 4))]

    if extra_vars:
        import json
        try:
            ev_json = json.dumps(extra_vars, ensure_ascii=False)
            argv += ["--extra-vars", ev_json]
        except Exception as e:
            warn(f"Failed serialize extra_vars: {e}")

    if extra_vars_raw:
        for evr in extra_vars_raw:
            argv += ["--extra-vars", evr]

    if extra_args:
        argv.extend(extra_args)

    return argv, inv_path


def run_playbook(
    playbook: str,
    *,
    inventory: Optional[str] = None,
    tags: Optional[List[str]] = None,
    skip_tags: Optional[List[str]] = None,
    limit: Optional[str] = None,
    extra_vars: Optional[Dict[str, object]] = None,
    extra_vars_raw: Optional[List[str]] = None,
    verbosity: int = 0,
    extra_args: Optional[Iterable[str]] = None,
    description: Optional[str] = None,
    abort_on_nonzero: bool = False,
) -> int:
    """Jalankan ansible-playbook, stream output real-time, return exit code.

    Args:
        description: Opsional string deskripsi yang di-print sebelum run (mis. "Precheck Validation")
        abort_on_nonzero: Jika True, sys.exit(rc) otomatis; False cuma return rc.

    Returns:
        Exit code (0 = OK)
    """
    argv, inv_path = build_ansible_command(
        playbook=playbook, inventory=inventory, tags=tags, skip_tags=skip_tags,
        limit=limit, extra_vars=extra_vars, extra_vars_raw=extra_vars_raw,
        verbosity=verbosity, extra_args=extra_args,
    )

    section(description or f"Run playbook: {playbook}")
    print(f"{BOLD}Inventory:{RESET} {inv_path}")
    print(f"{BOLD}Command   :{RESET} {shlex.join(argv)}")
    if os.environ.get("AGRA_DEBUG", "") == "1":
        debug(f"ANSIBLE_ROLES_PATH={os.environ.get('ANSIBLE_ROLES_PATH', '')}")
        debug(f"ANSIBLE_CONFIG={os.environ.get('ANSIBLE_CONFIG', '')}")

    env = ansible_env()

    try:
        proc = subprocess.Popen(
            argv,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            text=True,
        )
    except FileNotFoundError as e:
        error(f"Failed exec ansible-playbook: {e}")
        if abort_on_nonzero:
            sys.exit(2)
        return 2

    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            s = line.rstrip()
            if s.startswith("TASK [") or s.startswith("PLAY ["):
                print(f"{BOLD}{MAGENTA}{s}{RESET}", flush=True)
            elif any(x in s for x in ("FATAL", "FAILED!", "ERROR", "fatal:")) and "skipped" not in s.lower():
                print(f"{BOLD}{s}{RESET}", flush=True)
            else:
                print(s, flush=True)
    except KeyboardInterrupt:
        warn("Interrupted by user (Ctrl+C). Terminating ansible...")
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        if abort_on_nonzero:
            sys.exit(130)
        return 130

    rc = proc.wait()
    if rc == 0:
        info(f"Playbook {playbook} finished SUCCESS (rc=0)", bold=True)
    else:
        error(f"Playbook {playbook} FAILED (rc={rc})")
    if abort_on_nonzero and rc != 0:
        sys.exit(rc)
    return rc
