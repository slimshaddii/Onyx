"""
Persistent download manager window — FDM-style.
Shows speed, ETA, percent per item.
Speed/ETA requires file sizes pre-fetched from Steam API.
"""

import threading
import time
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal  # pylint: disable=no-name-in-module
from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QScrollArea, QFrame,
    QSizePolicy,
)

from app.core.app_settings import AppSettings
from app.core.steamcmd import DownloadQueue
from app.ui.styles import get_colors


# ── Theme Helper ──────────────────────────────────────────────────────────────

def _get_theme_colors() -> dict:
    """Return current theme colour map."""
    return get_colors(AppSettings.instance().theme)


# ── Download Item Widget ─────────────────────────────────────────────────────

class DownloadItemWidget(QFrame):
    """Single download row — name, progress bar, speed/ETA, cancel/clear."""

    cancel_requested = pyqtSignal(str)

    def __init__(self, workshop_id: str, file_size: int = 0, parent=None):
        super().__init__(parent)
        self.workshop_id = workshop_id
        self.file_size = file_size
        self._done = False
        self._start_time = 0.0
        self._last_pct = 0

        self._name_lbl: QLabel | None = None
        self._status_lbl: QLabel | None = None
        self._cancel_btn: QPushButton | None = None
        self._bar: QProgressBar | None = None
        self._detail_lbl: QLabel | None = None

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._apply_frame_style('normal')
        self._build()
        self._refresh_styles()

    def _build(self) -> None:
        """Construct child widgets and layouts."""
        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 6, 8, 6)
        lo.setSpacing(3)

        title_row = QHBoxLayout()
        self._name_lbl = QLabel("")
        self._name_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred)
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

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(6)
        self._bar.setTextVisible(False)
        self._apply_bar_style('normal')
        lo.addWidget(self._bar)

        detail_row = QHBoxLayout()
        self._detail_lbl = QLabel("")
        self._detail_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred)
        detail_row.addWidget(self._detail_lbl)
        lo.addLayout(detail_row)

    @property
    def status_text(self) -> str:
        """Current text of the status label."""
        return self._status_lbl.text()

    @property
    def progress_value(self) -> int:
        """Current progress bar value (0-100)."""
        return self._bar.value()

    def set_name(self, name: str) -> None:
        """Set the display name label."""
        self._name_lbl.setText(name)

    def set_status_text(self, text: str) -> None:
        """Set the status label text."""
        self._status_lbl.setText(text)

    def _refresh_styles(self) -> None:
        """Re-apply all label styles from current theme."""
        c = _get_theme_colors()
        self._name_lbl.setStyleSheet(
            f"font-size:11px; font-weight:bold; "
            f"color:{c['text']}; "
            f"background:transparent; border:none;")
        self._set_status_label_style(c['text_dim'])
        self._detail_lbl.setStyleSheet(
            f"font-size:9px; color:{c['text_dim']}; "
            f"background:transparent; border:none;")

    def _set_status_label_style(self, color: str) -> None:
        """Apply status label stylesheet with the given colour."""
        self._status_lbl.setStyleSheet(
            f"font-size:10px; color:{color}; "
            f"background:transparent; border:none;")

    def _apply_frame_style(self, state: str) -> None:
        """Apply frame border colour for normal/success/failed states."""
        c = _get_theme_colors()
        styles = {
            'normal': (
                f"QFrame {{ background:{c['bg_mid']};"
                f" border-radius:4px;"
                f" border:1px solid {c['border']};"
                f" margin:1px; }}"
            ),
            'success': (
                f"QFrame {{ background:{c['bg_mid']};"
                f" border-radius:4px;"
                f" border:1px solid {c['success']};"
                f" margin:1px; }}"
            ),
            'failed': (
                f"QFrame {{ background:{c['bg_mid']};"
                f" border-radius:4px;"
                f" border:1px solid {c['error']};"
                f" margin:1px; }}"
            ),
        }
        self.setStyleSheet(styles.get(state, styles['normal']))

    def _apply_bar_style(self, state: str) -> None:
        """Apply progress bar chunk colour for normal/success/failed states."""
        c = _get_theme_colors()
        colors = {
            'normal': c['accent'],
            'success': c['success'],
            'failed': c['error'],
        }
        color = colors.get(state, c['accent'])
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background:{c['bg_panel']};
                border-radius:3px; border:none;
            }}
            QProgressBar::chunk {{
                background:{color};
                border-radius:3px;
            }}
        """)

    def _apply_cancel_style(self, mode: str) -> None:
        """Apply cancel/clear button stylesheet."""
        c = _get_theme_colors()
        if mode == 'cancel':
            self._cancel_btn.setStyleSheet(f"""
                QPushButton {{
                    font-size:9px; padding:1px 4px;
                    background:{c['bg_mid']};
                    color:{c['error']};
                    border:1px solid {c['error']};
                    border-radius:3px;
                }}
                QPushButton:hover {{
                    background:{c['bg_card']};
                }}
                QPushButton:disabled {{
                    color:{c['text_dim']};
                    border-color:{c['border']};
                }}
            """)
        else:
            self._cancel_btn.setStyleSheet(f"""
                QPushButton {{
                    font-size:9px; padding:1px 4px;
                    background:{c['bg_mid']};
                    color:{c['text_dim']};
                    border:1px solid {c['border']};
                    border-radius:3px;
                }}
                QPushButton:hover {{
                    background:{c['bg_card']};
                    color:{c['text']};
                }}
            """)

    def set_downloading(self) -> None:
        """Transition to downloading state."""
        self._start_time = time.monotonic()
        self._last_pct = 0
        c = _get_theme_colors()
        self._status_lbl.setText("Downloading…")
        self._set_status_label_style(c['accent'])

    def set_progress(self, pct: int) -> None:
        """Update progress bar and speed/ETA display."""
        self._bar.setValue(pct)
        self._last_pct = pct

        if self.file_size and self._start_time and pct > 0:
            stats = self._calculate_download_stats(pct)
            self._status_lbl.setText(f"{pct}%")
            self._detail_lbl.setText(
                f"{_fmt_size(stats['done_bytes'])} / "
                f"{_fmt_size(self.file_size)}"
                f"  •  {_fmt_speed(stats['speed'])}"
                f"  •  ETA {_fmt_eta(stats['eta'])}")
        else:
            self._status_lbl.setText(f"{pct}%")
            self._detail_lbl.setText("")

    def _calculate_download_stats(self, pct: int) -> dict:
        """Return elapsed-based speed, ETA and bytes-done for current percent."""
        elapsed = time.monotonic() - self._start_time
        done_bytes = int(self.file_size * pct / 100)
        speed = done_bytes / elapsed if elapsed > 0 else 0
        remain_bytes = self.file_size - done_bytes
        eta = remain_bytes / speed if speed > 0 else 0
        return {
            'done_bytes': done_bytes,
            'speed': speed,
            'eta': eta,
        }

    def set_log(self, line: str) -> None:
        """Show a truncated log line in the detail area."""
        if len(line) > 70:
            line = line[:67] + "…"
        self._detail_lbl.setText(line)

    def set_done(self, success: bool) -> None:
        """Transition to completed or failed state."""
        self._done = True
        self._bar.setValue(100)

        if success:
            self._set_success_state()
        else:
            self._set_failed_state()

        self._cancel_btn.setText("Clear")
        try:
            self._cancel_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._cancel_btn.clicked.connect(self._self_remove)
        self._apply_cancel_style('clear')

    def _set_success_state(self) -> None:
        """Apply success styling and final avg-speed stat."""
        c = _get_theme_colors()
        self._status_lbl.setText("Complete")
        self._set_status_label_style(c['success'])
        self._apply_bar_style('success')
        self._apply_frame_style('success')
        if self.file_size:
            elapsed = time.monotonic() - self._start_time
            avg_speed = self.file_size / elapsed if elapsed > 0 else 0
            self._detail_lbl.setText(
                f"{_fmt_size(self.file_size)}"
                f"  •  avg {_fmt_speed(avg_speed)}")

    def _set_failed_state(self) -> None:
        """Apply failed styling."""
        c = _get_theme_colors()
        self._status_lbl.setText("Failed")
        self._set_status_label_style(c['error'])
        self._apply_bar_style('failed')
        self._apply_frame_style('failed')

    def _self_remove(self) -> None:
        """Remove this widget from its parent layout and notify the manager."""
        parent_lo = self._get_parent_layout()
        if parent_lo:
            parent_lo.removeWidget(self)
        self.deleteLater()
        mgr = self._find_manager()
        if mgr:
            mgr.remove_item(self.workshop_id)

    def _get_parent_layout(self):
        """Return the layout of this widget's parent, or None."""
        return self.parent().layout() if self.parent() else None

    def _find_manager(self):
        """Walk the parent chain to find the DownloadManagerWindow."""
        w = self.parent()
        while w:
            if isinstance(w, DownloadManagerWindow):
                return w
            w = w.parent() if hasattr(w, 'parent') else None
        return None

    def is_done(self) -> bool:
        """Return True if this download has completed."""
        return self._done


# ── Download Manager Window ──────────────────────────────────────────────────

class DownloadManagerWindow(QWidget):
    """
    Persistent FDM-style download manager window.
    Manages multiple concurrent downloads with per-item progress rows.
    """

    _apply_sizes_signal = pyqtSignal(dict)

    def __init__(self, queue: DownloadQueue, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.queue = queue
        self._items: dict[str, DownloadItemWidget] = {}
        self._sizes: dict[str, int] = {}

        self.setWindowTitle("Download Manager — Onyx")
        self.setMinimumSize(500, 380)
        self.resize(560, 460)

        self._count_lbl: QLabel | None = None
        self._overall_bar: QProgressBar | None = None
        self._container: QWidget | None = None
        self._container_lo: QVBoxLayout | None = None
        self._status_lbl: QLabel | None = None

        self._build()
        self._connect()

    def _build(self) -> None:
        """Construct the window layout, scroll area and status bar."""
        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 8, 8, 8)
        lo.setSpacing(6)

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

        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setValue(0)
        self._overall_bar.setFixedHeight(4)
        self._overall_bar.setTextVisible(False)
        self._overall_bar.hide()
        lo.addWidget(self._overall_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border:none; }")

        self._container = QWidget()
        self._container_lo = QVBoxLayout(self._container)
        self._container_lo.setContentsMargins(0, 0, 0, 0)
        self._container_lo.setSpacing(4)
        self._container_lo.addStretch()

        scroll.setWidget(self._container)
        lo.addWidget(scroll, 1)

        self._status_lbl = QLabel("Ready")
        self._status_lbl.setObjectName("statLabel")
        lo.addWidget(self._status_lbl)

    def _connect(self) -> None:
        """Wire queue signals to UI slots."""
        self.queue.job_started.connect(self._on_started)
        self.queue.job_progress.connect(self._on_progress)
        self.queue.job_finished.connect(self._on_finished)
        self.queue.job_log.connect(self._on_log)
        self.queue.queue_empty.connect(self._on_queue_empty)
        self._apply_sizes_signal.connect(self._apply_sizes)

    def add_download(self, workshop_id: str, name: str) -> None:
        """Add a download row to the UI if not already present."""
        if workshop_id in self._items:
            return
        size = self._sizes.get(workshop_id, 0)
        item = DownloadItemWidget(workshop_id, size, self._container)
        item.set_name(name)
        item.cancel_requested.connect(self._cancel_one)
        self._container_lo.insertWidget(
            self._container_lo.count() - 1, item)
        self._items[workshop_id] = item
        self._update_count()

    def remove_item(self, workshop_id: str) -> None:
        """Remove a completed/cancelled item from tracking."""
        self._items.pop(workshop_id, None)
        self._update_count()

    def queue_and_show(self, mods: list[tuple[str, str]]) -> None:
        """Add items to UI, enqueue downloads, pre-fetch sizes, then show window."""
        for wid, name in mods:
            self.add_download(wid, name)
        for wid, name in mods:
            self.queue.enqueue(wid, name)

        ws_ids = [wid for wid, _ in mods]
        threading.Thread(
            target=self._fetch_sizes,
            args=(ws_ids,),
            daemon=True).start()

        self.show()
        self.raise_()
        self.activateWindow()

    def _fetch_sizes(self, workshop_ids: list[str]) -> None:
        """Fetch file sizes from Steam API on a background thread."""
        try:
            from app.core.mod_update_checker import get_workshop_file_sizes  # pylint: disable=import-outside-toplevel
            sizes = get_workshop_file_sizes(workshop_ids)
            if sizes:
                self._apply_sizes_signal.emit(sizes)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def _apply_sizes(self, sizes: dict) -> None:
        """Apply fetched sizes to items on the main thread."""
        self._sizes.update(sizes)
        for wid, size in sizes.items():
            item = self._items.get(wid)
            if item and not item.is_done():
                item.file_size = size

    def _on_started(self, wid: str, title: str) -> None:
        """Handle job-started signal."""
        if wid not in self._items:
            self.add_download(wid, title)
        self._items[wid].set_downloading()
        self._status_lbl.setText(f"Downloading: {title}")
        self._overall_bar.show()
        self._update_count()

    def _on_progress(self, wid: str, pct: int) -> None:
        """Handle job-progress signal."""
        item = self._items.get(wid)
        if item:
            item.set_progress(pct)
        self._update_overall()

    def _on_finished(self, wid: str, ok: bool, msg: str) -> None:
        """Handle job-finished signal."""
        item = self._items.get(wid)
        if item:
            item.set_done(ok)
            if ok:
                self._record_timestamp(wid)
        self._update_count()
        if not ok:
            self._status_lbl.setText(
                f"Failed: {msg[:50]}" if msg else "A download failed.")
        self._update_overall()

    def _record_timestamp(self, workshop_id: str) -> None:
        """Persist last-downloaded timestamp for a completed mod."""
        try:
            from app.core.mod_update_checker import ModTimestampStore  # pylint: disable=import-outside-toplevel
            dr = AppSettings.instance().data_root
            if dr:
                ModTimestampStore(Path(dr)).record(workshop_id)
        except OSError:
            pass

    def _on_log(self, wid: str, line: str) -> None:
        """Handle job-log signal, forwarding relevant lines to the item row."""
        item = self._items.get(wid)
        if item:
            lower = line.lower()
            if any(kw in lower for kw in
                   ('download', 'error', 'success', 'fail', '%')):
                item.set_log(line)

    def _on_queue_empty(self) -> None:
        """Handle queue-empty signal and update summary status."""
        ok = sum(1 for it in self._items.values()
                 if it.is_done() and it.status_text == "Complete")
        total = len(self._items)
        self._status_lbl.setText(f"All done — {ok}/{total} succeeded")
        self._overall_bar.setValue(100)
        self._update_count()

    def _cancel_one(self, wid: str) -> None:
        """Cancel a single download by workshop ID."""
        self.queue.cancel(wid)
        item = self._items.get(wid)
        if item:
            item.set_done(False)
            item.set_status_text("Cancelled")
        self._update_count()

    def _cancel_all(self) -> None:
        """Cancel all active downloads."""
        self.queue.cancel_all()
        for item in self._items.values():
            if not item.is_done():
                item.set_done(False)
                item.set_status_text("Cancelled")
        self._update_count()

    def _clear_done(self) -> None:
        """Remove all completed/failed/cancelled rows from the UI."""
        for wid in list(self._items.keys()):
            item = self._items[wid]
            if item.is_done():
                self._items.pop(wid)
                self._container_lo.removeWidget(item)
                item.deleteLater()
        self._update_count()

    def _update_count(self) -> None:
        """Refresh the active/total counter label."""
        active = sum(1 for it in self._items.values() if not it.is_done())
        total = len(self._items)
        self._count_lbl.setText(f"{active} active / {total} total")

    def _update_overall(self) -> None:
        """Recompute and set the overall progress bar average."""
        if not self._items:
            return
        avg = sum(it.progress_value for it in self._items.values()) // len(self._items)
        self._overall_bar.setValue(avg)

    def closeEvent(self, e):  # pylint: disable=invalid-name
        """Accept close — downloads continue in queue."""
        e.accept()


# ── Formatting Helpers ────────────────────────────────────────────────────────

def _fmt_speed(bps: float) -> str:
    """Format bytes-per-second as a human-readable speed string."""
    if bps >= 1024 * 1024:
        return f"{bps / (1024 * 1024):.1f} MB/s"
    if bps >= 1024:
        return f"{bps / 1024:.0f} KB/s"
    return f"{bps:.0f} B/s"


def _fmt_eta(seconds: float) -> str:
    """Format seconds into mm:ss or h:mm:ss ETA string."""
    if seconds <= 0 or seconds > 86400:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_size(num_bytes: int) -> str:
    """Format a byte count as a human-readable size string."""
    if num_bytes >= 1024 ** 3:
        return f"{num_bytes / (1024 ** 3):.1f} GB"
    if num_bytes >= 1024 ** 2:
        return f"{num_bytes / (1024 ** 2):.1f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes} B"
