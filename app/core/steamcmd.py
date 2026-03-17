import subprocess
import os
import re
import shutil
from pathlib import Path
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal, QObject, QTimer


class SteamCMDDownloader(QThread):
    progress = pyqtSignal(str)
    download_progress = pyqtSignal(int)
    finished_download = pyqtSignal(bool, str, str)  # ok, msg, path

    def __init__(self, steamcmd_path: str, workshop_id: str, app_id: str = '294100',
                 destination: str = '', username: str = '', password: str = ''):
        super().__init__()
        self.steamcmd_path = steamcmd_path
        self.workshop_id = workshop_id
        self.app_id = app_id
        self.destination = destination
        self.username = username
        self.password = password
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        if not os.path.isfile(self.steamcmd_path):
            self.finished_download.emit(False, f"SteamCMD not found: {self.steamcmd_path}", '')
            return

        cmd = [self.steamcmd_path]
        if self.username and self.password:
            cmd.extend(['+login', self.username, self.password])
        else:
            cmd.extend(['+login', 'anonymous'])
        cmd.extend(['+workshop_download_item', self.app_id, self.workshop_id, 'validate', '+quit'])

        self.progress.emit(f"Downloading {self.workshop_id}…")

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=os.path.dirname(self.steamcmd_path))

            for line in iter(proc.stdout.readline, ''):
                if self._cancelled:
                    proc.terminate()
                    self.finished_download.emit(False, "Cancelled", '')
                    return
                line = line.strip()
                if line:
                    self.progress.emit(line)
                    m = re.search(r'(\d+(?:\.\d+)?)\s*%', line)
                    if m:
                        try:
                            self.download_progress.emit(int(float(m.group(1))))
                        except ValueError:
                            pass

            proc.wait()

            dl_path = (Path(self.steamcmd_path).parent / 'steamapps' / 'workshop' /
                       'content' / self.app_id / self.workshop_id)

            if dl_path.exists() and any(dl_path.iterdir()):
                final = str(dl_path)
                if self.destination:
                    dest = Path(self.destination) / self.workshop_id
                    if dest.exists():
                        shutil.rmtree(str(dest))
                    shutil.copytree(str(dl_path), str(dest))
                    final = str(dest)
                self.download_progress.emit(100)
                self.finished_download.emit(True, f"Downloaded {self.workshop_id}", final)
            else:
                self.finished_download.emit(False,
                    "Download failed — folder empty. Some mods need authenticated login.", '')
        except Exception as e:
            self.finished_download.emit(False, f"Error: {e}", '')


class DownloadJob:
    def __init__(self, workshop_id: str, title: str = ''):
        self.workshop_id = workshop_id
        self.title = title or f"Item {workshop_id}"
        self.status = 'queued'  # queued, downloading, done, error
        self.progress = 0
        self.error_msg = ''
        self.thread: Optional[SteamCMDDownloader] = None


class DownloadQueue(QObject):
    """Manages multiple concurrent SteamCMD downloads."""
    job_started = pyqtSignal(str, str)       # workshop_id, title
    job_progress = pyqtSignal(str, int)      # workshop_id, percent
    job_finished = pyqtSignal(str, bool, str) # workshop_id, success, msg
    job_log = pyqtSignal(str, str)           # workshop_id, log line
    queue_empty = pyqtSignal()

    def __init__(self, steamcmd_path: str = '', destination: str = '',
                 max_concurrent: int = 2, username: str = ''):
        super().__init__()
        self.steamcmd_path = steamcmd_path
        self.destination = destination
        self.max_concurrent = max_concurrent
        self.username = username
        self._queue: list[DownloadJob] = []
        self._active: dict[str, DownloadJob] = {}

    @property
    def is_configured(self) -> bool:
        return bool(self.steamcmd_path) and os.path.isfile(self.steamcmd_path)

    def enqueue(self, workshop_id: str, title: str = ''):
        # Skip if already queued or active
        for j in self._queue:
            if j.workshop_id == workshop_id:
                return
        if workshop_id in self._active:
            return

        job = DownloadJob(workshop_id, title)
        self._queue.append(job)
        self._process_queue()

    def cancel(self, workshop_id: str):
        # Remove from queue
        self._queue = [j for j in self._queue if j.workshop_id != workshop_id]
        # Cancel active
        if workshop_id in self._active:
            job = self._active[workshop_id]
            if job.thread:
                job.thread.cancel()

    def cancel_all(self):
        self._queue.clear()
        for job in list(self._active.values()):
            if job.thread:
                job.thread.cancel()

    @property
    def pending_count(self) -> int:
        return len(self._queue) + len(self._active)

    def _process_queue(self):
        while self._queue and len(self._active) < self.max_concurrent:
            job = self._queue.pop(0)
            self._start_job(job)

    def _start_job(self, job: DownloadJob):
        job.status = 'downloading'
        self._active[job.workshop_id] = job
        self.job_started.emit(job.workshop_id, job.title)

        t = SteamCMDDownloader(
            self.steamcmd_path, job.workshop_id,
            destination=self.destination, username=self.username)
        t.progress.connect(lambda msg, wid=job.workshop_id: self.job_log.emit(wid, msg))
        t.download_progress.connect(
            lambda pct, wid=job.workshop_id: self._on_progress(wid, pct))
        t.finished_download.connect(
            lambda ok, msg, path, wid=job.workshop_id: self._on_done(wid, ok, msg))
        job.thread = t
        t.start()

    def _on_progress(self, wid: str, pct: int):
        if wid in self._active:
            self._active[wid].progress = pct
        self.job_progress.emit(wid, pct)

    def _on_done(self, wid: str, ok: bool, msg: str):
        if wid in self._active:
            job = self._active.pop(wid)
            job.status = 'done' if ok else 'error'
            job.error_msg = '' if ok else msg
        self.job_finished.emit(wid, ok, msg)
        self._process_queue()
        if not self._active and not self._queue:
            self.queue_empty.emit()


class SteamCMDManager:
    def __init__(self, steamcmd_path: str = '', mods_destination: str = ''):
        self.steamcmd_path = steamcmd_path
        self.mods_destination = mods_destination

    def is_configured(self) -> bool:
        return bool(self.steamcmd_path) and os.path.isfile(self.steamcmd_path)

    def download_mod(self, workshop_id: str, username: str = '',
                     password: str = '') -> SteamCMDDownloader:
        return SteamCMDDownloader(
            self.steamcmd_path, workshop_id,
            destination=self.mods_destination,
            username=username, password=password)

    @staticmethod
    def extract_workshop_id(url_or_id: str) -> str:
        url_or_id = url_or_id.strip()
        m = re.search(r'[?&]id=(\d+)', url_or_id)
        if m:
            return m.group(1)
        if url_or_id.isdigit():
            return url_or_id
        return url_or_id