"""WebEngine detection and custom page."""

from PyQt6.QtCore import pyqtSignal  # pylint: disable=no-name-in-module

WE_ERROR = None
HAS_WE   = False

try:
    from PyQt6.QtWebEngineWidgets import (  # pylint: disable=no-name-in-module,unused-import
        QWebEngineView,
    )
    from PyQt6.QtWebEngineCore import (  # pylint: disable=no-name-in-module,unused-import
        QWebEnginePage, QWebEngineProfile, QWebEngineSettings,
    )
    HAS_WE = True
except Exception as _e:  # pylint: disable=broad-exception-caught
    WE_ERROR = str(_e)

if HAS_WE:
    class OnyxPage(QWebEnginePage):  # pylint: disable=possibly-used-before-assignment
        """QWebEnginePage subclass that intercepts onyx:// download URLs."""

        onyx_download = pyqtSignal(str)

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # pylint: disable=invalid-name
            """Intercept onyx://download/<mod_id> and emit onyx_download signal."""
            if url.scheme() == 'onyx':
                mid = url.path().strip('/')
                if url.host() == 'download' and mid and mid.isdigit():
                    self.onyx_download.emit(mid)
                return False
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)
