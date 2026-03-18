import sys
import os
import shutil
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def excepthook(exc_type, exc_value, exc_tb):
    tb = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(tb, file=sys.stderr)
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance()
        if app and not app.closingDown():
            QMessageBox.critical(None, "Onyx — Fatal Error", tb[:2000])
    except Exception:
        pass


def main():
    sys.excepthook = excepthook
    settings_file = os.path.join(os.path.dirname(__file__), 'data', 'app_settings.json')

    if '--clean' in sys.argv:
        print("[Onyx] Clean start — wiping settings…")
        if os.path.exists(settings_file):
            os.remove(settings_file)
            print(f"  Deleted {settings_file}")
        if '--clean-all' in sys.argv:
            from app.core.paths import get_default_data_root
            ddr = get_default_data_root()
            if ddr.exists():
                print(f"  Deleting data dir: {ddr}")
                shutil.rmtree(str(ddr), ignore_errors=True)
        print("[Onyx] Done. Starting fresh.\n")

    # QtWebEngine MUST be initialized before QApplication on some setups
    webengine_available = False
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        from PyQt6.QtWebEngineCore import QWebEnginePage      # noqa: F401
        webengine_available = True
        print("[Onyx] QtWebEngine: available")
    except Exception as e:
        print(f"[Onyx] QtWebEngine: NOT available — {e}")

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont, QIcon

    app = QApplication(sys.argv)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_dir, 'app', 'ui', 'resources', 'onyx_icon.png')
    app.setWindowIcon(QIcon(icon_path))
    app.setApplicationName("Onyx Launcher")
    app.setOrganizationName("Onyx")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    from app.ui.styles import DARK_STYLESHEET
    app.setStyleSheet(DARK_STYLESHEET)

    # Pass webengine flag to the app so workshop_browser can check it
    app.setProperty("webengine_available", webengine_available)

    from app.ui.main_window import MainWindow
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()