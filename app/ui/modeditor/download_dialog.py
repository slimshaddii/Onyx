"""Download progress dialog for auto-downloading missing dependencies."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from app.core.steamcmd import DownloadQueue


class DownloadProgressDialog(QDialog):
    """Shows progress while downloading multiple mods."""
    
    downloads_complete = pyqtSignal(list)  # list of (workshop_id, success, msg)
    
    def __init__(self, parent, download_queue: DownloadQueue, 
                 mods_to_download: list[tuple[str, str]]):
        """
        Args:
            parent: Parent widget
            download_queue: Configured DownloadQueue instance
            mods_to_download: List of (workshop_id, mod_name) tuples
        """
        super().__init__(parent)
        self.queue = download_queue
        self.mods = mods_to_download
        self.results: list[tuple[str, bool, str]] = []
        self._completed = 0
        self._total = len(mods_to_download)
        
        self.setWindowTitle("Downloading Dependencies")
        self.setMinimumSize(500, 350)
        self.setModal(True)
        
        self._build()
        self._connect_signals()
        self._start_downloads()
    
    def _build(self):
        lo = QVBoxLayout(self)
        lo.setSpacing(8)
        
        # Header
        self.header = QLabel(f"Downloading {self._total} mod(s)...")
        self.header.setStyleSheet("font-weight: bold; font-size: 12px;")
        lo.addWidget(self.header)
        
        # Overall progress
        prog_frame = QFrame()
        prog_lo = QVBoxLayout(prog_frame)
        prog_lo.setContentsMargins(0, 0, 0, 0)
        
        self.overall_label = QLabel(f"Overall: 0 / {self._total}")
        prog_lo.addWidget(self.overall_label)
        
        self.overall_bar = QProgressBar()
        self.overall_bar.setRange(0, self._total)
        self.overall_bar.setValue(0)
        prog_lo.addWidget(self.overall_bar)
        
        lo.addWidget(prog_frame)
        
        # Current download
        self.current_label = QLabel("Preparing...")
        lo.addWidget(self.current_label)
        
        self.current_bar = QProgressBar()
        self.current_bar.setRange(0, 100)
        self.current_bar.setValue(0)
        lo.addWidget(self.current_bar)
        
        # Log
        lo.addWidget(QLabel("Log:"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        self.log.setStyleSheet("font-family: monospace; font-size: 10px;")
        lo.addWidget(self.log)
        
        # Buttons
        btn_lo = QHBoxLayout()
        btn_lo.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_lo.addWidget(self.cancel_btn)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setEnabled(False)
        btn_lo.addWidget(self.close_btn)
        
        lo.addLayout(btn_lo)
    
    def _connect_signals(self):
        self.queue.job_started.connect(self._on_job_started)
        self.queue.job_progress.connect(self._on_job_progress)
        self.queue.job_finished.connect(self._on_job_finished)
        self.queue.job_log.connect(self._on_job_log)
        self.queue.queue_empty.connect(self._on_queue_empty)

    def _disconnect_signals(self):
        try:
            self.queue.job_started.disconnect(self._on_job_started)
            self.queue.job_progress.disconnect(self._on_job_progress)
            self.queue.job_finished.disconnect(self._on_job_finished)
            self.queue.job_log.disconnect(self._on_job_log)
            self.queue.queue_empty.disconnect(self._on_queue_empty)
        except Exception:
            pass
    
    def _start_downloads(self):
        self._log("Starting downloads...")
        for workshop_id, name in self.mods:
            self.queue.enqueue(workshop_id, name)
            self._log(f"  Queued: {name} ({workshop_id})")
    
    def _log(self, msg: str):
        self.log.append(msg)
        # Auto-scroll to bottom
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def _on_job_started(self, workshop_id: str, title: str):
        self.current_label.setText(f"Downloading: {title}")
        self.current_bar.setValue(0)
        self._log(f"\n[START] {title}")
    
    def _on_job_progress(self, workshop_id: str, percent: int):
        self.current_bar.setValue(percent)
    
    def _on_job_finished(self, workshop_id: str, success: bool, msg: str):
        self._completed += 1
        self.overall_bar.setValue(self._completed)
        self.overall_label.setText(f"Overall: {self._completed} / {self._total}")
        
        # Find the mod name
        name = workshop_id
        for wid, n in self.mods:
            if wid == workshop_id:
                name = n
                break
        
        self.results.append((workshop_id, success, msg))
        
        if success:
            self._log(f"[OK] {name}")
        else:
            self._log(f"[FAILED] {name}: {msg}")
    
    def _on_job_log(self, workshop_id: str, line: str):
        # Only show important lines to avoid spam
        lower = line.lower()
        if any(kw in lower for kw in ['download', 'error', 'success', 'fail', '%']):
            self._log(f"  {line}")
    
    def _on_queue_empty(self):
        success_count = sum(1 for _, ok, _ in self.results if ok)
        fail_count = len(self.results) - success_count
        
        self.header.setText(f"Complete: {success_count} succeeded, {fail_count} failed")
        self.current_label.setText("Done")
        self.current_bar.setValue(100)
        
        self.cancel_btn.setEnabled(False)
        self.close_btn.setEnabled(True)
        
        self._log(f"\n{'='*40}")
        self._log(f"Downloads complete: {success_count} OK, {fail_count} failed")
        
        self.downloads_complete.emit(self.results)
    
    def _on_cancel(self):
        self._log("\nCancelling...")
        self._disconnect_signals()
        self.queue.cancel_all()
        self.reject()
    
    def closeEvent(self, event):
        if self.queue.pending_count > 0:
            self._disconnect_signals()
            self.queue.cancel_all()
        super().closeEvent(event)