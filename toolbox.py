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

DEFAULT_CONFIG = {"lang": "system", "dark_theme": False}


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


class ToolboxLauncher(Gtk.Window):
    def __init__(self):
        super().__init__(title="GTK3 Toolbox")
        self.set_default_size(640, 600)

        self.cfg = load_config()
        self.strings = load_i18n(resolve_lang(self.cfg.get("lang", "system")))
        self.manifest = load_manifest()

        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-application-prefer-dark-theme", self.cfg.get("dark_theme", False))

        self._build_ui()

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
                listbox.add(ToolRow(tool, self.strings, lang, self._on_tool_action))
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
                    listbox_ext.add(ToolRow(tool, self.strings, lang, self._on_tool_action, external=True))
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
