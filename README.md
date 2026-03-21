# Onyx Launcher

A mod manager and instance launcher for RimWorld. Provides true per-instance isolation for mods, saves, and configuration. Allowing multiple modpack setups to coexist without conflict.

Built with Python and PyQt6. Inspired by Prism Launcher.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![GitHub release](https://img.shields.io/github/v/release/slimshaddii/Onyx?include_prereleases)](https://github.com/slimshaddii/Onyx/releases)

---

## Features

### Instance Management
- Full per-instance isolation (mods, saves, config, logs)
- Prism-style collapsible instance groups with drag-drop between groups
- Empty group persistence across sessions
- Instance duplication, rename, custom icons and colors
- Playtime tracking per instance including sessions when launcher was closed
- Per-instance RimWorld executable override for multi-version support
- Skip launch dialog option with remembered arguments per instance

### Mod Sorting
- Topological sort matching RimSort accuracy
- Fully dynamic tier detection with no hardcoded mod lists
- Dependency priority: `modDependenciesForced` > `ByVersion` > base (mutually exclusive)
- `loadAfterByVersion` / `loadBeforeByVersion` / `incompatibleWithByVersion` support
- `alternativePackageIds` support -- alternatives satisfy dependencies
- Framework detection: mods depended on by 2+ others are auto-promoted
- Circular dependency detection with alphabetical fallback

### Mod Editor
- Three-panel layout: inactive mods, active mods (drag to reorder), preview panel
- Badge system with 6 severity levels: error, dep, warning, order, performance, info
- Category filter chips with live per-category counts
- Auto-download missing dependencies via SteamCMD with download manager
- Per-instance ignored dependency warnings with UI to manage them
- Delete and redownload mods from within the editor
- Modlist history with timestamped snapshots, diff view, and rollback
- Def collision scanner across active mods
- JuMLi conflict and performance database integration

### Mod Library
- Standalone mod library browser for all downloaded mods
- Preview image, description, author, version, size per mod
- Sort by name, last updated, oldest first
- Filter by all, has update, workshop mods, local mods
- Multi-select with Ctrl+A, bulk delete and redownload
- Auto-cleanup of empty and incomplete download folders

### Mod Update Checker
- Steam Workshop update checking via Steam API (no API key required)
- Timestamp store tracks when each mod was downloaded
- Auto-check on startup option (background, silent)
- Manual check with per-mod update indicators
- Download all updates via download manager

### Download Manager
- FDM-style persistent download manager window
- Real-time download speed and ETA per item
- File sizes pre-fetched from Steam API before download starts
- Per-item cancel and clear
- Bulk cancel all, clear done
- Auto-records download timestamps for update checking

### Steam Workshop Browser
- Built-in browser via QtWebEngine
- Download individual mods, collections (including nested collections)
- Collection download with already-installed filtering
- Downloads button opens persistent download manager
- Library button opens mod library
- Check Updates button inline
- SteamCMD or Steam native download method toggle

### Save Management
- Per-instance save isolation
- Save compatibility badges: compatible, changed, missing, unknown
- RimWorld 1.5 (gzip) and 1.6 (plain XML) save format support
- Rename and delete saves from Edit Instance
- Auto-backup before launch with configurable retention count

### Log Viewer
- Instance log takes strict priority over AppData fallback
- Search, filter by level (error, warning, info)
- Automated troubleshooter detecting 10+ known issue patterns
- Startup Analysis tab: phase timings, peak memory usage, assembly info
- Performance mod detection (Performance Optimizer, RocketMan, FasterGameLoading)
- Export summary as HTML or text

### Modpack Sharing
- Export and import `.onyx` modpack files (ZIP-based)
- Includes mod list, load order, workshop IDs, and optional config
- Auto-offers download of missing mods on import
- Workshop IDs stored on instance for Fix Issues download support

### UI
- Dark theme (default) and light theme with full theme-aware color tokens
- `get_colors()` system used throughout -- no hardcoded dark hex strings
- Keyboard shortcuts: Ctrl+S, Ctrl+Z, Ctrl+N, F5, Ctrl+R, Delete
- Per-instance launch arguments with remember/skip dialog flag
- QListView with custom delegate for large mod list performance
- Lazy badge rendering -- only visible rows are painted

---

## Installation

### From Release

1. Go to [Releases](https://github.com/slimshaddii/Onyx/releases)
2. Download the zip for your platform
3. Extract anywhere
4. Run `OnyxLauncher.exe` (Windows) or `OnyxLauncher` (Linux/Mac)

Linux and macOS users may need to run `chmod +x OnyxLauncher` first.

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

To build for all platforms automatically, push a version tag to trigger GitHub Actions:

```bash
git tag v1.0.0-beta
git push origin v1.0.0-beta
```

---

## Usage

### First Launch

1. Onyx auto-detects your RimWorld installation on startup
2. If not found, open Settings and set the RimWorld executable path
3. Onyx will offer to import your existing RimWorld data as an instance

### Creating an Instance

1. Click "Add Instance" in the toolbar
2. Name your instance and configure it
3. Open the Mod Editor to add and sort mods
4. Launch from the instance card or detail panel

### Mod Sorting

1. Open the Mod Editor for an instance
2. Activate the mods you want
3. Click "Auto-Sort" to sort based on About.xml load order rules
4. Click "Fix Issues" to detect and resolve missing dependencies
5. Save when done

### Instance Groups

- Right-click empty space in the instance grid to create a group
- Right-click an instance card to move it to a group
- Click a group header to collapse or expand it
- Drag instance cards between group sections

### Multi-Version RimWorld

Each instance can override the global RimWorld executable path, allowing different RimWorld versions to run side by side. Set this in Edit Instance > Settings > RimWorld Override.

### Mod Updates

- Click "Check Updates" in the toolbar or Workshop browser
- Set auto-check mode in Settings > Mod Updates
- Updates are detected by comparing Steam Workshop timestamps against local download timestamps

---

## Tech Stack

- Python 3.13
- PyQt6 / PyQt6-WebEngine (optional, for Workshop browser)
- `toposort` (topological sorting)
- `requests` (Steam API for update checking and collection fetching)
- SteamCMD (mod downloads, optional)
- Steam Web API (workshop search and file size pre-fetch, optional)

---

## Project Structure

```
app/
  core/         # Instance management, sorting, scanning, parsing, update checking
  ui/           # PyQt6 windows, dialogs, panels
    detail/     # Instance detail sub-widgets
    modeditor/  # Mod editor components and download manager
    workshop/   # Steam Workshop browser
  utils/        # File and XML utilities
data/           # App settings, conflict database, timestamp store
```

---

## Supported Platforms

| Platform | Status | Notes |
|---|---|---|
| Windows | Supported | Primary development platform |
| Linux | Supported | Tested via GitHub Actions, Steam Deck paths included |
| macOS | Supported | Tested via GitHub Actions |

Non-Steam copies of RimWorld are fully supported via SteamCMD for mod downloads.
Steam Deck is supported -- Flatpak and native Steam paths are auto-detected.

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

Please keep code style consistent with the existing codebase. No hardcoded colors or mod IDs.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

- [RimSort](https://github.com/RimSort/RimSort) for sorting algorithm reference
- [Prism Launcher](https://prismlauncher.org/) for UI design inspiration
- JuMLi for the community conflict and performance database