# GTK3 Toolbox

Launcher für Python/GTK3-Tools, die on demand von GitHub geladen werden.

## Voraussetzungen

```bash
sudo apt install python3-gi gir1.2-gtk-3.0
```

## Starten

```bash
python3 toolbox.py
```

## Funktionsweise

- `tools.json` ist das Manifest: Liste aller Tools mit Repo-URL, Branch und Entry-Skript
- **Installieren** lädt das Repo als ZIP von GitHub (`<repo>/archive/refs/heads/<branch>.zip`) und entpackt es nach `~/.local/share/gtk3-toolbox/tools/<id>/`
- **Starten** führt das Entry-Skript mit dem System-Python aus
- **Aktualisieren** lädt neu herunter und ersetzt die alte Version
- **Entfernen** löscht das Tool-Verzeichnis

## Neues Tool hinzufügen

Eintrag in `tools.json` ergänzen:

```json
{
  "id": "mein-tool",
  "name": "Mein Tool",
  "description_de": "Beschreibung",
  "description_en": "Description",
  "repo": "https://github.com/NoCoderGHG/mein-tool",
  "branch": "main",
  "entry": "mein_tool.py",
  "available": true
}
```

`"available": false` markiert geplante Tools (ausgegraut). `"joke": true` für Scherzartikel (GUITAR).

## Features

- Hell-/Dunkel-Theme umschaltbar (persistent)
- i18n DE/EN, key-by-key-Fallback auf Englisch
- Externe Tools (Exaroton) in eigener Sektion
- Config: `~/.config/gtk3-toolbox/config.json`

## Lizenz

MIT — NoCoderGHG
