"""Jalankan ansible-playbook sebagai subprocess dengan STREAM OUTPUT REAL-TIME.

TIDAK pakai ansible_runner library agar dependency sedikit (hanya PyYAML).
User diharapkan sudah install ansible di system PATH.
"""
from __future__ import annotations
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from agra.errors import ExtraVarsConflictError, PlaybookNotFoundError
from agra.utils.colors import info, warn, error, section, debug, BOLD, RESET, MAGENTA
from agra.utils.paths import resolve_inventory, ansible_env, ansible_path
from agra.constants import PLAYBOOKS, REQUIRED_COMMANDS, ETC_DIR, GLOBALS_FILE, PASSWORDS_FILE


def _check_ansible_available() -> None:
    """Abort sebelum apa pun jika `ansible-playbook` tidak ada di PATH."""
    import shutil
    path = ansible_path()
    missing = [cmd for cmd in REQUIRED_COMMANDS if shutil.which(cmd, path=path) is None]
    if missing:
        error(
            "Ansible TIDAK TERINSTALL di PATH (missing commands: "
            + ", ".join(missing)
            + "). ansible-core adalah dependency agra — jalankan ulang ./install.sh, atau "
            "`pip install ansible-core` di venv yang sama dengan agra."
        )
        sys.exit(2)


def _check_etc_vars_readable() -> None:
    """Abort jika globals.yml / passwords.yml tidak ada atau tidak bisa dibaca user ini.

    Kedua file di-inject sebagai extra-vars (`-e @file`) yang dibaca oleh proses
    ansible-playbook di control node sebagai user pemanggil — `become` TIDAK berlaku
    di sini. Solusinya ownership (ARCHITECTURE.md §8.2), bukan workaround.
    """
    problems = []
    for f in (GLOBALS_FILE, PASSWORDS_FILE):
        if not f.is_file():
            problems.append(f"{f} tidak ditemukan")
        elif not os.access(f, os.R_OK):
            problems.append(f"{f} tidak bisa dibaca oleh user saat ini")
    if not problems:
        return
    for p in problems:
        error(p)
    print("Perbaikan:")
    print("  - File belum ada  : jalankan ./install.sh lalu `agra genpwd`")
    print(f"  - Permission      : sudo chown -R \"$USER:$USER\" {ETC_DIR}")
    sys.exit(2)


def _extra_var_keys(raw: str) -> Set[str]:
    """Nama var dalam satu argumen -e (KEY=VALUE..., JSON/YAML, atau @file).

    Best effort: bentuk yang tidak terbaca → set kosong (urutan argv tetap
    menjamin nilai dari CLI yang menang).
    """
    raw = raw.strip()
    data: object = None
    try:
        if raw.startswith("@"):
            import yaml
            with open(Path(raw[1:]).expanduser()) as fh:
                data = yaml.safe_load(fh)
        elif raw.startswith("{"):
            import yaml
            data = yaml.safe_load(raw)
        else:
            return {tok.split("=", 1)[0] for tok in shlex.split(raw) if "=" in tok}
    except Exception:
        return set()
    return set(data) if isinstance(data, dict) else set()


def check_extra_vars_conflicts(extra_vars_raw: Optional[Iterable[str]], cli_vars: Iterable[str]) -> None:
    """Tolak -e user yang menyebut var yang ditentukan CLI (target rollback, purge, dsb.).

    Dipanggil command SEBELUM konfirmasi/precheck, dan lagi oleh
    build_ansible_command sebagai jaring pengaman.
    """
    if isinstance(extra_vars_raw, str):
        extra_vars_raw = [extra_vars_raw]
    keys: Set[str] = set()
    for raw in extra_vars_raw or []:
        keys |= _extra_var_keys(raw)
    clash = sorted(keys & set(cli_vars))
    if clash:
        raise ExtraVarsConflictError(
            "-e/--extra-vars tidak boleh menimpa var yang ditentukan agra untuk command ini: "
            + ", ".join(clash)
            + ". Gunakan flag command-nya (lihat --help), bukan -e."
        )


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
    load_etc_vars: bool = True,
) -> Tuple[List[str], Path]:
    """Build list of argv untuk ansible-playbook command.

    load_etc_vars: inject `-e @/etc/agra/globals.yml -e @/etc/agra/passwords.yml`
        (Kolla pattern, ARCHITECTURE.md §8.1). Hanya genpwd yang mematikan ini,
        karena genpwd yang membuat passwords.yml.

    Returns: (argv_list, resolved_inventory_path)
    """
    _check_ansible_available()
    if load_etc_vars:
        _check_etc_vars_readable()

    pb_path: Path
    if playbook in PLAYBOOKS:
        pb_path = PLAYBOOKS[playbook]
    else:
        pb_path = Path(playbook).expanduser()
        if not pb_path.is_absolute():
            pb_path = (Path.cwd() / pb_path).resolve()

    if not pb_path.exists():
        raise PlaybookNotFoundError(f"Playbook tidak ditemukan: {pb_path}")

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

    if load_etc_vars:
        argv += ["-e", f"@{GLOBALS_FILE}", "-e", f"@{PASSWORDS_FILE}"]

    # -e user lebih dulu, var dari CLI TERAKHIR: di Ansible -e yang belakangan
    # menang, jadi target rollback / purge / restore yang sudah ditampilkan dan
    # dikonfirmasi tidak bisa tertimpa -e (konflik yang terbaca sudah ditolak).
    if extra_vars_raw:
        check_extra_vars_conflicts(extra_vars_raw, extra_vars or {})
        for evr in extra_vars_raw:
            argv += ["--extra-vars", evr]

    if extra_vars:
        argv += ["--extra-vars", json.dumps(extra_vars, ensure_ascii=False)]

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
    load_etc_vars: bool = True,
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
        verbosity=verbosity, extra_args=extra_args, load_etc_vars=load_etc_vars,
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
