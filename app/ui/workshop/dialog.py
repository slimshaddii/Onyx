"""Main workshop browser dialog."""

import json
import re
from pathlib import Path

from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QMessageBox, QWidget, QComboBox, QApplication, QInputDialog,
)
from PyQt6.QtCore import Qt, QUrl, QTimer  # pylint: disable=no-name-in-module

from app.core.app_settings import AppSettings
from app.core.mod_linker import link_mod_to_game, delete_downloaded_mod
from app.core.rimworld import ModInfo
from app.core.steam_integration import (
    DownloadMethod, subscribe_via_steam, open_workshop_page,
)
from app.core.steamcmd import SteamCMDManager, DownloadQueue
from app.ui.styles import get_colors
from app.ui.workshop.js_inject import INJECT_JS
from app.ui.workshop.web_page import HAS_WE, WE_ERROR

if HAS_WE:
    from app.ui.workshop.web_page import (
        OnyxPage, QWebEngineView, QWebEngineProfile, QWebEngineSettings,
    )

WORKSHOP_BROWSE = (
    "https://steamcommunity.com/workshop/browse/?appid=294100"
    "&browsesort=trend&section=readytouseitems")
WORKSHOP_HOME = "https://steamcommunity.com/app/294100/workshop/"


class WorkshopBrowserDialog(QDialog):
    """Steam Workshop browser with optional WebEngine integration."""

    def __init__(self, _parent, steamcmd: SteamCMDManager, rw=None,
                 _api_key='', installed_workshop_ids=None,
                 download_method=DownloadMethod.STEAMCMD,
                 _is_steam_copy=False, settings=None):
        super().__init__(None)
        self.steamcmd        = steamcmd
        self.rw              = rw
        self.installed_ids   = set(installed_workshop_ids or set())
        self.download_method = download_method
        self._settings       = settings or {}
        self._browser        = None
        self._inject_ver     = 0

        self.addr:       QLineEdit | None = None
        self.method_cb:  QComboBox | None = None
        self.status_lbl: QLabel    | None = None
        self.inst_lbl:   QLabel    | None = None

        self._dlq = DownloadQueue(
            steamcmd_path=steamcmd.steamcmd_path,
            destination=steamcmd.mods_destination,
            max_concurrent=3,
            username=self._settings.get('steamcmd_username', ''))

        from app.ui.modeditor.download_manager import DownloadManagerWindow  # pylint: disable=import-outside-toplevel
        self._dl_manager_window = DownloadManagerWindow(self._dlq, self)
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
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"[Workshop] WebEngine failed: {e}")
                can = False
        if not can:
            self._build_fallback()

    def _build_fallback(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)
        lo.addWidget(self._make_nav())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        msg = QLabel(
            f"WebEngine unavailable — "
            f"{WE_ERROR or 'pip install PyQt6-WebEngine'}\n"
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

        # pylint: disable=possibly-used-before-assignment
        profile = QWebEngineProfile.defaultProfile()
        s = profile.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)

        self._page = OnyxPage(profile, self)
        self._page.onyx_download.connect(self._download)

        self._browser = QWebEngineView(self)
        # pylint: enable=possibly-used-before-assignment
        self._browser.setPage(self._page)
        self._browser.loadStarted.connect(
            lambda: self.status_lbl.setText("Loading…"))
        self._browser.loadFinished.connect(self._on_loaded)
        self._browser.urlChanged.connect(self._on_url)
        body.addWidget(self._browser, 1)

        bw = QWidget()
        bw.setLayout(body)
        lo.addWidget(bw, 1)
        lo.addWidget(self._make_status())
        self._browser.load(QUrl(WORKSHOP_BROWSE))

    def _make_nav(self) -> QWidget:
        c = get_colors(AppSettings.instance().theme)
        w = QWidget()
        w.setStyleSheet(
            f"background:{c['bg_panel']};"
            f"border-bottom:1px solid {c['border']};")
        lo = QHBoxLayout(w)
        lo.setContentsMargins(6, 4, 6, 4)
        lo.setSpacing(3)

        if HAS_WE:
            for text, tip, fn in [
                ("Back",   "Go back",     lambda: self._browser and self._browser.back()),
                ("Fwd",    "Go forward",  lambda: self._browser and self._browser.forward()),
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

        dl_mgr_btn = QPushButton("Downloads")
        dl_mgr_btn.setFixedHeight(26)
        dl_mgr_btn.setStyleSheet("font-size:10px;padding:2px 8px;")
        dl_mgr_btn.setToolTip("Open Download Manager")
        dl_mgr_btn.clicked.connect(self._open_download_manager)
        lo.addWidget(dl_mgr_btn)

        lib_btn = QPushButton("Library")
        lib_btn.setFixedHeight(26)
        lib_btn.setStyleSheet("font-size:10px;padding:2px 8px;")
        lib_btn.setToolTip("Browse downloaded mods")
        lib_btn.clicked.connect(self._open_library)
        lo.addWidget(lib_btn)

        lo.addWidget(QLabel("│"))

        dl_coll_btn = QPushButton("Get Collection")
        dl_coll_btn.setFixedHeight(26)
        dl_coll_btn.setStyleSheet("font-size:10px;padding:2px 8px;")
        dl_coll_btn.setToolTip(
            "Download all mods from a Steam Workshop collection.\n"
            "Paste the collection URL or ID in the address bar first.")
        dl_coll_btn.clicked.connect(self._download_collection)
        lo.addWidget(dl_coll_btn)

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
        c = get_colors(AppSettings.instance().theme)
        w = QWidget()
        w.setStyleSheet(
            f"background:{c['bg_panel']};"
            f"border-top:1px solid {c['border']};")
        w.setFixedHeight(24)
        lo = QHBoxLayout(w)
        lo.setContentsMargins(10, 0, 10, 0)
        self.status_lbl = QLabel("Ready")
        self.status_lbl.setStyleSheet(
            f"color:{c['text_dim']};font-size:10px;")
        lo.addWidget(self.status_lbl, 1)
        self.inst_lbl = QLabel(f"{len(self.installed_ids)} installed")
        self.inst_lbl.setStyleSheet(
            f"color:{c['success']};font-size:10px;")
        lo.addWidget(self.inst_lbl)
        update_btn = QPushButton("Check Updates")
        update_btn.clicked.connect(self._open_update_checker)
        lo.addWidget(update_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        lo.addWidget(close_btn)
        return w

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
            if t.isdigit():
                self._try_download_or_collection(t)
            return
        if t.startswith('http'):
            self._browser.load(QUrl(t))
        elif t.isdigit():
            self._browser.load(QUrl(
                f"https://steamcommunity.com/sharedfiles/filedetails/?id={t}"))
        elif re.search(r'id=(\d+)', t):
            wid = re.search(r'id=(\d+)', t).group(1)
            self._browser.load(QUrl(
                f"https://steamcommunity.com/sharedfiles/filedetails/?id={wid}"))
        else:
            self._browser.load(QUrl(
                f"https://steamcommunity.com/workshop/browse/"
                f"?appid=294100&searchtext={t}"
                f"&browsesort=trend&section=readytouseitems"))

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
        js = INJECT_JS.replace(
            '__INSTALLED_IDS__', json.dumps(list(self.installed_ids)))
        js = js.replace('__VERSION__', str(self._inject_ver))
        self._browser.page().runJavaScript(js)

    def _download(self, mod_id: str):
        if self.method_cb.currentData() == 'steam_native':
            if subscribe_via_steam(mod_id):
                QMessageBox.information(
                    self, "Steam", f"Opened {mod_id} in Steam.")
            else:
                open_workshop_page(mod_id)
            return

        if not self._dlq.is_configured:
            QMessageBox.warning(
                self, "SteamCMD",
                "SteamCMD not configured. Set path in Settings.")
            return

        self._dlq.enqueue(mod_id, f"Item {mod_id}")

    def _open_download_manager(self):
        """Open the persistent download manager window."""
        from app.ui.modeditor.download_manager import DownloadManagerWindow  # pylint: disable=import-outside-toplevel
        if not hasattr(self, '_dl_manager_window'):
            self._dl_manager_window = DownloadManagerWindow(self._dlq, self)
        self._dl_manager_window.show()
        self._dl_manager_window.raise_()
        self._dl_manager_window.activateWindow()

    def _open_library(self):
        """Open the mod library browser."""
        from app.ui.mod_library_dialog import ModLibraryDialog  # pylint: disable=import-outside-toplevel
        dr = self._settings.get('data_root', '')
        if not dr:
            QMessageBox.warning(self, "Library", "Data root not configured.")
            return
        dlg = ModLibraryDialog(
            self,
            Path(dr) / 'mods',
            download_manager=None)
        dlg.exec()

    def _open_update_checker(self):
        """Open the mod update checker dialog."""
        from app.ui.mod_update_dialog import ModUpdateDialog  # pylint: disable=import-outside-toplevel
        dr = self._settings.get('data_root', '')
        if not dr:
            QMessageBox.warning(self, "Check Updates",
                                "Data root not configured.")
            return
        dlg = ModUpdateDialog(
            self, self.rw, Path(dr),
            download_manager=self._dl_manager_window)
        dlg.exec()

    def _download_collection(self):
        t = self.addr.text().strip()
        m = re.search(r'id=(\d+)', t)
        if m:
            coll_id = m.group(1)
        elif t.isdigit():
            coll_id = t
        else:
            coll_id, ok = QInputDialog.getText(
                self, "Collection ID",
                "Enter Steam Workshop collection ID or URL:")
            if not ok or not coll_id.strip():
                return
            m2 = re.search(r'id=(\d+)', coll_id)
            coll_id = m2.group(1) if m2 else coll_id.strip()

        if not coll_id.isdigit():
            QMessageBox.warning(self, "Invalid ID",
                                "Could not find a valid collection ID.")
            return

        self.status_lbl.setText(f"Fetching collection {coll_id}...")
        QApplication.processEvents()

        mod_ids, error = self._fetch_collection(coll_id)
        if error:
            QMessageBox.warning(self, "Collection Error", error)
            self.status_lbl.setText("Ready")
            return

        if not mod_ids:
            QMessageBox.information(self, "Empty Collection",
                                    "No mods found in this collection.")
            self.status_lbl.setText("Ready")
            return

        to_download = [mid for mid in mod_ids
                       if mid not in self.installed_ids]
        already     = len(mod_ids) - len(to_download)

        if not to_download:
            QMessageBox.information(
                self, "Collection",
                f"All {len(mod_ids)} mods already installed.")
            self.status_lbl.setText("Ready")
            return

        msg = (f"Collection contains {len(mod_ids)} mod(s).\n"
               f"Already installed: {already}\n"
               f"To download: {len(to_download)}\n\n"
               f"Download {len(to_download)} mod(s) now?")

        if QMessageBox.question(
                self, "Download Collection", msg,
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            self.status_lbl.setText("Ready")
            return

        if not self._dlq.is_configured:
            QMessageBox.warning(self, "SteamCMD",
                                "SteamCMD not configured.")
            return

        for mod_id in to_download:
            self._dlq.enqueue(mod_id, f"Mod {mod_id}")

        self.status_lbl.setText(
            f"Queued {len(to_download)} mod(s) from collection")

    @staticmethod
    def _fetch_collection(collection_id: str) -> tuple[list[str], str]:
        """Fetch mod IDs from a Steam Workshop collection.

        Returns (mod_id_list, error_string). No API key required.
        """
        import requests as _requests  # pylint: disable=import-outside-toplevel

        url = ("https://api.steampowered.com/"
               "ISteamRemoteStorage/GetCollectionDetails/v1/")
        try:
            resp = _requests.post(url, data={
                'collectioncount': '1',
                'publishedfileids[0]': collection_id,
            }, timeout=15)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as e:  # pylint: disable=broad-exception-caught
            return [], f"Network error: {e}"

        try:
            result = raw['response']['collectiondetails'][0]
        except (KeyError, IndexError):
            return [], "Unexpected API response format."

        if result.get('result') != 1:
            return [], (f"Steam API error: result code "
                        f"{result.get('result')}. "
                        f"Is this a valid collection ID?")

        children = result.get('children', [])
        if not children:
            return [], ""

        mod_ids: list[str] = []
        nested:  list[str] = []

        for child in children:
            fid       = str(child.get('publishedfileid', ''))
            file_type = child.get('file_type', 0)
            if not fid:
                continue
            if file_type == 2:
                nested.append(fid)
            else:
                mod_ids.append(fid)

        for nested_id in nested:
            sub_ids, _ = WorkshopBrowserDialog._fetch_collection(nested_id)
            mod_ids.extend(sub_ids)

        seen:   set[str]  = set()
        unique: list[str] = []
        for mid in mod_ids:
            if mid not in seen:
                seen.add(mid)
                unique.append(mid)

        return unique, ""

    def _on_started(self, _wid, title):
        self.status_lbl.setText(f"Downloading: {title}")
        self._dl_manager_window.show()
        self._dl_manager_window.raise_()

    def _on_progress(self, _wid, _pct):
        pass

    def _on_finished(self, wid, ok, msg):
        title = wid
        if ok:
            self.installed_ids.add(wid)
            self.inst_lbl.setText(f"{len(self.installed_ids)} installed")
            self.status_lbl.setText(f"Done: {title}")
            self._link_mod(wid)
            self._inject()
            QTimer.singleShot(500,  self._inject)
            QTimer.singleShot(1500, self._inject)
            QTimer.singleShot(3000, self._inject)
        else:
            self.status_lbl.setText(f"Failed: {msg[:40]}")

        if ok:
            self.installed_ids.add(wid)
            self.inst_lbl.setText(f"{len(self.installed_ids)} installed")
            self.status_lbl.setText(f"Done: {title}")
            self._link_mod(wid)
            self._inject()
            QTimer.singleShot(500,  self._inject)
            QTimer.singleShot(1500, self._inject)
            QTimer.singleShot(3000, self._inject)
        else:
            self.status_lbl.setText(f"Failed: {msg[:40]}")

    def _link_mod(self, wid):
        dr  = self._settings.get('data_root', '')
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

    def _refresh_sidebar(self):
        pass

    def _handle_delete(self, wid, action):
        dr  = self._settings.get('data_root', '')
        exe = self._settings.get('rimworld_exe', '')
        if not dr:
            return

        mod_folder = Path(dr) / 'mods' / wid
        game_mods  = Path(exe).parent / 'Mods' if exe else Path()

        if action == "delete":
            name = wid
            info = ModInfo.from_path(mod_folder, 'workshop')
            if info:
                name = info.name
            if QMessageBox.question(
                    self, "Delete",
                    f"Delete '{name}' from Onyx and game?",
                    QMessageBox.StandardButton.Yes |
                    QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
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

    def closeEvent(self, e):  # pylint: disable=invalid-name
        """Clean up signal connections and browser on close."""
        try:
            self._dlq.job_started.disconnect(self._on_started)
            self._dlq.job_progress.disconnect(self._on_progress)
            self._dlq.job_finished.disconnect(self._on_finished)
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        self._dlq.cancel_all()
        if self._browser:
            try:
                self._browser.setPage(None)
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        super().closeEvent(e)
