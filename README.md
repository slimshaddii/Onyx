Create a file called `README.md` in your project root (`D:\Coding\Projects\RimWorld\Onyx\README.md`):

```markdown
# Onyx Launcher

A mod manager and instance launcher for RimWorld. Provides per-instance isolation for mods, saves, and configuration, allowing multiple modpack setups to coexist without conflict.

Built with Python and PyQt6. Inspired by Prism Launcher.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![GitHub release](https://img.shields.io/github/v/release/slimshaddii/Onyx?include_prereleases)](https://github.com/slimshaddii/Onyx/releases)

---

## Features

### Instance Management
- Full per-instance isolation (mods, saves, config, logs)
- Prism-style collapsible instance groups with drag-drop
- Empty group persistence across sessions
- Instance duplication, rename, custom icons
- Playtime tracking per instance

### Mod Sorting
- Topological sort matching RimSort's accuracy
- Fully dynamic tier detection (no hardcoded mod lists)
- Dependency priority: modDependenciesForced > ByVersion > base (mutually exclusive)
- loadAfterByVersion / loadBeforeByVersion support
- Framework detection (mods depended on by 2+ others auto-promoted)
- Circular dependency handling with alphabetical fallback

### Mod Editor
- Three-panel layout: inactive mods, active mods (drag to reorder), preview
- Badge system with 6 severity levels (error, dep, warning, order, performance, info)
- Category filter chips with per-category counts
- Auto-download missing dependencies via SteamCMD
- Per-instance ignored dependency warnings
- Delete and redownload mods from within the editor
- Modlist history with timestamped snapshots, diff view, and rollback

### Save Management
- Per-instance save isolation
- Save compatibility badges (compatible, changed, missing, unknown)
- Save header parsing without loading full save data
- Auto-backup before launch with configurable retention

### Workshop Integration
- Built-in Steam Workshop browser (via QtWebEngine)
- SteamCMD-based mod downloads for non-Steam copies
- Steam Web API search (optional)

### Diagnostics
- Log viewer with search, filtering, and syntax highlighting
- Automated troubleshooter detecting 10+ known issue patterns
- Def collision scanner across active mods
- JuMLi conflict and performance database integration
- Mod search across all instances

### Modpack Sharing
- Export and import .onyx modpack files
- Includes mod list, load order, and metadata
- Auto-downloads missing mods on import

### UI
- Dark theme (default) and light theme
- Theme-aware color tokens throughout
- Keyboard shortcuts (Ctrl+S, Ctrl+Z, Ctrl+N, F5, Delete)
- Per-instance launch arguments with remember/skip dialog
- QListView with custom delegate for large mod list performance

---

## Installation

### From Release

1. Go to [Releases](https://github.com/slimshaddii/Onyx/releases)
2. Download the zip for your platform
3. Extract anywhere
4. Run `OnyxLauncher.exe` (Windows) or `OnyxLauncher` (Linux/Mac)

Linux users may need to run `chmod +x OnyxLauncher` first.

### From Source

Requirements: Python 3.13+

```bash
git clone https://github.com/slimshaddii/Onyx.git
cd Onyx
pip install -r requirements.txt
python main.py
```

### Building

```bash
pip install pyinstaller pillow
python build.py --clean
```

Output will be in `dist/OnyxLauncher-Beta/`.

---

## Usage

### First Launch

1. Onyx will auto-detect your RimWorld installation
2. If not found, go to Settings and set the RimWorld executable path
3. Onyx will offer to import your existing RimWorld data as an instance

### Creating an Instance

1. Click "Add Instance" in the toolbar
2. Name your instance
3. Open the Mod Editor to add and sort mods
4. Launch the game from the instance

### Mod Sorting

1. Open the Mod Editor for an instance
2. Activate the mods you want
3. Click "Auto-Sort" to sort based on About.xml load order rules
4. Click "Fix Issues" to resolve missing dependencies
5. Save when done

### Instance Groups

- Right-click empty space to create a group
- Right-click an instance to move it to a group
- Click a group header to collapse/expand
- Drag instances between groups

---

## Tech Stack

- Python 3.13
- PyQt6 / PyQt6-WebEngine (optional, for Workshop browser)
- toposort (topological sorting)
- SteamCMD (mod downloads, optional)
- Steam Web API (workshop search, optional)

---

## Project Structure

```
app/
  core/       # Instance management, sorting, scanning, parsing
  ui/         # PyQt6 windows, dialogs, panels
    detail/   # Instance detail sub-widgets
    modeditor/# Mod editor components
    workshop/ # Steam Workshop browser
  utils/      # File and XML utilities
data/         # App settings, conflict database
```

---

## Supported Platforms

| Platform | Status | Notes |
|----------|--------|-------|
| Windows  | Supported | Primary development platform |
| Linux    | Supported | Tested via GitHub Actions |
| macOS    | Supported | Tested via GitHub Actions |

Non-Steam copies of RimWorld are fully supported via SteamCMD for mod downloads.

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

Please keep code style consistent with the existing codebase.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

- [RimSort](https://github.com/RimSort/RimSort) for sorting algorithm reference
- [Prism Launcher](https://prismlauncher.org/) for UI design inspiration
- JuMLi for the community conflict and performance database
```

---

Also create a `LICENSE` file in the project root (`D:\Coding\Projects\RimWorld\Onyx\LICENSE`):

```
MIT License

Copyright (c) 2025 slimshaddii

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

Then commit:

```bash
git add README.md LICENSE
git commit -m "Add README and MIT license"
git push
```