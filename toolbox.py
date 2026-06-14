#!/usr/bin/env python3
# GTK3 Toolbox Launcher
# Lädt Python/GTK3-Tools on demand von GitHub
# MIT License — NoCoderGHG

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gio

import json
import locale
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile
from pathlib import Path

APP_DIR = Path(__file__).parent
CONFIG_DIR = Path.home() / ".config" / "gtk3-toolbox"
CONFIG_FILE = CONFIG_DIR / "config.json"
TOOLS_DIR = Path.home() / ".local" / "share" / "gtk3-toolbox" / "tools"
I18N_DIR = APP_DIR / "i18n"

SUPPORTED_LANGUAGES = {
    "de": "Deutsch",
    "en": "English",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "pl": "Polski",
    "ru": "Русский",
    "tr": "Türkçe",
    "zh": "中文",
    "ja": "日本語",
}

MANIFEST_FILE = APP_DIR / "tools.json"

DEFAULT_CONFIG = {"lang": "system", "dark_theme": False, "auto_update_check": False}

VERSION_FILE_NAME = ".gtk3-toolbox-commit"


def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def detect_system_lang():
    try:
        loc = locale.getlocale()[0] or ""
    except Exception:
        loc = ""
    if not loc:
        loc = os.environ.get("LANG", "")
    code = loc.lower().split("_")[0].split(".")[0]
    if code in SUPPORTED_LANGUAGES and (I18N_DIR / f"{code}.json").exists():
        return code
    return "de" if code == "de" else "en"


def resolve_lang(setting):
    if setting == "system":
        return detect_system_lang()
    return setting


def load_i18n(lang):
    en = {}
    en_path = I18N_DIR / "en.json"
    if en_path.exists():
        with open(en_path) as f:
            en = json.load(f)
    if lang == "en":
        return en
    path = I18N_DIR / f"{lang}.json"
    if not path.exists():
        return en
    with open(path) as f:
        strings = json.load(f)
    for k, v in en.items():
        strings.setdefault(k, v)
    return strings

def build_lang_options(strings):
    """Liste (code, label) fuer das Sprachmenue. Sprachen ohne eigene
    i18n-Datei werden mit "(EN)" markiert (Fallback auf Englisch)."""
    opts = [("system", t(strings, "lang_system")),
            ("de", t(strings, "lang_de")),
            ("en", t(strings, "lang_en"))]
    for code, name in SUPPORTED_LANGUAGES.items():
        if code in ("de", "en"):
            continue
        label = name if (I18N_DIR / f"{code}.json").exists() else f"{name} (EN)"
        opts.append((code, label))
    return opts


def build_lang_lists(strings):
    """Wie build_lang_options, aber als getrennte Listen (codes, labels)."""
    codes, items = [], []
    for code, label in build_lang_options(strings):
        codes.append(code)
        items.append(label)
    return codes, items



def t(strings, key, **kwargs):
    s = strings.get(key, key)
    for k, v in kwargs.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def load_manifest():
    if not MANIFEST_FILE.exists():
        return None
    try:
        with open(MANIFEST_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def tool_install_dir(tool_id):
    return TOOLS_DIR / tool_id


def is_installed(tool):
    entry = tool_install_dir(tool["id"]) / tool["entry"]
    return entry.exists()


def repo_owner_name(repo_url):
    """https://github.com/OWNER/NAME -> (OWNER, NAME)"""
    parts = repo_url.rstrip("/").split("/")
    return parts[-2], parts[-1]


def fetch_latest_commit_sha(repo_url, branch):
    owner, name = repo_owner_name(repo_url)
    url = f"https://api.github.com/repos/{owner}/{name}/commits/{branch}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.load(resp)
    return data.get("sha")


def get_installed_commit(tool_id):
    f = tool_install_dir(tool_id) / VERSION_FILE_NAME
    if f.exists():
        try:
            return f.read_text().strip()
        except Exception:
            return None
    return None


def set_installed_commit(tool_id, sha):
    f = tool_install_dir(tool_id) / VERSION_FILE_NAME
    try:
        f.write_text(sha)
    except Exception:
        pass


def check_updates(manifest, callback):
    """Vergleicht installierte Tools mit dem aktuellen Commit auf GitHub.
    callback(results) wird im Main-Thread aufgerufen, results = Liste von
    (tool, installed_sha, latest_sha)."""
    results = []
    all_tools = list(manifest.get("tools", [])) + list(manifest.get("external", []))
    for tool in all_tools:
        repo = tool.get("repo")
        if not repo or not is_installed(tool):
            continue
        installed = get_installed_commit(tool["id"])
        if not installed:
            # Kein gespeicherter Commit (z.B. Installation vor Einfuehrung
            # des Update-Checkers) -> nicht vergleichbar, ueberspringen.
            continue
        try:
            latest = fetch_latest_commit_sha(repo, tool.get("branch", "main"))
        except Exception:
            continue
        if latest and latest != installed:
            results.append((tool, installed, latest))
    GLib.idle_add(callback, results)


def download_and_install(tool, callback):
    tool_id = tool["id"]
    repo = tool["repo"].rstrip("/")
    branch = tool.get("branch", "main")
    zip_url = f"{repo}/archive/refs/heads/{branch}.zip"
    dest = tool_install_dir(tool_id)
    tmp_zip = TOOLS_DIR / f"{tool_id}.zip"

    try:
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(zip_url, tmp_zip)

        if dest.exists():
            shutil.rmtree(dest)

        with zipfile.ZipFile(tmp_zip) as zf:
            names = zf.namelist()
            root = names[0].split("/")[0] if names else None
            extract_tmp = TOOLS_DIR / f"{tool_id}_tmp"
            if extract_tmp.exists():
                shutil.rmtree(extract_tmp)
            zf.extractall(extract_tmp)
            if root and (extract_tmp / root).is_dir():
                shutil.move(str(extract_tmp / root), str(dest))
                shutil.rmtree(extract_tmp, ignore_errors=True)
            else:
                shutil.move(str(extract_tmp), str(dest))

        tmp_zip.unlink(missing_ok=True)

        # Aktuellen Commit-Hash merken, fuer spaetere Update-Checks.
        try:
            sha = fetch_latest_commit_sha(repo, branch)
            if sha:
                set_installed_commit(tool_id, sha)
        except Exception:
            pass

        GLib.idle_add(callback, tool, True, "")
    except Exception as e:
        tmp_zip.unlink(missing_ok=True)
        GLib.idle_add(callback, tool, False, str(e))


def launch_tool(tool):
    entry = tool_install_dir(tool["id"]) / tool["entry"]
    subprocess.Popen([sys.executable, str(entry)], cwd=str(entry.parent))


class ToolRow(Gtk.ListBoxRow):
    def __init__(self, tool, strings, lang, on_action, external=False):
        super().__init__()
        self.tool = tool
        self.strings = strings
        self.on_action = on_action
        self.external = external

        box = Gtk.Box(spacing=12)
        box.set_border_width(10)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box = Gtk.Box(spacing=8)
        lbl_name = Gtk.Label()
        lbl_name.set_markup(f"<b>{GLib.markup_escape_text(tool['name'])}</b>")
        lbl_name.set_xalign(0)
        title_box.pack_start(lbl_name, False, False, 0)

        if tool.get("joke"):
            badge = Gtk.Label(label=t(strings, "badge_joke"))
            badge.get_style_context().add_class("dim-label")
            title_box.pack_start(badge, False, False, 0)
        if external:
            badge = Gtk.Label(label=t(strings, "badge_external"))
            badge.get_style_context().add_class("dim-label")
            title_box.pack_start(badge, False, False, 0)
        if not tool.get("available", True) and not external:
            badge = Gtk.Label(label=t(strings, "badge_not_available"))
            badge.get_style_context().add_class("dim-label")
            title_box.pack_start(badge, False, False, 0)

        vbox.pack_start(title_box, False, False, 0)

        desc_key = f"description_{lang}"
        desc = tool.get(desc_key) or tool.get("description_en", "")
        lbl_desc = Gtk.Label(label=desc)
        lbl_desc.set_xalign(0)
        lbl_desc.get_style_context().add_class("dim-label")
        lbl_desc.set_line_wrap(True)
        vbox.pack_start(lbl_desc, False, False, 0)

        box.pack_start(vbox, True, True, 0)

        self.btn_box = Gtk.Box(spacing=6)
        box.pack_end(self.btn_box, False, False, 0)
        self.add(box)
        self.refresh_buttons()

    def refresh_buttons(self):
        for child in self.btn_box.get_children():
            self.btn_box.remove(child)

        available = self.tool.get("available", True) or self.external
        installed = is_installed(self.tool)

        if not available:
            self.set_sensitive(False)
        elif installed:
            btn_launch = Gtk.Button(label=t(self.strings, "btn_launch"))
            btn_launch.get_style_context().add_class("suggested-action")
            btn_launch.connect("clicked", lambda b: self.on_action("launch", self))
            btn_update = Gtk.Button(label=t(self.strings, "btn_update"))
            btn_update.connect("clicked", lambda b: self.on_action("install", self))
            btn_remove = Gtk.Button(label=t(self.strings, "btn_remove"))
            btn_remove.connect("clicked", lambda b: self.on_action("remove", self))
            self.btn_box.pack_start(btn_launch, False, False, 0)
            self.btn_box.pack_start(btn_update, False, False, 0)
            self.btn_box.pack_start(btn_remove, False, False, 0)
        else:
            btn_install = Gtk.Button(label=t(self.strings, "btn_install"))
            btn_install.connect("clicked", lambda b: self.on_action("install", self))
            self.btn_box.pack_start(btn_install, False, False, 0)

        self.btn_box.show_all()


class UpdateDialog(Gtk.Dialog):
    """Zeigt Tools mit verfuegbaren Updates (alter -> neuer Commit) zur Auswahl."""

    def __init__(self, parent, strings, results):
        super().__init__(title=t(strings, "update_dialog_title"), transient_for=parent, flags=0)
        self.add_buttons(
            t(strings, "update_later"), Gtk.ResponseType.CANCEL,
            t(strings, "update_now"), Gtk.ResponseType.OK,
        )
        self.set_default_size(420, -1)

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)

        lbl = Gtk.Label(label=t(strings, "update_dialog_text"))
        lbl.set_xalign(0)
        lbl.set_line_wrap(True)
        box.pack_start(lbl, False, False, 0)

        self._checks = []
        for tool, old_sha, new_sha in results:
            cb = Gtk.CheckButton(
                label=f"{tool['name']}  ({old_sha[:7]} \u2192 {new_sha[:7]})"
            )
            cb.set_active(True)
            box.pack_start(cb, False, False, 0)
            self._checks.append((cb, tool))

        box.show_all()

    def selected_tools(self):
        return [tool for cb, tool in self._checks if cb.get_active()]


class ToolboxLauncher(Gtk.Window):
    def __init__(self):
        super().__init__(title="GTK3 Toolbox")
        self.set_default_size(640, 600)

        self.cfg = load_config()
        self.strings = load_i18n(resolve_lang(self.cfg.get("lang", "system")))
        self.manifest = load_manifest()
        self.rows = {}

        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-application-prefer-dark-theme", self.cfg.get("dark_theme", False))

        self._build_ui()

        if self.cfg.get("auto_update_check", False):
            self._run_update_check(manual=False)

    def _build_ui(self):
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = t(self.strings, "app_title")
        self.set_titlebar(header)

        btn_theme = Gtk.Button()
        icon = Gio.ThemedIcon(name="weather-clear-night-symbolic")
        btn_theme.add(Gtk.Image.new_from_gicon(icon, Gtk.IconSize.BUTTON))
        btn_theme.set_tooltip_text(t(self.strings, "btn_theme"))
        btn_theme.connect("clicked", self._on_theme_toggle)
        header.pack_end(btn_theme)

        btn_check_updates = Gtk.Button()
        icon_update = Gio.ThemedIcon(name="view-refresh-symbolic")
        btn_check_updates.add(Gtk.Image.new_from_gicon(icon_update, Gtk.IconSize.BUTTON))
        btn_check_updates.set_tooltip_text(t(self.strings, "btn_check_updates"))
        btn_check_updates.connect("clicked", lambda b: self._run_update_check(manual=True))
        header.pack_end(btn_check_updates)

        chk_auto_update = Gtk.CheckButton(label=t(self.strings, "chk_auto_update"))
        chk_auto_update.set_active(self.cfg.get("auto_update_check", False))
        chk_auto_update.connect("toggled", self._on_auto_update_toggled)
        header.pack_end(chk_auto_update)

        lang_combo = Gtk.ComboBoxText()
        for code, label in build_lang_options(self.strings):
            lang_combo.append(code, label)
        lang_combo.set_active_id(self.cfg.get("lang", "system"))
        lang_combo.connect("changed", self._on_lang_changed)
        header.pack_end(lang_combo)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        vbox.pack_start(scroll, True, True, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_border_width(12)
        scroll.add(content)

        if self.manifest is None:
            lbl = Gtk.Label(label=t(self.strings, "manifest_error"))
            content.pack_start(lbl, False, False, 12)
        else:
            lang = self.cfg.get("lang", "de")

            lbl_tools = Gtk.Label()
            lbl_tools.set_markup(f"<b>{t(self.strings, 'section_tools')}</b>")
            lbl_tools.set_xalign(0)
            content.pack_start(lbl_tools, False, False, 4)

            listbox = Gtk.ListBox()
            listbox.set_selection_mode(Gtk.SelectionMode.NONE)
            for tool in self.manifest.get("tools", []):
                row = ToolRow(tool, self.strings, lang, self._on_tool_action)
                self.rows[tool["id"]] = row
                listbox.add(row)
            content.pack_start(listbox, False, False, 0)

            ext = self.manifest.get("external", [])
            if ext:
                lbl_ext = Gtk.Label()
                lbl_ext.set_markup(f"<b>{t(self.strings, 'section_external')}</b>")
                lbl_ext.set_xalign(0)
                content.pack_start(lbl_ext, False, False, 4)

                listbox_ext = Gtk.ListBox()
                listbox_ext.set_selection_mode(Gtk.SelectionMode.NONE)
                for tool in ext:
                    row = ToolRow(tool, self.strings, lang, self._on_tool_action, external=True)
                    self.rows[tool["id"]] = row
                    listbox_ext.add(row)
                content.pack_start(listbox_ext, False, False, 0)

        self.statusbar = Gtk.Statusbar()
        self.status_ctx = self.statusbar.get_context_id("main")
        vbox.pack_end(self.statusbar, False, False, 0)

    def _status(self, msg):
        self.statusbar.pop(self.status_ctx)
        self.statusbar.push(self.status_ctx, msg)

    def _on_tool_action(self, action, row):
        tool = row.tool
        if action == "install":
            self._status(t(self.strings, "status_installing", name=tool["name"]))
            row.set_sensitive(False)
            thread = threading.Thread(
                target=download_and_install,
                args=(tool, lambda tl, ok, err: self._on_install_done(row, ok, err)),
                daemon=True,
            )
            thread.start()
        elif action == "launch":
            try:
                self._status(t(self.strings, "status_launching", name=tool["name"]))
                launch_tool(tool)
            except Exception as e:
                self._status(t(self.strings, "status_launch_failed", error=e))
        elif action == "remove":
            dialog = Gtk.MessageDialog(
                parent=self,
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=t(self.strings, "confirm_remove", name=tool["name"]),
            )
            if dialog.run() == Gtk.ResponseType.YES:
                shutil.rmtree(tool_install_dir(tool["id"]), ignore_errors=True)
                self._status(t(self.strings, "status_removed", name=tool["name"]))
                row.refresh_buttons()
            dialog.destroy()

    def _on_install_done(self, row, ok, err):
        row.set_sensitive(True)
        if ok:
            self._status(t(self.strings, "status_installed", name=row.tool["name"]))
        else:
            self._status(t(self.strings, "status_install_failed", error=err))
        row.refresh_buttons()

    def _on_theme_toggle(self, _):
        self.cfg["dark_theme"] = not self.cfg.get("dark_theme", False)
        save_config(self.cfg)
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-application-prefer-dark-theme", self.cfg["dark_theme"])

    def _on_auto_update_toggled(self, btn):
        self.cfg["auto_update_check"] = btn.get_active()
        save_config(self.cfg)

    def _run_update_check(self, manual=False):
        if self.manifest is None:
            return
        if manual:
            self._status(t(self.strings, "status_checking_updates"))
        thread = threading.Thread(
            target=check_updates,
            args=(self.manifest, lambda results: self._on_update_check_done(results, manual)),
            daemon=True,
        )
        thread.start()

    def _on_update_check_done(self, results, manual):
        if not results:
            if manual:
                self._status(t(self.strings, "status_no_updates"))
            return

        dlg = UpdateDialog(self, self.strings, results)
        response = dlg.run()
        selected = dlg.selected_tools() if response == Gtk.ResponseType.OK else []
        dlg.destroy()

        for tool in selected:
            row = self.rows.get(tool["id"])
            if row:
                row.set_sensitive(False)
            self._status(t(self.strings, "status_installing", name=tool["name"]))
            threading.Thread(
                target=download_and_install,
                args=(tool, lambda tl, ok, err, r=row: self._on_install_done(r, ok, err) if r else None),
                daemon=True,
            ).start()

    def _on_lang_changed(self, combo):
        new_lang = combo.get_active_id()
        if new_lang and new_lang != self.cfg.get("lang"):
            self.cfg["lang"] = new_lang
            save_config(self.cfg)
            new_strings = load_i18n(resolve_lang(new_lang))
            dialog = Gtk.MessageDialog(
                parent=self,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text=t(new_strings, "restart_hint"),
            )
            dialog.run()
            dialog.destroy()


def main():
    win = ToolboxLauncher()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
