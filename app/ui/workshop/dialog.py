"""Main workshop browser dialog."""

import re
import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QMessageBox, QWidget, QComboBox, QApplication
)
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QFont

from app.core.steamcmd import SteamCMDManager, DownloadQueue
from app.core.workshop import fetch_details_sync
from app.core.steam_integration import DownloadMethod, subscribe_via_steam, open_workshop_page
from app.core.mod_linker import link_mod_to_game, delete_downloaded_mod
from app.core.rimworld import ModInfo

from app.ui.workshop.sidebar import DownloadSidebar
from app.ui.workshop.js_inject import INJECT_JS
from app.ui.workshop.web_page import HAS_WE, WE_ERROR

if HAS_WE:
    from app.ui.workshop.web_page import OnyxPage, QWebEngineView, QWebEngineProfile, QWebEngineSettings

WORKSHOP_BROWSE = (
    "https://steamcommunity.com/workshop/browse/?appid=294100"
    "&browsesort=trend&section=readytouseitems")
WORKSHOP_HOME = "https://steamcommunity.com/app/294100/workshop/"


class WorkshopBrowserDialog(QDialog):
    def __init__(self, parent, steamcmd: SteamCMDManager, rw=None,
                 api_key='', installed_workshop_ids=None,
                 download_method=DownloadMethod.STEAMCMD,
                 is_steam_copy=False, settings=None):
        super().__init__(None)
        self.steamcmd = steamcmd
        self.rw = rw
        self.installed_ids = set(installed_workshop_ids or set())
        self.download_method = download_method
        self._settings = settings or {}
        self._browser = None
        self._inject_ver = 0

        self._dlq = DownloadQueue(
            steamcmd_path=steamcmd.steamcmd_path,
            destination=steamcmd.mods_destination,
            max_concurrent=3,
            username=self._settings.get('steamcmd_username', ''))
        self._dlq.job_started.connect(self._on_started)
        self._dlq.job_progress.connect(self._on_progress)
        self._dlq.job_finished.connect(self._on_finished)

        self.setWindowTitle("Steam Workshop — Onyx")
        self.setMinimumSize(1000, 560)
        self.resize(1200, 700)

        can = HAS_WE
        if can:
            app = QApplication.instance()
            if app and app.property("webengine_available") is False:
                can = False
        if can:
            try:
                self._build_with_browser()
            except Exception as e:
                print(f"[Workshop] WebEngine failed: {e}")
                can = False
        if not can:
            self._build_fallback()

    # ── Build ────────────────────────────────────────────────────

    def _build_fallback(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)
        lo.addWidget(self._make_nav())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        self.sidebar = DownloadSidebar(self)
        self.sidebar.delete_mod.connect(self._handle_delete)
        self._refresh_sidebar()
        body.addWidget(self.sidebar)
        msg = QLabel(f"WebEngine unavailable — {WE_ERROR or 'pip install PyQt6-WebEngine'}\n"
                     "Enter a mod ID in the address bar.")
        msg.setStyleSheet("padding:24px;color:#aaa;")
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(msg, 1)
        bw = QWidget()
        bw.setLayout(body)
        lo.addWidget(bw, 1)
        lo.addWidget(self._make_status())

    def _build_with_browser(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)
        lo.addWidget(self._make_nav())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.sidebar = DownloadSidebar(self)
        self.sidebar.delete_mod.connect(self._handle_delete)
        self._refresh_sidebar()
        body.addWidget(self.sidebar)

        profile = QWebEngineProfile.defaultProfile()
        s = profile.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)

        self._page = OnyxPage(profile, self)
        self._page.onyx_download.connect(self._download)

        self._browser = QWebEngineView(self)
        self._browser.setPage(self._page)
        self._browser.loadStarted.connect(lambda: self.status_lbl.setText("Loading…"))
        self._browser.loadFinished.connect(self._on_loaded)
        self._browser.urlChanged.connect(self._on_url)
        body.addWidget(self._browser, 1)

        bw = QWidget()
        bw.setLayout(body)
        lo.addWidget(bw, 1)
        lo.addWidget(self._make_status())
        self._browser.load(QUrl(WORKSHOP_BROWSE))

    # ── Nav bar ──────────────────────────────────────────────────

    def _make_nav(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#12121f;border-bottom:1px solid #252540;")
        lo = QHBoxLayout(w)
        lo.setContentsMargins(6, 4, 6, 4)
        lo.setSpacing(3)

        if HAS_WE:
            for text, tip, fn in [
                ("Back", "Go back", lambda: self._browser and self._browser.back()),
                ("Fwd", "Go forward", lambda: self._browser and self._browser.forward()),
                ("Reload", "Reload page", lambda: self._browser and self._browser.reload()),
            ]:
                b = QPushButton(text)
                b.setToolTip(tip)
                b.setFixedHeight(26)
                b.setStyleSheet("font-size:10px;padding:2px 8px;")
                b.clicked.connect(fn)
                lo.addWidget(b)

        home = QPushButton("Home")
        home.setFixedHeight(26)
        home.setStyleSheet("font-size:10px;padding:2px 8px;")
        home.clicked.connect(self._go_home)
        lo.addWidget(home)

        self.addr = QLineEdit(WORKSHOP_HOME)
        self.addr.setObjectName("addressBar")
        self.addr.setPlaceholderText("URL, mod ID, or search…")
        self.addr.returnPressed.connect(self._navigate)
        lo.addWidget(self.addr, 1)

        go = QPushButton("Go")
        go.setObjectName("primaryButton")
        go.setFixedHeight(26)
        go.setStyleSheet("font-size:10px;padding:2px 10px;")
        go.clicked.connect(self._navigate)
        lo.addWidget(go)

        lo.addWidget(QLabel("│"))

        self.method_cb = QComboBox()
        self.method_cb.addItem("SteamCMD", "steamcmd")
        self.method_cb.addItem("Steam", "steam_native")
        self.method_cb.setCurrentIndex(
            1 if self.download_method == DownloadMethod.STEAM_NATIVE else 0)
        self.method_cb.setFixedWidth(100)
        lo.addWidget(self.method_cb)

        return w

    def _make_status(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#0e0e1a;border-top:1px solid #1a1a30;")
        w.setFixedHeight(24)
        lo = QHBoxLayout(w)
        lo.setContentsMargins(10, 0, 10, 0)
        self.status_lbl = QLabel("Ready")
        self.status_lbl.setStyleSheet("color:#555;font-size:10px;")
        lo.addWidget(self.status_lbl, 1)
        self.inst_lbl = QLabel(f"{len(self.installed_ids)} installed")
        self.inst_lbl.setStyleSheet("color:#4CAF50;font-size:10px;")
        lo.addWidget(self.inst_lbl)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        lo.addWidget(close_btn)
        return w

    # ── Navigation ───────────────────────────────────────────────

    def _go_home(self):
        if self._browser:
            self._browser.load(QUrl(WORKSHOP_BROWSE))
        self.addr.setText(WORKSHOP_HOME)

    def _navigate(self):
        t = self.addr.text().strip()
        if not t or t == WORKSHOP_HOME:
            self._go_home()
            return
        if not self._browser:
            return
        if t.startswith('http'):
            self._browser.load(QUrl(t))
        elif t.isdigit():
            self._browser.load(QUrl(f"https://steamcommunity.com/sharedfiles/filedetails/?id={t}"))
        elif re.search(r'id=(\d+)', t):
            self._browser.load(QUrl(f"https://steamcommunity.com/sharedfiles/filedetails/?id={re.search(r'id=(\d+)',t).group(1)}"))
        else:
            self._browser.load(QUrl(f"https://steamcommunity.com/workshop/browse/?appid=294100&searchtext={t}&browsesort=trend&section=readytouseitems"))

    # ── Page events ──────────────────────────────────────────────

    def _on_loaded(self, ok):
        self.status_lbl.setText("Ready" if ok else "Failed")
        if ok:
            self._inject()
            QTimer.singleShot(1000, self._inject)
            QTimer.singleShot(2500, self._inject)

    def _on_url(self, url):
        s = url.toString()
        if s and not s.startswith('onyx://'):
            self.addr.setText(s)

    def _inject(self):
        if not self._browser or not self._browser.page():
            return
        self._inject_ver += 1
        js = INJECT_JS.replace('__INSTALLED_IDS__', json.dumps(list(self.installed_ids)))
        js = js.replace('__VERSION__', str(self._inject_ver))
        self._browser.page().runJavaScript(js)

    # ── Download ─────────────────────────────────────────────────

    def _download(self, mod_id: str):
        if self.method_cb.currentData() == 'steam_native':
            if subscribe_via_steam(mod_id):
                QMessageBox.information(self, "Steam", f"Opened {mod_id} in Steam.")
            else:
                open_workshop_page(mod_id)
            return

        if not self._dlq.is_configured:
            QMessageBox.warning(self, "SteamCMD", "SteamCMD not configured. Set path in Settings.")
            return

        self._dlq.enqueue(mod_id, f"Item {mod_id}")

    def _on_started(self, wid, title):
        self.sidebar.add_download(wid, title)
        self.status_lbl.setText(f"Downloading: {title}")

    def _on_progress(self, wid, pct):
        self.sidebar.update_progress(wid, pct)

    def _on_finished(self, wid, ok, msg):
        # Use title already stored by _on_started rather than blocking network call
        title = wid
        for i in range(self.sidebar.dl_list.count()):
            it = self.sidebar.dl_list.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) == wid:
                raw = it.text()
                if raw.startswith(('⬇ ', '✅ ', '❌ ')):
                    raw = raw[2:]
                title = raw.split('—')[0].strip() if '—' in raw else raw.strip()
                break

        self.sidebar.finish_download(wid, ok, title)

        if ok:
            self.installed_ids.add(wid)
            self.inst_lbl.setText(f"{len(self.installed_ids)} installed")
            self.status_lbl.setText(f"Done: {title}")
            self._link_mod(wid)
            self._refresh_sidebar()
            self._inject()
            QTimer.singleShot(800, self._inject)
        else:
            self.status_lbl.setText(f"Failed: {msg[:40]}")

    def _link_mod(self, wid):
        dr = self._settings.get('data_root', '')
        exe = self._settings.get('rimworld_exe', '')
        if not dr or not exe:
            return
        src = Path(dr) / 'mods' / wid
        dst = Path(exe).parent / 'Mods'
        if src.exists():
            ok, method = link_mod_to_game(src, dst)
            print(f"[ModLink] {wid}: {ok} ({method})")
            if not ok:
                print(f"[ModLink] FAILED for {wid}: {method}")

    # ── Mod management ───────────────────────────────────────────

    def _refresh_sidebar(self):
        dr = self._settings.get('data_root', '')
        if dr:
            self.sidebar.refresh_mods(Path(dr) / 'mods')

    def _handle_delete(self, wid, action):
        dr = self._settings.get('data_root', '')
        exe = self._settings.get('rimworld_exe', '')
        if not dr:
            return

        mod_folder = Path(dr) / 'mods' / wid
        game_mods = Path(exe).parent / 'Mods' if exe else Path()

        if action == "delete":
            name = wid
            info = ModInfo.from_path(mod_folder, 'workshop')
            if info:
                name = info.name
            if QMessageBox.question(self, "Delete",
                f"Delete '{name}' from Onyx and game?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return
            delete_downloaded_mod(mod_folder, game_mods)
            self.installed_ids.discard(wid)
            self.inst_lbl.setText(f"{len(self.installed_ids)} installed")
            self._refresh_sidebar()
            self._inject()
        elif action == "redownload":
            delete_downloaded_mod(mod_folder, game_mods)
            self.installed_ids.discard(wid)
            self._refresh_sidebar()
            self._inject()
            self._download(wid)

    # ── Cleanup ──────────────────────────────────────────────────

    def closeEvent(self, e):
        try:
            self._dlq.job_started.disconnect(self._on_started)
            self._dlq.job_progress.disconnect(self._on_progress)
            self._dlq.job_finished.disconnect(self._on_finished)
        except Exception:
            pass
        self._dlq.cancel_all()
        if self._browser:
            try:
                self._browser.setPage(None)
            except Exception:
                pass
        super().closeEvent(e)