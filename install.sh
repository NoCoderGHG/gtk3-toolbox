#!/bin/bash
#
# Installer for GTK3 Toolbox.
# Copies the app to ~/.local/share/gtk3-toolbox/, installs launcher and desktop entry.
#
# Run from inside the repo root:
#   ./install.sh

set -e

REPO_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

APP_SRC="$REPO_DIR/toolbox.py"
I18N_SRC="$REPO_DIR/i18n"
TOOLS_JSON_SRC="$REPO_DIR/tools.json"
LAUNCHER_SRC="$REPO_DIR/gtk3-toolbox"
DESKTOP_SRC="$REPO_DIR/gtk3-toolbox.desktop"

APP_DST_DIR="$HOME/.local/share/gtk3-toolbox"
LAUNCHER_DST="$HOME/.local/bin/gtk3-toolbox"
DESKTOP_DST="$HOME/.local/share/applications/gtk3-toolbox.desktop"

# Color helpers
if [[ -t 1 ]]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    DIM='\033[2m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN=''; YELLOW=''; RED=''; DIM=''; BOLD=''; NC=''
fi

info()  { echo -e "${GREEN}→${NC} $1"; }
warn()  { echo -e "${YELLOW}!${NC} $1"; }
err()   { echo -e "${RED}✗${NC} $1"; }
note()  { echo -e "${DIM}  $1${NC}"; }

ask_yes_no() {
    local prompt="$1" default="${2:-n}" hint
    [[ "$default" == "y" ]] && hint="[Y/n]" || hint="[y/N]"
    while true; do
        read -r -p "$prompt $hint " answer
        answer="${answer:-$default}"
        case "${answer,,}" in
            y|yes|j|ja) return 0 ;;
            n|no|nein)  return 1 ;;
            *) echo "Please answer yes or no." ;;
        esac
    done
}

echo
echo -e "${BOLD}GTK3 Toolbox — Installer${NC}"
echo

# === Sanity check ===
MISSING=0
[[ ! -f "$APP_SRC" ]]        && err "Missing: $APP_SRC"        && MISSING=1
[[ ! -d "$I18N_SRC" ]]       && err "Missing: $I18N_SRC"       && MISSING=1
[[ ! -f "$TOOLS_JSON_SRC" ]] && err "Missing: $TOOLS_JSON_SRC" && MISSING=1
[[ ! -f "$LAUNCHER_SRC" ]]   && err "Missing: $LAUNCHER_SRC"   && MISSING=1
[[ ! -f "$DESKTOP_SRC" ]]    && err "Missing: $DESKTOP_SRC"    && MISSING=1
if [[ $MISSING -eq 1 ]]; then
    err "Repository structure is incomplete. Run this script from the repo root."
    exit 1
fi

# === Check dependencies ===
info "Checking dependencies…"

MISSING_DEPS=()

command -v python3 > /dev/null 2>&1 || MISSING_DEPS+=("python3")

if ! python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>/dev/null; then
    MISSING_DEPS+=("python3-gi" "gir1.2-gtk-3.0")
fi

if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    err "Missing system packages:"
    for dep in "${MISSING_DEPS[@]}"; do
        echo "    - $dep"
    done
    echo
    note "On Debian/Ubuntu/Mint, install with:"
    echo "    sudo apt install ${MISSING_DEPS[*]}"
    echo
    if ! ask_yes_no "Continue installation anyway?" "n"; then
        exit 1
    fi
else
    note "All dependencies present."
fi

# === Stop running instance ===
if pgrep -u "$USER" -f "toolbox.py" > /dev/null 2>&1; then
    info "Stopping running instance…"
    pkill -u "$USER" -f "toolbox.py" 2>/dev/null || true
    sleep 0.3
fi

# === Detect existing installation ===
EXISTING=0
[[ -d "$APP_DST_DIR" ]]  && EXISTING=1
[[ -f "$LAUNCHER_DST" ]] && EXISTING=1
[[ -f "$DESKTOP_DST" ]]  && EXISTING=1

if [[ $EXISTING -eq 1 ]]; then
    warn "An existing installation was detected."
    note "Existing files will be overwritten. User configuration in"
    note "  ~/.config/gtk3-toolbox/  and installed tools in"
    note "  ~/.local/share/gtk3-toolbox/tools/  will not be touched."
    echo
    if ! ask_yes_no "Continue?" "y"; then
        echo "Aborted."
        exit 0
    fi
fi

# === Install app ===
info "Installing app to $APP_DST_DIR"
mkdir -p "$APP_DST_DIR"
cp "$APP_SRC" "$APP_DST_DIR/toolbox.py"
cp "$TOOLS_JSON_SRC" "$APP_DST_DIR/tools.json"

info "Installing i18n files"
mkdir -p "$APP_DST_DIR/i18n"
cp "$I18N_SRC/"*.json "$APP_DST_DIR/i18n/"

# === Record current commit for self-update check ===
COMMIT_SHA=$(python3 -c "
import urllib.request, json
try:
    req = urllib.request.Request(
        'https://api.github.com/repos/NoCoderGHG/gtk3-toolbox/commits/main',
        headers={'Accept': 'application/vnd.github+json'}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        print(json.load(r).get('sha', ''))
except Exception:
    print('')
" 2>/dev/null)
if [[ -n "$COMMIT_SHA" ]]; then
    echo "$COMMIT_SHA" > "$APP_DST_DIR/.gtk3-toolbox-commit"
    note "Recorded commit: ${COMMIT_SHA:0:7}"
fi

# === Install launcher ===
info "Installing launcher to $LAUNCHER_DST"
mkdir -p "$(dirname "$LAUNCHER_DST")"
cp "$LAUNCHER_SRC" "$LAUNCHER_DST"
chmod +x "$LAUNCHER_DST"

# === Install desktop entry ===
info "Installing desktop entry to $DESKTOP_DST"
mkdir -p "$(dirname "$DESKTOP_DST")"
sed "s|__LAUNCHER_PATH__|$LAUNCHER_DST|g" "$DESKTOP_SRC" > "$DESKTOP_DST"

if command -v update-desktop-database > /dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications/" 2>/dev/null || true
fi

( kbuildsycoca5 2>/dev/null || kbuildsycoca6 2>/dev/null ) || true

echo
echo -e "${GREEN}${BOLD}✅ Installation complete.${NC}"
echo
note "Start the app from your application menu, or run:"
note "  gtk3-toolbox"
note ""
note "If 'gtk3-toolbox' is not found, ensure ~/.local/bin is in your PATH:"
note "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
echo
