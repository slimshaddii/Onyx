"""WebEngine detection and custom page."""

from PyQt6.QtCore import pyqtSignal

WE_ERROR = None
HAS_WE = False

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import (
        QWebEnginePage, QWebEngineProfile, QWebEngineSettings
    )
    HAS_WE = True
except Exception as _e:
    WE_ERROR = str(_e)

if HAS_WE:
    class OnyxPage(QWebEnginePage):
        onyx_download = pyqtSignal(str)

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            if url.scheme() == 'onyx':
                mid = url.path().strip('/')
                if url.host() == 'download' and mid and mid.isdigit():
                    self.onyx_download.emit(mid)
                return False
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)