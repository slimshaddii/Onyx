"""
Persistent download manager window.
Shows all active and completed downloads with per-item cancel.
Pause is not supported by SteamCMD — cancel and requeue is the equivalent.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QScrollArea, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor

from app.core.steamcmd import DownloadQueue


class DownloadItemWidget(QFrame):
    """One row in the download manager — shows name, progress, cancel."""

    cancel_requested = pyqtSignal(str)  # workshop_id

    def __init__(self, workshop_id: str, name: str, parent=None):
        super().__init__(parent)
        self.workshop_id = workshop_id
        self._done       = False

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background:#2a2a2a; border-radius:4px; "
            "border:1px solid #3a3a3a; margin:1px; }")

        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 6, 8, 6)
        lo.setSpacing(3)

        # Title row
        title_row = QHBoxLayout()
        self._name_lbl = QLabel(name)
        self._name_lbl.setStyleSheet(
            "font-size:11px; font-weight:bold; color:#ffffff; "
            "background:transparent; border:none;")
        self._name_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title_row.addWidget(self._name_lbl, 1)

        self._status_lbl = QLabel("Queued")
        self._status_lbl.setStyleSheet(
            "font-size:10px; color:#888888; "
            "background:transparent; border:none;")
        title_row.addWidget(self._status_lbl)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedSize(52, 20)
        self._cancel_btn.setStyleSheet("""
            QPushButton {
                font-size:9px; padding:1px 4px;
                background:#3a2a2a; color:#cc6666;
                border:1px solid #663333; border-radius:3px;
            }
            QPushButton:hover { background:#4a2a2a; color:#ff6666; }
            QPushButton:pressed { background:#2a1a1a; }
            QPushButton:disabled {
                background:#2a2a2a; color:#555555;
                border-color:#333333;
            }
        """)
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
        self._bar.setStyleSheet("""
            QProgressBar {
                background:#1a1a1a; border-radius:3px; border:none;
            }
            QProgressBar::chunk {
                background:#74d4cc; border-radius:3px;
            }
        """)
        lo.addWidget(self._bar)

        # Log line
        self._log_lbl = QLabel("")
        self._log_lbl.setStyleSheet(
            "font-size:9px; color:#555555; "
            "background:transparent; border:none;")
        self._log_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lo.addWidget(self._log_lbl)

    def set_progress(self, pct: int):
        self._bar.setValue(pct)
        self._status_lbl.setText(f"{pct}%")

    def set_downloading(self):
        self._status_lbl.setText("Downloading…")
        self._status_lbl.setStyleSheet(
            "font-size:10px; color:#74d4cc; "
            "background:transparent; border:none;")

    def set_log(self, line: str):
        # Show only short meaningful lines
        if len(line) > 60:
            line = line[:57] + "…"
        self._log_lbl.setText(line)

    def set_done(self, success: bool):
        self._done = True
        self._bar.setValue(100)
        self._cancel_btn.setText("Clear")
        self._cancel_btn.setEnabled(True)
        # Disconnect cancel signal, connect clear signal instead
        try:
            self._cancel_btn.clicked.disconnect()
        except Exception:
            pass
        self._cancel_btn.clicked.connect(self._self_remove)
        self._cancel_btn.setStyleSheet("""
            QPushButton {
                font-size:9px; padding:1px 4px;
                background:#2a2a2a; color:#888888;
                border:1px solid #3a3a3a; border-radius:3px;
            }
            QPushButton:hover { background:#3a3a3a; color:#aaaaaa; }
        """)

        if success:
            self._status_lbl.setText("Complete")
            self._status_lbl.setStyleSheet(
                "font-size:10px; color:#4CAF50; "
                "background:transparent; border:none;")
            self._bar.setStyleSheet("""
                QProgressBar {
                    background:#1a1a1a; border-radius:3px; border:none;
                }
                QProgressBar::chunk {
                    background:#4CAF50; border-radius:3px;
                }
            """)
            self.setStyleSheet(
                "QFrame { background:#1a2a1a; border-radius:4px; "
                "border:1px solid #2a4a2a; margin:1px; }")
        else:
            self._status_lbl.setText("Failed")
            self._status_lbl.setStyleSheet(
                "font-size:10px; color:#ff4444; "
                "background:transparent; border:none;")
            self._bar.setStyleSheet("""
                QProgressBar {
                    background:#1a1a1a; border-radius:3px; border:none;
                }
                QProgressBar::chunk {
                    background:#ff4444; border-radius:3px;
                }
            """)
            self.setStyleSheet(
                "QFrame { background:#2a1a1a; border-radius:4px; "
                "border:1px solid #4a2a2a; margin:1px; }")
            
    def _self_remove(self):
        """Remove this item from the manager when Clear is clicked."""
        parent_lo = self.parent().layout() if self.parent() else None
        if parent_lo:
            parent_lo.removeWidget(self)
        self.deleteLater()
        # Notify manager to update count
        mgr = self._find_manager()
        if mgr:
            self.workshop_id and mgr._items.pop(self.workshop_id, None)
            mgr._update_count()

    def _find_manager(self):
        """Walk up widget tree to find DownloadManagerWindow."""
        w = self.parent()
        while w:
            if isinstance(w, DownloadManagerWindow):
                return w
            w = w.parent() if hasattr(w, 'parent') else None
        return None

    def is_done(self) -> bool:
        return self._done


class DownloadManagerWindow(QWidget):
    """
    Non-modal download manager window.
    Shows all downloads with individual progress bars and cancel buttons.
    Call show() to open — stays open until user closes it.
    """

    def __init__(self, queue: DownloadQueue, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.queue = queue
        self._items: dict[str, DownloadItemWidget] = {}

        self.setWindowTitle("Download Manager — Onyx")
        self.setMinimumSize(420, 300)
        self.resize(480, 400)

        self._build()
        self._connect()

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 8, 8, 8)
        lo.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Download Manager")
        title.setStyleSheet(
            "font-size:13px; font-weight:bold; color:#74d4cc;")
        hdr.addWidget(title)
        hdr.addStretch()

        self._count_lbl = QLabel("0 active")
        self._count_lbl.setStyleSheet("font-size:10px; color:#888;")
        hdr.addWidget(self._count_lbl)

        cancel_all_btn = QPushButton("Cancel All")
        cancel_all_btn.setFixedHeight(22)
        cancel_all_btn.setStyleSheet("""
            QPushButton {
                font-size:10px; padding:1px 8px;
                background:#3a2a2a; color:#cc6666;
                border:1px solid #663333; border-radius:3px;
            }
            QPushButton:hover { background:#4a2a2a; color:#ff6666; }
            QPushButton:pressed { background:#2a1a1a; }
        """)
        cancel_all_btn.clicked.connect(self._cancel_all)
        hdr.addWidget(cancel_all_btn)

        clear_btn = QPushButton("Clear Done")
        clear_btn.setFixedHeight(22)
        clear_btn.setStyleSheet("""
            QPushButton {
                font-size:10px; padding:1px 8px;
                background:#2a2a2a; color:#888888;
                border:1px solid #3a3a3a; border-radius:3px;
            }
            QPushButton:hover { background:#3a3a3a; color:#aaaaaa; }
            QPushButton:pressed { background:#1a1a1a; }
        """)
        clear_btn.clicked.connect(self._clear_done)
        hdr.addWidget(clear_btn)

        lo.addLayout(hdr)

        # Scroll area for download items
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

        # Status bar
        self._status_lbl = QLabel("Ready")
        self._status_lbl.setStyleSheet(
            "font-size:10px; color:#555; padding:2px 0;")
        lo.addWidget(self._status_lbl)

    def _connect(self):
        self.queue.job_started.connect(self._on_started)
        self.queue.job_progress.connect(self._on_progress)
        self.queue.job_finished.connect(self._on_finished)
        self.queue.job_log.connect(self._on_log)
        self.queue.queue_empty.connect(self._on_queue_empty)

    def _disconnect(self):
        try:
            self.queue.job_started.disconnect(self._on_started)
            self.queue.job_progress.disconnect(self._on_progress)
            self.queue.job_finished.disconnect(self._on_finished)
            self.queue.job_log.disconnect(self._on_log)
            self.queue.queue_empty.disconnect(self._on_queue_empty)
        except Exception:
            pass

    # ── Public API ────────────────────────────────────────────────────────

    def add_download(self, workshop_id: str, name: str):
        """Add a download item to the manager UI."""
        if workshop_id in self._items:
            return
        item = DownloadItemWidget(workshop_id, name, self._container)
        item.cancel_requested.connect(self._cancel_one)
        # Insert before the trailing stretch
        self._container_lo.insertWidget(
            self._container_lo.count() - 1, item)
        self._items[workshop_id] = item
        self._update_count()

    def queue_and_show(self, mods: list[tuple[str, str]]):
        """
        Add all items to UI first, then enqueue all at once.
        Prevents queue_empty firing before all items are queued.
        """
        for wid, name in mods:
            self.add_download(wid, name)

        for wid, name in mods:
            self.queue.enqueue(wid, name)

        self.show()
        self.raise_()
        self.activateWindow()

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_started(self, wid: str, title: str):
        if wid not in self._items:
            self.add_download(wid, title)
        self._items[wid].set_downloading()
        self._status_lbl.setText(f"Downloading: {title}")
        self._update_count()

    def _on_progress(self, wid: str, pct: int):
        if wid in self._items:
            self._items[wid].set_progress(pct)

    def _on_finished(self, wid: str, ok: bool, msg: str):
        if wid in self._items:
            self._items[wid].set_done(ok)
        self._update_count()
        if not ok:
            self._status_lbl.setText(
                f"Failed: {msg[:50]}" if msg else "A download failed.")

    def _on_log(self, wid: str, line: str):
        if wid in self._items:
            lower = line.lower()
            if any(kw in lower for kw in
                   ['download', 'error', 'success', 'fail', '%']):
                self._items[wid].set_log(line)

    def _on_queue_empty(self):
        done  = sum(1 for it in self._items.values() if it.is_done())
        total = len(self._items)
        ok    = sum(1 for it in self._items.values()
                    if it.is_done() and
                    it._status_lbl.text() == "Complete")
        self._status_lbl.setText(
            f"All done — {ok}/{total} succeeded")
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
        to_remove = [wid for wid, it in self._items.items()
                     if it.is_done()]
        for wid in to_remove:
            item = self._items.pop(wid)
            self._container_lo.removeWidget(item)
            item.deleteLater()
        self._update_count()

    def _update_count(self):
        active = sum(1 for it in self._items.values()
                     if not it.is_done())
        total  = len(self._items)
        self._count_lbl.setText(
            f"{active} active / {total} total")

    def closeEvent(self, e):
        # Don't disconnect — queue keeps running in background
        # User can reopen via toolbar button
        e.accept()