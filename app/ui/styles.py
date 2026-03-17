DARK_STYLESHEET = """
/* ===== Base ===== */
QMainWindow, QDialog { background-color: #1b1b2a; color: #d0d4dc; }
QWidget { background: transparent; color: #d0d4dc; font-family: "Segoe UI"; font-size: 12px; }

/* ===== Toolbar ===== */
QToolBar { background: #151522; border-bottom: 1px solid #2a2a40; spacing: 1px; padding: 3px 6px; }
QToolBar::separator { width: 1px; background: #2a2a40; margin: 3px 4px; }
QToolButton { background: transparent; color: #9a9eb0; border: none; border-radius: 5px;
    padding: 5px 10px; font-size: 11px; font-weight: 600; }
QToolButton:hover { background: #252540; color: #fff; }
QToolButton:pressed { background: #303050; }

/* ===== Buttons ===== */
QPushButton { background: #262640; color: #d0d4dc; border: 1px solid #353555;
    border-radius: 5px; padding: 5px 14px; font-weight: 600; font-size: 11px; }
QPushButton:hover { background: #353555; }
QPushButton:pressed { background: #404065; }
QPushButton:disabled { background: #1a1a2a; color: #444; border-color: #222; }
QPushButton#primaryButton { background: #3d5afe; color: #fff; border: none; }
QPushButton#primaryButton:hover { background: #536dfe; }
QPushButton#dangerButton { background: #b71c1c; color: #fff; border: none; }
QPushButton#dangerButton:hover { background: #d32f2f; }
QPushButton#successButton { background: #2e7d32; color: #fff; border: none; }
QPushButton#successButton:hover { background: #43a047; }
QPushButton#subscribeBtn { background: #388e3c; color: #fff; border: none;
    font-size: 13px; padding: 8px 22px; border-radius: 3px; }
QPushButton#subscribeBtn:hover { background: #43a047; }
QPushButton#installedBtn { background: #1b5e20; color: #81c784;
    border: 1px solid #2e7d32; font-size: 13px; padding: 8px 22px; border-radius: 3px; }

/* ===== Inputs ===== */
QLineEdit, QTextEdit, QPlainTextEdit { background: #151522; color: #d0d4dc;
    border: 1px solid #353555; border-radius: 5px; padding: 5px 8px;
    selection-background-color: #3d5afe; }
QLineEdit:focus, QTextEdit:focus { border-color: #3d5afe; }
QLineEdit#addressBar { background: #111120; border: 2px solid #353555;
    border-radius: 14px; padding: 5px 14px; font-size: 12px; font-family: "Consolas","Segoe UI"; }
QLineEdit#addressBar:focus { border-color: #3d5afe; }
QLineEdit#searchBar { background: #151522; border: 1px solid #353555;
    border-radius: 14px; padding: 6px 14px; font-size: 12px; }
QLineEdit#searchBar:focus { border-color: #3d5afe; }

/* ===== Lists ===== */
QListWidget { background: #151522; border: 1px solid #252540; border-radius: 6px;
    outline: none; padding: 1px; }
QListWidget::item { padding: 3px 6px; border-radius: 3px; margin: 0px 1px; }
QListWidget::item:selected { background: #252550; color: #7c8aff; }
QListWidget::item:hover:!selected { background: #1e1e35; }
QListWidget#workshopList { border-radius: 0; border: none; }
QListWidget#workshopList::item { padding: 2px 8px; border-radius: 0;
    border-bottom: 1px solid #1e1e30; margin: 0; }
QListWidget#workshopList::item:selected { background: #252550; }

/* ===== Scrollbar ===== */
QScrollBar:vertical { background: transparent; width: 6px; }
QScrollBar::handle:vertical { background: #353555; border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #454570; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; height: 0; }
QScrollBar:horizontal { background: transparent; height: 6px; }
QScrollBar::handle:horizontal { background: #353555; border-radius: 3px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { height: 0; }

/* ===== Tabs ===== */
QTabWidget::pane { border: 1px solid #252540; background: #1b1b2a; top: -1px; }
QTabBar::tab { background: #151522; color: #666; padding: 7px 16px;
    border: 1px solid #252540; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    margin-right: 1px; font-weight: 600; font-size: 11px; }
QTabBar::tab:selected { background: #1b1b2a; color: #7c8aff; }
QTabBar::tab:hover:!selected { background: #202035; color: #aaa; }

/* ===== Splitter ===== */
QSplitter::handle { background: #252540; }
QSplitter::handle:horizontal { width: 1px; }

/* ===== Labels ===== */
QLabel { color: #d0d4dc; background: transparent; }
QLabel#heading { font-size: 16px; font-weight: 700; color: #7c8aff; }
QLabel#subheading { font-size: 12px; color: #7a7e90; }
QLabel#statLabel { font-size: 10px; color: #555; }
QLabel#cardTitle { font-size: 12px; font-weight: 700; color: #d0d4dc; }
QLabel#cardStat { font-size: 10px; color: #5a5e70; }
QLabel#installedCheck { color: #4CAF50; font-size: 13px; font-weight: bold; }

/* ===== GroupBox ===== */
QGroupBox { border: 1px solid #252540; border-radius: 6px; margin-top: 10px;
    padding-top: 14px; font-weight: 700; font-size: 11px; color: #7c8aff; background: #1a1a2a; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 6px; }

/* ===== ComboBox ===== */
QComboBox { background: #151522; color: #d0d4dc; border: 1px solid #353555;
    border-radius: 5px; padding: 4px 8px; font-size: 11px; min-width: 70px; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #1e1e35; color: #d0d4dc;
    border: 1px solid #353555; selection-background-color: #353555; }

/* ===== CheckBox ===== */
QCheckBox { spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #353555;
    border-radius: 3px; background: #151522; }
QCheckBox::indicator:checked { background: #3d5afe; border-color: #3d5afe; }

/* ===== ProgressBar ===== */
QProgressBar { background: #151522; border: 1px solid #252540; border-radius: 5px;
    text-align: center; color: #d0d4dc; height: 18px; font-size: 10px; }
QProgressBar::chunk { background: #3d5afe; border-radius: 4px; }

/* ===== StatusBar ===== */
QStatusBar { background: #151522; color: #555; border-top: 1px solid #252540; padding: 1px; font-size: 10px; }

/* ===== Misc ===== */
QHeaderView::section { background: #151522; color: #9a9eb0; padding: 5px;
    border: none; border-right: 1px solid #252540; font-weight: 700; font-size: 11px; }
QToolTip { background: #262640; color: #d0d4dc; border: 1px solid #353555;
    padding: 4px 8px; border-radius: 4px; font-size: 11px; }
QSpinBox { background: #151522; color: #d0d4dc; border: 1px solid #353555;
    border-radius: 5px; padding: 3px 6px; }

/* ===== Instance cards ===== */
QFrame#instanceCard { background: #202038; border: 2px solid #2a2a44;
    border-radius: 10px; }
QFrame#instanceCard:hover { border-color: #404068; background: #252544; }
QFrame#instanceCardSelected { background: #252550; border: 2px solid #3d5afe; border-radius: 10px; }

QScrollArea { border: none; background: transparent; }
"""