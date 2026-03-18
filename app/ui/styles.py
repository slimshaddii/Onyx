# Onyx Launcher — Prism-inspired dark theme
# Palette: #222222 (bg), #323232 (panels), #ffffff (text), #74d4cc (accent)

THEME_COLORS: dict[str, dict[str, str]] = {
    'dark': {
        'bg':          '#222222',
        'bg_mid':      '#2a2a2a',
        'bg_panel':    '#1a1a1a',
        'bg_card':     '#323232',
        'border':      '#3a3a3a',
        'text':        '#ffffff',
        'text_dim':    '#888888',
        'text_faint':  '#aaaaaa',
        'accent':      '#74d4cc',
        'error':       '#ff4444',
        'warning':     '#ff8800',
        'order':       '#ffaa00',
        'success':     '#4CAF50',
        'item_normal': '#e0e0e0',
    },
    'light': {
        'bg':          '#f0f0f0',
        'bg_mid':      '#e8e8e8',
        'bg_panel':    '#ffffff',
        'bg_card':     '#e0e0e0',
        'border':      '#c0c0c0',
        'text':        '#1a1a1a',
        'text_dim':    '#666666',
        'text_faint':  '#444444',
        'accent':      '#2a9d96',
        'error':       '#cc0000',
        'warning':     '#cc6600',
        'order':       '#997700',
        'success':     '#2e7d32',
        'item_normal': '#1a1a1a',
    },
}


def get_colors(theme: str = 'dark') -> dict[str, str]:
    """Return color tokens for the given theme ('dark' or 'light')."""
    return THEME_COLORS.get(theme, THEME_COLORS['dark'])

DARK_STYLESHEET = """
/* ===== Base ===== */
QMainWindow, QDialog { background-color: #222222; color: #ffffff; }
QWidget { background: #222222; color: #ffffff; font-family: "Segoe UI"; font-size: 12px; }
QAbstractScrollArea { background: #222222; }
QDialog { background: #222222; }
QWidget#centralWidget { background: #222222; }

/* ===== Toolbar ===== */
QToolBar { background: #1a1a1a; border-bottom: 1px solid #3a3a3a; spacing: 1px; padding: 3px 6px; }
QToolBar::separator { width: 1px; background: #3a3a3a; margin: 3px 4px; }
QToolButton { background: transparent; color: #b0b0b0; border: none; border-radius: 5px;
    padding: 5px 10px; font-size: 11px; font-weight: 600; }
QToolButton:hover { background: #3a3a3a; color: #ffffff; }
QToolButton:pressed { background: #444444; }

/* ===== Buttons ===== */
QPushButton { background: #3a3a3a; color: #ffffff; border: 1px solid #4a4a4a;
    border-radius: 5px; padding: 5px 14px; font-weight: 600; font-size: 11px; }
QPushButton:hover { background: #4a4a4a; }
QPushButton:pressed { background: #555555; }
QPushButton:disabled { background: #2a2a2a; color: #555555; border-color: #333333; }

/* primaryButton — explicit state rules to prevent disabled bleed-through */
QPushButton#primaryButton          { background: #74d4cc; color: #1a1a1a; border: none; font-weight: 700; }
QPushButton#primaryButton:hover    { background: #8ae0d8; color: #1a1a1a; }
QPushButton#primaryButton:pressed  { background: #5cc0b8; color: #1a1a1a; }
QPushButton#primaryButton:disabled { background: #2a6a66; color: #1a1a1a; border: none; opacity: 0.5; }
QPushButton#primaryButton:enabled  { background: #74d4cc; color: #1a1a1a; border: none; }

/* dangerButton */
QPushButton#dangerButton          { background: #cc3333; color: #ffffff; border: none; }
QPushButton#dangerButton:hover    { background: #e04040; color: #ffffff; }
QPushButton#dangerButton:pressed  { background: #aa2222; color: #ffffff; }
QPushButton#dangerButton:disabled { background: #4a1a1a; color: #888888; border: none; }
QPushButton#dangerButton:enabled  { background: #cc3333; color: #ffffff; border: none; }

/* successButton */
QPushButton#successButton          { background: #3a8a3e; color: #ffffff; border: none; }
QPushButton#successButton:hover    { background: #4a9e4e; color: #ffffff; }
QPushButton#successButton:pressed  { background: #2a7a2e; color: #ffffff; }
QPushButton#successButton:disabled { background: #1a3a1e; color: #888888; border: none; }
QPushButton#successButton:enabled  { background: #3a8a3e; color: #ffffff; border: none; }

/* subscribeBtn / installedBtn */
QPushButton#subscribeBtn { background: #3a8a3e; color: #ffffff; border: none;
    font-size: 13px; padding: 8px 22px; border-radius: 3px; }
QPushButton#subscribeBtn:hover { background: #4a9e4e; }
QPushButton#installedBtn { background: #2a5a2e; color: #88cc88;
    border: 1px solid #3a7a3e; font-size: 13px; padding: 8px 22px; border-radius: 3px; }

/* ===== Inputs ===== */
QLineEdit, QTextEdit, QPlainTextEdit { background: #1a1a1a; color: #ffffff;
    border: 1px solid #4a4a4a; border-radius: 5px; padding: 5px 8px;
    selection-background-color: #74d4cc; selection-color: #1a1a1a; }
QLineEdit:focus, QTextEdit:focus { border-color: #74d4cc; }
QLineEdit#addressBar { background: #1a1a1a; border: 2px solid #4a4a4a;
    border-radius: 14px; padding: 5px 14px; font-size: 12px; font-family: "Consolas","Segoe UI"; }
QLineEdit#addressBar:focus { border-color: #74d4cc; }
QLineEdit#searchBar { background: #1a1a1a; border: 1px solid #4a4a4a;
    border-radius: 14px; padding: 6px 14px; font-size: 12px; }
QLineEdit#searchBar:focus { border-color: #74d4cc; }

/* ===== Lists ===== */
QListWidget { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 6px;
    outline: none; padding: 1px; }
QListWidget::item { padding: 3px 6px; border-radius: 3px; margin: 0px 1px; }
QListWidget::item:selected { background: #2a4a48; color: #74d4cc; }
QListWidget::item:hover:!selected { background: #2a2a2a; }
QListWidget#workshopList { border-radius: 0; border: none; }
QListWidget#workshopList::item { padding: 2px 8px; border-radius: 0;
    border-bottom: 1px solid #2a2a2a; margin: 0; }
QListWidget#workshopList::item:selected { background: #2a4a48; }

/* ===== Scrollbar ===== */
QScrollBar:vertical { background: transparent; width: 6px; }
QScrollBar::handle:vertical { background: #4a4a4a; border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #5a5a5a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; height: 0; }
QScrollBar:horizontal { background: transparent; height: 6px; }
QScrollBar::handle:horizontal { background: #4a4a4a; border-radius: 3px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { height: 0; }

/* ===== Tabs ===== */
QTabWidget::pane { border: 1px solid #3a3a3a; background: #222222; top: -1px; }
QTabBar::tab { background: #1a1a1a; color: #888888; padding: 7px 16px;
    border: 1px solid #3a3a3a; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    margin-right: 1px; font-weight: 600; font-size: 11px; }
QTabBar::tab:selected { background: #222222; color: #74d4cc; }
QTabBar::tab:hover:!selected { background: #2a2a2a; color: #cccccc; }

/* ===== Splitter ===== */
QSplitter::handle { background: #3a3a3a; }
QSplitter::handle:horizontal { width: 1px; }

/* ===== Labels ===== */
QLabel { color: #ffffff; background: transparent; }
QLabel#heading { font-size: 16px; font-weight: 700; color: #74d4cc; }
QLabel#subheading { font-size: 12px; color: #888888; }
QLabel#statLabel { font-size: 10px; color: #666666; }
QLabel#cardTitle { font-size: 12px; font-weight: 700; color: #ffffff; }
QLabel#cardStat { font-size: 10px; color: #777777; }
QLabel#installedCheck { color: #4CAF50; font-size: 13px; font-weight: bold; }

/* ===== GroupBox ===== */
QGroupBox { border: 1px solid #3a3a3a; border-radius: 6px; margin-top: 10px;
    padding-top: 14px; font-weight: 700; font-size: 11px; color: #74d4cc; background: #282828; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 6px; }

/* ===== ComboBox ===== */
QComboBox { background: #1a1a1a; color: #ffffff; border: 1px solid #4a4a4a;
    border-radius: 5px; padding: 4px 8px; font-size: 11px; min-width: 70px; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #2a2a2a; color: #ffffff;
    border: 1px solid #4a4a4a; selection-background-color: #2a4a48; }

/* ===== CheckBox ===== */
QCheckBox { spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #4a4a4a;
    border-radius: 3px; background: #1a1a1a; }
QCheckBox::indicator:checked { background: #74d4cc; border-color: #74d4cc; }

/* ===== ProgressBar ===== */
QProgressBar { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 5px;
    text-align: center; color: #ffffff; height: 18px; font-size: 10px; }
QProgressBar::chunk { background: #74d4cc; border-radius: 4px; }

/* ===== StatusBar ===== */
QStatusBar { background: #1a1a1a; color: #888888; border-top: 1px solid #3a3a3a;
    padding: 1px; font-size: 10px; }

/* ===== Misc ===== */
QHeaderView::section { background: #1a1a1a; color: #b0b0b0; padding: 5px;
    border: none; border-right: 1px solid #3a3a3a; font-weight: 700; font-size: 11px; }
QToolTip { background: #323232; color: #ffffff; border: 1px solid #4a4a4a;
    padding: 4px 8px; border-radius: 4px; font-size: 11px; }
QSpinBox { background: #1a1a1a; color: #ffffff; border: 1px solid #4a4a4a;
    border-radius: 5px; padding: 3px 6px; }

/* ===== Instance cards ===== */
QFrame#instanceCard { background: #323232; border: 2px solid #3a3a3a; border-radius: 10px; }
QFrame#instanceCard:hover { border-color: #555555; background: #3a3a3a; }
QFrame#instanceCardSelected { background: #2a4a48; border: 2px solid #74d4cc; border-radius: 10px; }

QScrollArea { border: none; background: transparent; }
"""

LIGHT_STYLESHEET = """
QMainWindow, QDialog { background-color: #f0f0f0; color: #1a1a1a; }
QWidget { background: #f0f0f0; color: #1a1a1a; font-family: "Segoe UI"; font-size: 12px; }
QAbstractScrollArea { background: #f0f0f0; }
QDialog { background: #f0f0f0; }
QWidget#centralWidget { background: #f0f0f0; }

QToolBar { background: #e0e0e0; border-bottom: 1px solid #c0c0c0;
           spacing: 1px; padding: 3px 6px; }
QToolButton { background: transparent; color: #333333; border: none;
              border-radius: 5px; padding: 5px 10px;
              font-size: 11px; font-weight: 600; }
QToolButton:hover { background: #d0d0d0; color: #000000; }
QToolButton:pressed { background: #c0c0c0; }

QPushButton { background: #e0e0e0; color: #1a1a1a;
              border: 1px solid #b0b0b0; border-radius: 5px;
              padding: 5px 14px; font-weight: 600; font-size: 11px; }
QPushButton:hover { background: #d0d0d0; }
QPushButton:pressed { background: #c0c0c0; }
QPushButton:disabled { background: #ececec; color: #aaaaaa; border-color: #cccccc; }

QPushButton#primaryButton         { background: #5bbdb5; color: #ffffff; border: none; font-weight: 700; }
QPushButton#primaryButton:hover   { background: #4aada5; color: #ffffff; }
QPushButton#primaryButton:pressed { background: #3a9d95; color: #ffffff; }
QPushButton#primaryButton:disabled { background: #aaddd9; color: #ffffff; border: none; }
QPushButton#primaryButton:enabled  { background: #5bbdb5; color: #ffffff; border: none; }

QPushButton#dangerButton          { background: #cc3333; color: #ffffff; border: none; }
QPushButton#dangerButton:hover    { background: #e04040; color: #ffffff; }
QPushButton#dangerButton:disabled { background: #e8b0b0; color: #888888; border: none; }
QPushButton#dangerButton:enabled  { background: #cc3333; color: #ffffff; border: none; }

QPushButton#successButton          { background: #3a8a3e; color: #ffffff; border: none; }
QPushButton#successButton:hover    { background: #4a9e4e; color: #ffffff; }
QPushButton#successButton:disabled { background: #b0d8b2; color: #888888; border: none; }
QPushButton#successButton:enabled  { background: #3a8a3e; color: #ffffff; border: none; }

QLineEdit, QTextEdit, QPlainTextEdit { background: #ffffff; color: #1a1a1a;
    border: 1px solid #c0c0c0; border-radius: 5px; padding: 5px 8px; }
QLineEdit:focus, QTextEdit:focus { border-color: #5bbdb5; }

QListWidget, QTreeWidget { background: #ffffff; border: 1px solid #c0c0c0;
    border-radius: 6px; outline: none; }
QListWidget::item { padding: 3px 6px; border-radius: 3px; }
QListWidget::item:selected { background: #c8eae8; color: #1a1a1a; }
QListWidget::item:hover:!selected { background: #e8e8e8; }

QScrollBar:vertical { background: transparent; width: 6px; }
QScrollBar::handle:vertical { background: #c0c0c0; border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #a0a0a0; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; height: 0; }

QTabWidget::pane { border: 1px solid #c0c0c0; background: #f0f0f0; }
QTabBar::tab { background: #e0e0e0; color: #555555; padding: 7px 16px;
               border: 1px solid #c0c0c0; border-bottom: none;
               border-top-left-radius: 6px; border-top-right-radius: 6px;
               margin-right: 1px; font-weight: 600; font-size: 11px; }
QTabBar::tab:selected { background: #f0f0f0; color: #5bbdb5; }
QTabBar::tab:hover:!selected { background: #d8d8d8; color: #333333; }

QSplitter::handle { background: #c0c0c0; }
QSplitter::handle:horizontal { width: 1px; }

QLabel { color: #1a1a1a; background: transparent; }
QGroupBox { border: 1px solid #c0c0c0; border-radius: 6px;
            margin-top: 10px; padding-top: 14px;
            font-weight: 700; font-size: 11px; color: #5bbdb5;
            background: #e8e8e8; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 6px; }

QComboBox { background: #ffffff; color: #1a1a1a; border: 1px solid #c0c0c0;
            border-radius: 5px; padding: 4px 8px; font-size: 11px; }
QComboBox QAbstractItemView { background: #ffffff; color: #1a1a1a;
    border: 1px solid #c0c0c0; selection-background-color: #c8eae8; }

QProgressBar { background: #e0e0e0; border: 1px solid #c0c0c0;
               border-radius: 5px; text-align: center;
               color: #1a1a1a; height: 18px; }
QProgressBar::chunk { background: #5bbdb5; border-radius: 4px; }

QStatusBar { background: #e0e0e0; color: #555555; border-top: 1px solid #c0c0c0; }
QToolTip { background: #ffffff; color: #1a1a1a; border: 1px solid #c0c0c0;
           padding: 4px 8px; border-radius: 4px; font-size: 11px; }

QFrame#instanceCard { background: #e8e8e8; border: 2px solid #d0d0d0; border-radius: 10px; }
QFrame#instanceCard:hover { border-color: #b0b0b0; background: #e0e0e0; }
QFrame#instanceCardSelected { background: #c8eae8; border: 2px solid #5bbdb5; border-radius: 10px; }
QScrollArea { border: none; background: transparent; }
"""