#!/bin/bash
# Install agra di control node, sebagai operator user (bukan sudo).
#
#   ./install.sh                 # venv ~/.local/share/agra/venv + /etc/agra
#   AGRA_VENV=/opt/agra ./install.sh
#
# - Jalankan sebagai OPERATOR user (bukan `sudo ./install.sh`): /etc/agra dan
#   venv dimiliki user ini; sudo hanya dipakai untuk membuat /etc/agra.
# - Boleh dijalankan dari direktori mana pun dan berulang kali (idempotent).
# - pip TIDAK pernah menyentuh Python sistem (PEP 668): selalu ke venv — venv
#   yang sedang aktif ($VIRTUAL_ENV) atau $AGRA_VENV.

# `sh install.sh` (dash di Debian/Ubuntu) tidak mengenal pipefail/BASH_SOURCE:
# jalankan ulang dengan bash. Sengaja POSIX sampai baris exec ini.
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
ETC_SRC="$REPO_DIR/etc/agra"
AGRA_ETC=/etc/agra

if [ "$(id -u)" -eq 0 ]; then
    echo "ERROR: jangan jalankan install.sh sebagai root/sudo." >&2
    echo "       Jalankan sebagai operator user: ./install.sh (sudo diminta hanya untuk $AGRA_ETC)." >&2
    exit 1
fi

# ── Python venv + agra (ansible-core ikut sebagai dependency) ──
# ansible-core >= 2.16 butuh Python >= 3.10 di control node: RHEL/Rocky 9
# membawa python3 = 3.9, jadi pilih interpreter terbaru yang tersedia.
find_python() {
    local py
    for py in ${AGRA_PYTHON:-} python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$py" >/dev/null 2>&1 \
            && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
            command -v "$py"
            return 0
        fi
    done
    return 1
}

if [ -n "${VIRTUAL_ENV:-}" ]; then
    VENV="$VIRTUAL_ENV"
    echo "Pakai venv aktif: $VENV"
else
    VENV="${AGRA_VENV:-$HOME/.local/share/agra/venv}"
    if [ ! -x "$VENV/bin/python" ]; then
        if ! PYTHON="$(find_python)"; then
            echo "ERROR: butuh Python >= 3.10 (ansible-core). Install dulu, mis.:" >&2
            echo "       RHEL/Rocky 9 : sudo dnf install python3.12" >&2
            echo "       Debian/Ubuntu: sudo apt install python3 python3-venv" >&2
            echo "       Atau set AGRA_PYTHON=/path/python3.x" >&2
            exit 1
        fi
        echo "Membuat venv: $VENV ($("$PYTHON" --version))"
        if ! "$PYTHON" -m venv "$VENV"; then
            echo "ERROR: $PYTHON -m venv gagal. Debian/Ubuntu: sudo apt install python3-venv" >&2
            exit 1
        fi
    fi
fi
if ! "$VENV/bin/python" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    echo "ERROR: $VENV memakai $("$VENV/bin/python" --version); agra butuh Python >= 3.10." >&2
    exit 1
fi
"$VENV/bin/python" -m pip install --upgrade pip
# Editable: checkout repo ini yang dipakai (git pull = update agra).
"$VENV/bin/python" -m pip install -e "$REPO_DIR"

# `agra` di PATH tanpa activate venv.
BIN_DIR="$HOME/.local/bin"
if [ -z "${VIRTUAL_ENV:-}" ]; then
    mkdir -p "$BIN_DIR"
    ln -sfn "$VENV/bin/agra" "$BIN_DIR/agra"
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *)
            # Tambahkan ke rc file shell login user — sekali saja (penanda
            # di bawah), jadi install.sh tetap idempotent.
            case "$(basename "${SHELL:-bash}")" in
                zsh) SHELL_RC="$HOME/.zshrc" ;;
                bash) SHELL_RC="$HOME/.bashrc" ;;
                *) SHELL_RC="$HOME/.profile" ;;
            esac
            PATH_MARKER="# agra: ~/.local/bin di PATH (install.sh)"
            if [ -n "${AGRA_NO_MODIFY_PATH:-}" ]; then
                echo "WARNING: $BIN_DIR belum ada di PATH — tambahkan ke $SHELL_RC: export PATH=\"$BIN_DIR:\$PATH\""
            else
                if ! grep -qxF "$PATH_MARKER" "$SHELL_RC" 2>/dev/null; then
                    printf '\n%s\nexport PATH="$HOME/.local/bin:$PATH"\n' "$PATH_MARKER" >> "$SHELL_RC"
                    echo "PATH: $BIN_DIR ditambahkan ke $SHELL_RC"
                fi
                PATH_HINT="source $SHELL_RC"
            fi
            ;;
    esac
fi

# ── /etc/agra (pola /etc/kolla): dimiliki operator user ──
AGRA_OPERATOR="$(id -un)"
AGRA_OPERATOR_GROUP="$(id -gn)"

sudo mkdir -p "$AGRA_ETC/config" "$AGRA_ETC/ssl"
sudo chown -R "$AGRA_OPERATOR:$AGRA_OPERATOR_GROUP" "$AGRA_ETC"
chmod 0750 "$AGRA_ETC" "$AGRA_ETC/config" "$AGRA_ETC/ssl"

# Template default — TIDAK menimpa file yang sudah ada.
[ -f "$AGRA_ETC/globals.yml" ] || install -m 0640 "$ETC_SRC/globals.yml" "$AGRA_ETC/globals.yml"
[ -f "$AGRA_ETC/passwords.yml" ] || install -m 0600 "$ETC_SRC/passwords.yml.example" "$AGRA_ETC/passwords.yml"
# Override config default: salin file yang belum ada saja (tanpa cp -n,
# yang perilakunya berbeda antar versi coreutils).
(cd "$ETC_SRC/config" && find . -type f) | while read -r f; do
    [ -e "$AGRA_ETC/config/$f" ] || install -D -m 0640 "$ETC_SRC/config/$f" "$AGRA_ETC/config/$f"
done

chmod 0640 "$AGRA_ETC/globals.yml"
chmod 0600 "$AGRA_ETC/passwords.yml"
if [ -f "$AGRA_ETC/ssl/agra.key" ]; then chmod 0600 "$AGRA_ETC/ssl/agra.key"; fi

echo "$AGRA_ETC owned by $AGRA_OPERATOR:$AGRA_OPERATOR_GROUP"
echo "agra: $("$VENV/bin/agra" --version)"
echo "Next:"
if [ -n "${PATH_HINT:-}" ]; then
    echo "  0. $PATH_HINT        # atau buka terminal baru, supaya \`agra\` ada di PATH"
fi
echo "  1. edit $AGRA_ETC/globals.yml"
echo "  2. agra genpwd                 # isi secret yang masih kosong di $AGRA_ETC/passwords.yml"
echo "  3. agra check -i <inventory>"
