from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QGroupBox, QListWidget, QListWidgetItem,
    QTabWidget, QWidget, QFileDialog, QComboBox, QSplitter
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCharFormat, QColor, QFont

from app.core.log_parser import LogParser, LogIssue
from app.core.instance import Instance
from typing import Optional


class LogViewerDialog(QDialog):
    def __init__(self, parent, log_parser: LogParser,
                 instance: Optional[Instance] = None):
        super().__init__(parent)
        self.log_parser = log_parser
        self.instance = instance

        self.setWindowTitle("Log Viewer & Troubleshooter")
        self.setMinimumSize(900, 650)
        self._build_ui()
        self._auto_load_log()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Top bar
        top_bar = QHBoxLayout()

        self.log_path_label = QLabel("No log loaded")
        self.log_path_label.setStyleSheet("color: #6c7086;")
        top_bar.addWidget(self.log_path_label, 1)

        self.load_btn = QPushButton("📂 Open Log")
        self.load_btn.clicked.connect(self._on_open_log)
        top_bar.addWidget(self.load_btn)

        self.auto_load_btn = QPushButton("🔄 Auto-detect")
        self.auto_load_btn.clicked.connect(self._auto_load_log)
        top_bar.addWidget(self.auto_load_btn)

        self.refresh_btn = QPushButton("⟳ Refresh")
        self.refresh_btn.clicked.connect(self._refresh)
        top_bar.addWidget(self.refresh_btn)

        layout.addLayout(top_bar)

        tabs = QTabWidget()

        # Log View Tab
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search logs...")
        self.search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self.search_input)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Errors Only", "Warnings Only", "Info Only"])
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.filter_combo.setFixedWidth(140)
        search_layout.addWidget(self.filter_combo)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(search_btn)

        log_layout.addLayout(search_layout)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 10))
        self.log_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        log_layout.addWidget(self.log_view)

        # Stats bar
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #a6adc8;")
        log_layout.addWidget(self.stats_label)

        tabs.addTab(log_tab, "📄 Log View")

        # Troubleshooter Tab
        trouble_tab = QWidget()
        trouble_layout = QVBoxLayout(trouble_tab)

        self.issues_list = QListWidget()
        self.issues_list.setSpacing(2)
        self.issues_list.itemClicked.connect(self._on_issue_selected)
        trouble_layout.addWidget(self.issues_list)

        self.issue_detail = QTextEdit()
        self.issue_detail.setReadOnly(True)
        self.issue_detail.setMaximumHeight(200)
        self.issue_detail.setPlaceholderText("Click an issue to see details and suggestions...")
        trouble_layout.addWidget(self.issue_detail)

        tabs.addTab(trouble_tab, "🔧 Troubleshooter")

        # Summary Tab
        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)

        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        summary_layout.addWidget(self.summary_text)

        export_btn = QPushButton("📤 Export Summary")
        export_btn.clicked.connect(self._export_summary)
        summary_layout.addWidget(export_btn)

        tabs.addTab(summary_tab, "📊 Summary")

        layout.addWidget(tabs)

        # Close
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _auto_load_log(self):
        instance_path = self.instance.path if self.instance else None
        log_path = self.log_parser.find_player_log(instance_path)
        if log_path:
            self._load_log(log_path)
        else:
            self.log_path_label.setText("No log file found. Launch the game first.")

    def _on_open_log(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Log File", "",
                                               "Log Files (*.log *.txt);;All Files (*)")
        if path:
            self._load_log(Path(path))

    def _load_log(self, path: Path):
        if self.log_parser.parse_file(path):
            self.log_path_label.setText(f"📄 {path}")
            self._display_log()
            self._run_analysis()
        else:
            self.log_path_label.setText(f"Failed to load: {path}")

    def _refresh(self):
        path_text = self.log_path_label.text()
        if path_text.startswith("📄 "):
            path = Path(path_text[2:].strip())
            self._load_log(path)
        else:
            self._auto_load_log()

    def _display_log(self, entries=None):
        if entries is None:
            entries = self.log_parser.entries

        self.log_view.setUpdatesEnabled(False)
        self.log_view.clear()
        cursor = self.log_view.textCursor()

        error_fmt = QTextCharFormat()
        error_fmt.setForeground(QColor("#f38ba8"))
        error_fmt.setFontWeight(QFont.Weight.Bold)
        warn_fmt = QTextCharFormat()
        warn_fmt.setForeground(QColor("#fab387"))
        info_fmt = QTextCharFormat()
        info_fmt.setForeground(QColor("#cdd6f4"))

        for entry in entries:
            if entry.level == 'ERROR':
                cursor.setCharFormat(error_fmt)
            elif entry.level == 'WARNING':
                cursor.setCharFormat(warn_fmt)
            else:
                cursor.setCharFormat(info_fmt)
            cursor.insertText(f"[{entry.line_number:5d}] {entry.message}\n")

        self.log_view.setTextCursor(cursor)
        self.log_view.setUpdatesEnabled(True)
        self.log_view.moveCursor(cursor.MoveOperation.Start)

        errors = self.log_parser.get_error_count()
        warnings = self.log_parser.get_warning_count()
        total = len(self.log_parser.entries)
        self.stats_label.setText(
            f"Total: {total} lines | "
            f"🔴 {errors} errors | "
            f"🟡 {warnings} warnings | "
            f"Showing: {len(entries)} lines"
        )

        errors = self.log_parser.get_error_count()
        warnings = self.log_parser.get_warning_count()
        total = len(self.log_parser.entries)
        self.stats_label.setText(
            f"Total: {total} lines | "
            f"🔴 {errors} errors | "
            f"🟡 {warnings} warnings | "
            f"Showing: {len(entries)} lines"
        )

    def _on_search(self):
        query = self.search_input.text().strip()
        if query:
            results = self.log_parser.search(query)
            self._display_log(results)
        else:
            self._display_log()

    def _on_filter_changed(self):
        idx = self.filter_combo.currentIndex()
        if idx == 0:
            self._display_log()
        elif idx == 1:
            entries = [e for e in self.log_parser.entries if e.level == 'ERROR']
            self._display_log(entries)
        elif idx == 2:
            entries = [e for e in self.log_parser.entries if e.level == 'WARNING']
            self._display_log(entries)
        elif idx == 3:
            entries = [e for e in self.log_parser.entries if e.level == 'INFO']
            self._display_log(entries)

    def _run_analysis(self):
        issues = self.log_parser.analyze()
        self.issues_list.clear()

        if not issues:
            item = QListWidgetItem("✅ No known issues detected!")
            item.setForeground(QColor("#a6e3a1"))
            self.issues_list.addItem(item)
        else:
            for issue in issues:
                icon = {'error': '🔴', 'warning': '🟡', 'info': 'ℹ️'}.get(issue.severity, '❔')
                count_str = f" (×{issue.count})" if issue.count > 1 else ""
                item = QListWidgetItem(f"{icon} {issue.title}{count_str}")
                item.setData(Qt.ItemDataRole.UserRole, issue)

                color = {
                    'error': QColor("#f38ba8"),
                    'warning': QColor("#fab387"),
                    'info': QColor("#89b4fa"),
                }.get(issue.severity, QColor("#cdd6f4"))
                item.setForeground(color)
                self.issues_list.addItem(item)

        # Generate summary
        self._generate_summary(issues)

    def _on_issue_selected(self, item):
        issue = item.data(Qt.ItemDataRole.UserRole)
        if issue:
            self.issue_detail.setHtml(
                f"<h3 style='color: #89b4fa'>{issue.title}</h3>"
                f"<p><b>Severity:</b> {issue.severity.upper()}</p>"
                f"<p><b>Occurrences:</b> {issue.count}</p>"
                f"<p><b>Description:</b> {issue.description}</p>"
                f"<p style='color: #a6e3a1'><b>Suggestion:</b> {issue.suggestion}</p>"
                f"{'<p><b>Related mod:</b> ' + issue.related_mod + '</p>' if issue.related_mod else ''}"
            )

    def _generate_summary(self, issues: list[LogIssue]):
        errors = self.log_parser.get_error_count()
        warnings = self.log_parser.get_warning_count()
        total = len(self.log_parser.entries)

        html = f"""
        <h2 style='color: #89b4fa'>Log Analysis Summary</h2>
        <p>Total log lines: <b>{total}</b></p>
        <p style='color: #f38ba8'>Errors: <b>{errors}</b></p>
        <p style='color: #fab387'>Warnings: <b>{warnings}</b></p>
        <hr>
        <h3>Detected Issues ({len(issues)})</h3>
        """

        if issues:
            for issue in issues:
                icon = {'error': '🔴', 'warning': '🟡', 'info': 'ℹ️'}.get(issue.severity, '')
                html += f"<p>{icon} <b>{issue.title}</b> (×{issue.count}) — {issue.suggestion}</p>"
        else:
            html += "<p style='color: #a6e3a1'>✅ No known issues detected!</p>"

        html += """
        <hr>
        <h3>General Tips</h3>
        <ul>
            <li>Errors during startup are usually mod-related</li>
            <li>NullReferenceException often means mod conflicts or missing dependencies</li>
            <li>Check load order if you see "patch operation failed" errors</li>
            <li>Cross-reference errors mean a mod is referencing defs from another mod that's not loaded</li>
            <li>Harmless errors (like RocketMan leftovers) can be safely ignored</li>
        </ul>
        """

        if self.instance:
            html += f"""
            <hr>
            <h3>Instance Info</h3>
            <p>Instance: <b>{self.instance.name}</b></p>
            <p>Active mods: <b>{self.instance.mod_count}</b></p>
            <p>Save files: <b>{self.instance.save_count}</b></p>
            """

        self.summary_text.setHtml(html)

    def _export_summary(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Summary", "log_summary.html",
                                               "HTML Files (*.html);;Text Files (*.txt)")
        if path:
            if path.endswith('.html'):
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(self.summary_text.toHtml())
            else:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(self.summary_text.toPlainText())