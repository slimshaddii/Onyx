"""
Persistent download manager window — FDM-style.
Shows speed, ETA, percent per item.
Speed/ETA requires file sizes pre-fetched from Steam API.
"""

import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QScrollArea, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from app.core.steamcmd import DownloadQueue
from app.core.app_settings import AppSettings
from app.ui.styles import get_colors


def _c(key: str) -> str:
    return get_colors(AppSettings.instance().theme)[key]


class DownloadItemWidget(QFrame):
    cancel_requested = pyqtSignal(str)

    def __init__(self, workshop_id: str, name: str,
                 file_size: int = 0, parent=None):
        super().__init__(parent)
        self.workshop_id  = workshop_id
        self.file_size    = file_size   # bytes, 0 = unknown
        self._done        = False
        self._start_time  = 0.0
        self._last_pct    = 0

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._apply_frame_style('normal')

        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 6, 8, 6)
        lo.setSpacing(3)

        # Title row
        title_row = QHBoxLayout()
        self._name_lbl = QLabel(name)
        self._name_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title_row.addWidget(self._name_lbl, 1)

        self._status_lbl = QLabel("Queued")
        title_row.addWidget(self._status_lbl)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedSize(52, 20)
        self._apply_cancel_style('cancel')
        self._cancel_btn.clicked.connect(
            lambda: self.cancel_requested.emit(self.workshop_id))
        title_row.addWidget(self._cancel_btn)
        lo.addLayout(title_row)

        # Progress bar
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(6)
        self._bar.setTextVisible(False)
        self._apply_bar_style('normal')
        lo.addWidget(self._bar)

        # Detail row: speed + ETA + size
        detail_row = QHBoxLayout()
        self._detail_lbl = QLabel("")
        self._detail_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        detail_row.addWidget(self._detail_lbl)
        lo.addLayout(detail_row)

        self._refresh_styles()

    def _refresh_styles(self):
        c = get_colors(AppSettings.instance().theme)
        self._name_lbl.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{c['text']}; "
            f"background:transparent; border:none;")
        self._status_lbl.setStyleSheet(
            f"font-size:10px; color:{c['text_dim']}; "
            f"background:transparent; border:none;")
        self._detail_lbl.setStyleSheet(
            f"font-size:9px; color:{c['text_dim']}; "
            f"background:transparent; border:none;")

    def _apply_frame_style(self, state: str):
        c = get_colors(AppSettings.instance().theme)
        styles = {
            'normal':  f"QFrame {{ background:{c['bg_mid']}; border-radius:4px; border:1px solid {c['border']}; margin:1px; }}",
            'success': f"QFrame {{ background:{c['bg_mid']}; border-radius:4px; border:1px solid {c['success']}; margin:1px; }}",
            'failed':  f"QFrame {{ background:{c['bg_mid']}; border-radius:4px; border:1px solid {c['error']}; margin:1px; }}",
        }
        self.setStyleSheet(styles.get(state, styles['normal']))

    def _apply_bar_style(self, state: str):
        c = get_colors(AppSettings.instance().theme)
        colors = {
            'normal':  c['accent'],
            'success': c['success'],
            'failed':  c['error'],
        }
        color = colors.get(state, c['accent'])
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background:{c['bg_panel']}; border-radius:3px; border:none;
            }}
            QProgressBar::chunk {{
                background:{color}; border-radius:3px;
            }}
        """)

    def _apply_cancel_style(self, mode: str):
        c = get_colors(AppSettings.instance().theme)
        if mode == 'cancel':
            self._cancel_btn.setStyleSheet(f"""
                QPushButton {{
                    font-size:9px; padding:1px 4px;
                    background:{c['bg_mid']}; color:{c['error']};
                    border:1px solid {c['error']}; border-radius:3px;
                }}
                QPushButton:hover {{ background:{c['bg_card']}; }}
                QPushButton:disabled {{ color:{c['text_dim']}; border-color:{c['border']}; }}
            """)
        else:  # clear
            self._cancel_btn.setStyleSheet(f"""
                QPushButton {{
                    font-size:9px; padding:1px 4px;
                    background:{c['bg_mid']}; color:{c['text_dim']};
                    border:1px solid {c['border']}; border-radius:3px;
                }}
                QPushButton:hover {{ background:{c['bg_card']}; color:{c['text']}; }}
            """)

    def set_downloading(self):
        self._start_time = time.monotonic()
        self._last_pct   = 0
        c = get_colors(AppSettings.instance().theme)
        self._status_lbl.setText("Downloading…")
        self._status_lbl.setStyleSheet(
            f"font-size:10px; color:{c['accent']}; "
            f"background:transparent; border:none;")

    def set_progress(self, pct: int):
        self._bar.setValue(pct)
        self._last_pct = pct

        if self.file_size and self._start_time and pct > 0:
            elapsed     = time.monotonic() - self._start_time
            done_bytes  = int(self.file_size * pct / 100)
            speed       = done_bytes / elapsed if elapsed > 0 else 0
            remain_bytes = self.file_size - done_bytes
            eta         = remain_bytes / speed if speed > 0 else 0

            speed_str = _fmt_speed(speed)
            eta_str   = _fmt_eta(eta)
            size_str  = _fmt_size(self.file_size)
            done_str  = _fmt_size(done_bytes)

            self._status_lbl.setText(f"{pct}%")
            self._detail_lbl.setText(
                f"{done_str} / {size_str}  •  {speed_str}  •  ETA {eta_str}")
        else:
            self._status_lbl.setText(f"{pct}%")
            self._detail_lbl.setText("")

    def set_log(self, line: str):
        if len(line) > 70:
            line = line[:67] + "…"
        self._detail_lbl.setText(line)

    def set_done(self, success: bool):
        self._done = True
        self._bar.setValue(100)

        if success:
            c = get_colors(AppSettings.instance().theme)
            self._status_lbl.setText("Complete")
            self._status_lbl.setStyleSheet(
                f"font-size:10px; color:{c['success']}; "
                f"background:transparent; border:none;")
            self._apply_bar_style('success')
            self._apply_frame_style('success')
            if self.file_size:
                elapsed = time.monotonic() - self._start_time
                avg_speed = self.file_size / elapsed if elapsed > 0 else 0
                self._detail_lbl.setText(
                    f"{_fmt_size(self.file_size)}  •  "
                    f"avg {_fmt_speed(avg_speed)}")
        else:
            c = get_colors(AppSettings.instance().theme)
            self._status_lbl.setText("Failed")
            self._status_lbl.setStyleSheet(
                f"font-size:10px; color:{c['error']}; "
                f"background:transparent; border:none;")
            self._apply_bar_style('failed')
            self._apply_frame_style('failed')

        self._cancel_btn.setText("Clear")
        try:
            self._cancel_btn.clicked.disconnect()
        except Exception:
            pass
        self._cancel_btn.clicked.connect(self._self_remove)
        self._apply_cancel_style('clear')

    def _self_remove(self):
        parent_lo = self.parent().layout() if self.parent() else None
        if parent_lo:
            parent_lo.removeWidget(self)
        self.deleteLater()
        mgr = self._find_manager()
        if mgr:
            mgr._items.pop(self.workshop_id, None)
            mgr._update_count()

    def _find_manager(self):
        w = self.parent()
        while w:
            if isinstance(w, DownloadManagerWindow):
                return w
            w = w.parent() if hasattr(w, 'parent') else None
        return None

    def is_done(self) -> bool:
        return self._done


class DownloadManagerWindow(QWidget):
    def __init__(self, queue: DownloadQueue, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.queue   = queue
        self._items: dict[str, DownloadItemWidget] = {}
        self._sizes: dict[str, int] = {}   # pre-fetched file sizes

        self.setWindowTitle("Download Manager — Onyx")
        self.setMinimumSize(500, 380)
        self.resize(560, 460)

        self._build()
        self._connect()

    def _build(self):
        c  = get_colors(AppSettings.instance().theme)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 8, 8, 8)
        lo.setSpacing(6)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("Download Manager")
        title.setObjectName("heading")
        hdr.addWidget(title)
        hdr.addStretch()

        self._count_lbl = QLabel("0 active")
        self._count_lbl.setObjectName("statLabel")
        hdr.addWidget(self._count_lbl)

        cancel_all_btn = QPushButton("Cancel All")
        cancel_all_btn.setFixedHeight(22)
        cancel_all_btn.setObjectName("dangerButton")
        cancel_all_btn.clicked.connect(self._cancel_all)
        hdr.addWidget(cancel_all_btn)

        clear_btn = QPushButton("Clear Done")
        clear_btn.setFixedHeight(22)
        clear_btn.clicked.connect(self._clear_done)
        hdr.addWidget(clear_btn)
        lo.addLayout(hdr)

        # ── Overall progress ──────────────────────────────────────────────
        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setValue(0)
        self._overall_bar.setFixedHeight(4)
        self._overall_bar.setTextVisible(False)
        self._overall_bar.hide()
        lo.addWidget(self._overall_bar)

        # ── Scroll area ───────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border:none; }")

        self._container    = QWidget()
        self._container_lo = QVBoxLayout(self._container)
        self._container_lo.setContentsMargins(0, 0, 0, 0)
        self._container_lo.setSpacing(4)
        self._container_lo.addStretch()

        scroll.setWidget(self._container)
        lo.addWidget(scroll, 1)

        # ── Status bar ────────────────────────────────────────────────────
        self._status_lbl = QLabel("Ready")
        self._status_lbl.setObjectName("statLabel")
        lo.addWidget(self._status_lbl)

    def _connect(self):
        self.queue.job_started.connect(self._on_started)
        self.queue.job_progress.connect(self._on_progress)
        self.queue.job_finished.connect(self._on_finished)
        self.queue.job_log.connect(self._on_log)
        self.queue.queue_empty.connect(self._on_queue_empty)

    # ── Public API ────────────────────────────────────────────────────────

    def add_download(self, workshop_id: str, name: str):
        if workshop_id in self._items:
            return
        size = self._sizes.get(workshop_id, 0)
        item = DownloadItemWidget(
            workshop_id, name, size, self._container)
        item.cancel_requested.connect(self._cancel_one)
        self._container_lo.insertWidget(
            self._container_lo.count() - 1, item)
        self._items[workshop_id] = item
        self._update_count()

    def queue_and_show(self, mods: list[tuple[str, str]]):
        """
        Pre-fetch file sizes from Steam API (background thread),
        add all items to UI, then enqueue.
        """
        for wid, name in mods:
            self.add_download(wid, name)

        # Enqueue immediately so downloads start
        for wid, name in mods:
            self.queue.enqueue(wid, name)

        # Fetch sizes in background — updates items when ready
        ws_ids = [wid for wid, _ in mods]
        import threading
        threading.Thread(
            target=self._fetch_sizes,
            args=(ws_ids,),
            daemon=True).start()

        self.show()
        self.raise_()
        self.activateWindow()

    def _fetch_sizes(self, workshop_ids: list[str]):
        """Background: fetch file sizes then update items."""
        try:
            from app.core.mod_update_checker import get_workshop_file_sizes
            sizes = get_workshop_file_sizes(workshop_ids)
            self._sizes.update(sizes)
            # Update existing items that haven't started yet
            for wid, size in sizes.items():
                if wid in self._items and not self._items[wid]._done:
                    self._items[wid].file_size = size
        except Exception:
            pass  # Size fetch failure is non-fatal — shows % only

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_started(self, wid: str, title: str):
        if wid not in self._items:
            self.add_download(wid, title)
        self._items[wid].set_downloading()
        self._status_lbl.setText(f"Downloading: {title}")
        self._overall_bar.show()
        self._update_count()

    def _on_progress(self, wid: str, pct: int):
        if wid in self._items:
            self._items[wid].set_progress(pct)
        self._update_overall()

    def _on_finished(self, wid: str, ok: bool, msg: str):
        if wid in self._items:
            self._items[wid].set_done(ok)
            # Record timestamp on success
            if ok:
                self._record_timestamp(wid)
        self._update_count()
        if not ok:
            self._status_lbl.setText(
                f"Failed: {msg[:50]}" if msg else "A download failed.")
        self._update_overall()

    def _record_timestamp(self, workshop_id: str):
        try:
            from app.core.mod_update_checker import ModTimestampStore
            from pathlib import Path
            dr = AppSettings.instance().data_root
            if dr:
                store = ModTimestampStore(Path(dr))
                store.record(workshop_id)
        except Exception:
            pass

    def _on_log(self, wid: str, line: str):
        if wid in self._items:
            lower = line.lower()
            if any(kw in lower for kw in
                   ['download', 'error', 'success', 'fail', '%']):
                self._items[wid].set_log(line)

    def _on_queue_empty(self):
        ok    = sum(1 for it in self._items.values()
                    if it.is_done() and
                    it._status_lbl.text() == "Complete")
        total = len(self._items)
        self._status_lbl.setText(f"All done — {ok}/{total} succeeded")
        self._overall_bar.setValue(100)
        self._update_count()

    def _cancel_one(self, wid: str):
        self.queue.cancel(wid)
        if wid in self._items:
            self._items[wid].set_done(False)
            self._items[wid]._status_lbl.setText("Cancelled")
        self._update_count()

    def _cancel_all(self):
        self.queue.cancel_all()
        for item in self._items.values():
            if not item.is_done():
                item.set_done(False)
                item._status_lbl.setText("Cancelled")
        self._update_count()

    def _clear_done(self):
        for wid in list(self._items.keys()):
            item = self._items[wid]
            if item.is_done():
                self._items.pop(wid)
                self._container_lo.removeWidget(item)
                item.deleteLater()
        self._update_count()

    def _update_count(self):
        active = sum(1 for it in self._items.values() if not it.is_done())
        total  = len(self._items)
        self._count_lbl.setText(f"{active} active / {total} total")

    def _update_overall(self):
        items = list(self._items.values())
        if not items:
            return
        avg = sum(it._bar.value() for it in items) // len(items)
        self._overall_bar.setValue(avg)

    def closeEvent(self, e):
        e.accept()


# ── Format helpers ────────────────────────────────────────────────────────────

def _fmt_speed(bps: float) -> str:
    if bps >= 1024 * 1024:
        return f"{bps / (1024*1024):.1f} MB/s"
    if bps >= 1024:
        return f"{bps / 1024:.0f} KB/s"
    return f"{bps:.0f} B/s"


def _fmt_eta(seconds: float) -> str:
    if seconds <= 0 or seconds > 86400:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024 * 1024:
        return f"{num_bytes / (1024**3):.1f} GB"
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024**2):.1f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes} B"