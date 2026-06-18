#!/bin/bash
#
# Uninstaller for GTK3 Toolbox.
# Removes the installed app, launcher, desktop entry, and (optionally)
# the user configuration and downloaded tools.

set -e

APP_DIR="$HOME/.local/share/gtk3-toolbox"
TOOLS_DIR="$APP_DIR/tools"
LAUNCHER="$HOME/.local/bin/gtk3-toolbox"
DESKTOP_FILE="$HOME/.local/share/applications/gtk3-toolbox.desktop"
CONFIG_DIR="$HOME/.config/gtk3-toolbox"

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
echo -e "${BOLD}GTK3 Toolbox — Uninstaller${NC}"
echo

FOUND=0
[[ -d "$APP_DIR" ]]      && FOUND=1
[[ -f "$LAUNCHER" ]]     && FOUND=1
[[ -f "$DESKTOP_FILE" ]] && FOUND=1

if [[ $FOUND -eq 0 ]]; then
    warn "Nothing to uninstall — no installation found in standard locations."
    note "Checked:"
    note "  $APP_DIR"
    note "  $LAUNCHER"
    note "  $DESKTOP_FILE"
    exit 0
fi

# Stop running instance
if pgrep -u "$USER" -f "toolbox.py" > /dev/null 2>&1; then
    info "Stopping running instance…"
    pkill -u "$USER" -f "toolbox.py" 2>/dev/null || true
    sleep 0.3
fi

# Remove launcher
if [[ -f "$LAUNCHER" ]]; then
    info "Removing launcher: $LAUNCHER"
    rm -f "$LAUNCHER"
fi

# Remove desktop entry
if [[ -f "$DESKTOP_FILE" ]]; then
    info "Removing desktop entry: $DESKTOP_FILE"
    rm -f "$DESKTOP_FILE"
    if command -v update-desktop-database > /dev/null 2>&1; then
        update-desktop-database "$HOME/.local/share/applications/" 2>/dev/null || true
    fi
fi

# Optionally remove downloaded tools
if [[ -d "$TOOLS_DIR" ]]; then
    echo
    warn "Downloaded tools found at: $TOOLS_DIR"
    note "This contains all tools installed via the Toolbox."
    if ask_yes_no "Remove downloaded tools as well?" "n"; then
        info "Removing downloaded tools…"
        rm -rf "$TOOLS_DIR"
        note "Tools removed."
    else
        note "Tools kept at $TOOLS_DIR"
    fi
fi

# Remove app directory (toolbox.py, tools.json, i18n — but not tools/ if kept)
if [[ -d "$APP_DIR" ]]; then
    info "Removing app directory: $APP_DIR"
    rm -rf "$APP_DIR"
fi

# Optionally remove user config
if [[ -d "$CONFIG_DIR" ]]; then
    echo
    warn "User configuration found at: $CONFIG_DIR"
    note "This contains your language settings and preferences."
    if ask_yes_no "Remove user configuration as well?" "n"; then
        info "Removing user configuration…"
        rm -rf "$CONFIG_DIR"
        note "Configuration removed."
    else
        note "Configuration kept. You can remove it manually later if needed."
    fi
fi

( kbuildsycoca5 2>/dev/null || kbuildsycoca6 2>/dev/null ) || true

echo
echo -e "${GREEN}${BOLD}✅ Uninstall complete.${NC}"
echo
