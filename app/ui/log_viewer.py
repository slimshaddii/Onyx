"""Log viewer and troubleshooter dialog for RimWorld instance logs."""

from pathlib import Path

from PyQt6.QtWidgets import (  # pylint: disable=no-name-in-module
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QListWidget, QListWidgetItem,
    QTabWidget, QWidget, QFileDialog, QComboBox,
)
from PyQt6.QtCore import Qt  # pylint: disable=no-name-in-module
from PyQt6.QtGui import QTextCharFormat, QColor, QFont  # pylint: disable=no-name-in-module

from app.core.app_settings import AppSettings
from app.core.instance import Instance
from app.core.log_parser import LogParser, LogIssue
from app.ui.styles import get_colors


def _c() -> dict:
    """Return the current theme color dict."""
    return get_colors(AppSettings.instance().theme)


class LogViewerDialog(QDialog):
    """Log viewer and troubleshooter for RimWorld Player.log files."""

    def __init__(self, parent, log_parser: LogParser,
                 instance: Instance | None = None):
        super().__init__(parent)
        self.log_parser = log_parser
        self.instance   = instance
        self._current_log_path: Path | None = None

        self.log_path_label: QLabel | None     = None
        self.load_btn:       QPushButton | None = None
        self.auto_load_btn:  QPushButton | None = None
        self.refresh_btn:    QPushButton | None = None
        self.search_input:   QLineEdit | None   = None
        self.filter_combo:   QComboBox | None    = None
        self.log_view:       QTextEdit | None    = None
        self.stats_label:    QLabel | None       = None
        self.issues_list:    QListWidget | None  = None
        self.issue_detail:   QTextEdit | None    = None
        self.summary_text:   QTextEdit | None    = None
        self.startup_text:   QTextEdit | None    = None

        self.setWindowTitle("Log Viewer & Troubleshooter")
        self.setMinimumSize(900, 650)
        self._build_ui()
        self._auto_load_log()

    def _build_ui(self):
        """Build the log viewer layout with tabs."""
        layout = QVBoxLayout(self)

        layout.addLayout(self._build_top_bar())

        tabs = QTabWidget()
        tabs.addTab(self._build_log_tab(), "📄 Log View")
        tabs.addTab(
            self._build_trouble_tab(), "🔧 Troubleshooter")
        tabs.addTab(
            self._build_summary_tab(), "📊 Summary")
        tabs.addTab(
            self._build_startup_tab(), "⚡ Startup Analysis")
        layout.addWidget(tabs)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _build_top_bar(self) -> QHBoxLayout:
        """Build the top toolbar with path label and buttons."""
        top_bar = QHBoxLayout()

        self.log_path_label = QLabel("No log loaded")
        self.log_path_label.setObjectName("statLabel")
        top_bar.addWidget(self.log_path_label, 1)

        self.load_btn = QPushButton("📂 Open Log")
        self.load_btn.clicked.connect(self._on_open_log)
        top_bar.addWidget(self.load_btn)

        self.auto_load_btn = QPushButton("🔄 Auto-detect")
        self.auto_load_btn.clicked.connect(
            self._auto_load_log)
        top_bar.addWidget(self.auto_load_btn)

        self.refresh_btn = QPushButton("⟳ Refresh")
        self.refresh_btn.clicked.connect(self._refresh)
        top_bar.addWidget(self.refresh_btn)

        return top_bar

    def _build_log_tab(self) -> QWidget:
        """Build the log view tab."""
        log_tab    = QWidget()
        log_layout = QVBoxLayout(log_tab)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "🔍 Search logs...")
        self.search_input.returnPressed.connect(
            self._on_search)
        search_layout.addWidget(self.search_input)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(
            ["All", "Errors Only", "Warnings Only",
             "Info Only"])
        self.filter_combo.currentIndexChanged.connect(
            self._on_filter_changed)
        self.filter_combo.setFixedWidth(140)
        search_layout.addWidget(self.filter_combo)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(search_btn)

        log_layout.addLayout(search_layout)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 12))
        self.log_view.setLineWrapMode(
            QTextEdit.LineWrapMode.NoWrap)
        log_layout.addWidget(self.log_view)

        self.stats_label = QLabel("")
        self.stats_label.setObjectName("subheading")
        log_layout.addWidget(self.stats_label)

        return log_tab

    def _build_trouble_tab(self) -> QWidget:
        """Build the troubleshooter tab."""
        trouble_tab    = QWidget()
        trouble_layout = QVBoxLayout(trouble_tab)

        self.issues_list = QListWidget()
        self.issues_list.setSpacing(2)
        self.issues_list.itemClicked.connect(
            self._on_issue_selected)
        trouble_layout.addWidget(self.issues_list)

        self.issue_detail = QTextEdit()
        self.issue_detail.setReadOnly(True)
        self.issue_detail.setMaximumHeight(200)
        self.issue_detail.setPlaceholderText(
            "Click an issue to see details and suggestions...")
        trouble_layout.addWidget(self.issue_detail)

        return trouble_tab

    def _build_summary_tab(self) -> QWidget:
        """Build the summary tab."""
        summary_tab    = QWidget()
        summary_layout = QVBoxLayout(summary_tab)

        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        summary_layout.addWidget(self.summary_text)

        export_btn = QPushButton("📤 Export Summary")
        export_btn.clicked.connect(self._export_summary)
        summary_layout.addWidget(export_btn)

        return summary_tab

    def _build_startup_tab(self) -> QWidget:
        """Build the startup analysis tab."""
        startup_tab    = QWidget()
        startup_layout = QVBoxLayout(startup_tab)

        self.startup_text = QTextEdit()
        self.startup_text.setReadOnly(True)
        startup_layout.addWidget(self.startup_text)

        return startup_tab

    # ── Log loading ───────────────────────────────────────────────────

    def _auto_load_log(self):
        """Auto-detect and load the Player.log file."""
        instance_path = (
            self.instance.path if self.instance else None)
        log_path = self.log_parser.find_player_log(
            instance_path)
        if log_path:
            self._load_log(log_path)
            if self.instance:
                self.log_path_label.setText(
                    f"📄 {self.instance.name} — {log_path}")
        else:
            if self.instance:
                self.log_path_label.setText(
                    f"No log for '{self.instance.name}'. "
                    f"Launch the game first.")
            else:
                self.log_path_label.setText(
                    "No log file found. "
                    "Launch the game first.")

    def _on_open_log(self):
        """Open a log file via file picker."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Log File", "",
            "Log Files (*.log *.txt);;All Files (*)")
        if path:
            self._load_log(Path(path))

    def _load_log(self, path: Path):
        """Parse and display a log file."""
        self._current_log_path = path
        if self.log_parser.parse_file(path):
            self.log_path_label.setText(f"📄 {path}")
            self._display_log()
            self._run_analysis()
        else:
            self.log_path_label.setText(
                f"Failed to load: {path}")

    def _refresh(self):
        """Reload the current log file."""
        if self._current_log_path:
            self._load_log(self._current_log_path)
        else:
            self._auto_load_log()

    # ── Log display ───────────────────────────────────────────────────

    def _display_log(self, entries=None):
        """Render log entries into the log view widget."""
        if entries is None:
            entries = self.log_parser.entries

        self.log_view.setUpdatesEnabled(False)
        self.log_view.clear()
        cursor = self.log_view.textCursor()

        colors = _c()

        error_fmt = QTextCharFormat()
        error_fmt.setForeground(QColor(colors['error']))
        error_fmt.setFontWeight(QFont.Weight.Bold)
        warn_fmt = QTextCharFormat()
        warn_fmt.setForeground(QColor(colors['warning']))
        info_fmt = QTextCharFormat()
        info_fmt.setForeground(QColor(colors['text']))

        for entry in entries:
            if entry.level == 'ERROR':
                cursor.setCharFormat(error_fmt)
            elif entry.level == 'WARNING':
                cursor.setCharFormat(warn_fmt)
            else:
                cursor.setCharFormat(info_fmt)
            cursor.insertText(
                f"[{entry.line_number:5d}] "
                f"{entry.message}\n")

        self.log_view.setTextCursor(cursor)
        self.log_view.setUpdatesEnabled(True)
        self.log_view.moveCursor(
            cursor.MoveOperation.Start)

        errors   = self.log_parser.get_error_count()
        warnings = self.log_parser.get_warning_count()
        total    = len(self.log_parser.entries)
        self.stats_label.setText(
            f"Total: {total} lines | "
            f"🔴 {errors} errors | "
            f"🟡 {warnings} warnings | "
            f"Showing: {len(entries)} lines")

    def _on_search(self):
        """Filter log entries by search query."""
        query = self.search_input.text().strip()
        if query:
            results = self.log_parser.search(query)
            self._display_log(results)
        else:
            self._display_log()

    def _on_filter_changed(self):
        """Filter log entries by level."""
        idx = self.filter_combo.currentIndex()
        if idx == 0:
            self._display_log()
            return

        level_map = {1: 'ERROR', 2: 'WARNING', 3: 'INFO'}
        level = level_map.get(idx)
        if level:
            entries = [
                e for e in self.log_parser.entries
                if e.level == level]
            self._display_log(entries)

    # ── Analysis ──────────────────────────────────────────────────────

    def _run_analysis(self):
        """Run issue analysis and populate tabs."""
        issues = self.log_parser.analyze()
        self._populate_issues(issues)
        self._generate_summary(issues)
        self._generate_startup_analysis()

    def _populate_issues(self, issues: list[LogIssue]):
        """Fill the troubleshooter issue list."""
        self.issues_list.clear()
        colors = _c()

        if not issues:
            item = QListWidgetItem(
                "✅ No known issues detected!")
            item.setForeground(QColor("#a6e3a1"))
            self.issues_list.addItem(item)
            return

        color_map = {
            'error':   QColor(colors['error']),
            'warning': QColor(colors['warning']),
            'info':    QColor(colors['accent']),
        }
        default_color = QColor(colors['text'])
        for issue in issues:
            icon = {
                'error': '🔴', 'warning': '🟡',
                'info': 'ℹ️',
            }.get(issue.severity, '❔')
            count_str = (
                f" (×{issue.count})"
                if issue.count > 1 else "")
            item = QListWidgetItem(
                f"{icon} {issue.title}{count_str}")
            item.setData(
                Qt.ItemDataRole.UserRole, issue)
            item.setForeground(
                color_map.get(
                    issue.severity, default_color))
            self.issues_list.addItem(item)

    def _generate_startup_analysis(self):
        """Parse and display startup timing and memory."""
        colors   = _c()
        analysis = self.log_parser.parse_startup_analysis()

        if not analysis.phases and not analysis.memory_stats:
            self.startup_text.setHtml(
                f"<p style='color:{colors['text_dim']};'>"
                f"No startup data found. Launch the game "
                f"and reload the log.</p>")
            return

        parts: list[str] = []
        parts.append(
            f"<h2 style='color:{colors['accent']};'>"
            f"Startup Analysis</h2>")

        if analysis.game_version:
            parts.append(
                f"<p>RimWorld "
                f"<b>{analysis.game_version}</b></p>")

        if analysis.total_startup_s > 0:
            parts.append(
                f"<p>Estimated total startup: "
                f"<b style='color:{colors['warning']};'>"
                f"{analysis.total_startup_s:.1f}s</b></p>")

        if analysis.phases:
            parts.append(
                self._render_phases(analysis, colors))

        if analysis.memory_stats:
            parts.append(
                self._render_memory(analysis, colors))

        parts.append(
            self._render_assembly_info(analysis, colors))
        parts.append(self._render_tips(analysis, colors))

        self.startup_text.setHtml(''.join(parts))

    def _render_phases(self, analysis, colors) -> str:
        """Render the startup phases HTML table."""
        html = (
            f"<hr><h3 style='color:{colors['accent']};'>"
            f"Startup Phases</h3>"
            f"<table width='100%' cellspacing='4'>"
            f"<tr>"
            f"<th align='left' "
            f"style='color:{colors['text_dim']};'>"
            f"Phase</th>"
            f"<th align='right' "
            f"style='color:{colors['text_dim']};'>"
            f"Duration</th>"
            f"<th align='left' "
            f"style='color:{colors['text_dim']};'>"
            f"Impact</th></tr>")

        sorted_phases = sorted(
            analysis.phases,
            key=lambda p: p.seconds, reverse=True)
        max_sec = (max(p.seconds for p in sorted_phases)
                   if sorted_phases else 1)

        for phase in sorted_phases:
            pct = (phase.seconds / max_sec
                   if max_sec > 0 else 0)

            if pct >= 0.7:
                color, impact = colors['error'], 'High'
            elif pct >= 0.3:
                color, impact = colors['warning'], 'Medium'
            else:
                color, impact = colors['success'], 'Low'

            bar_len = int(pct * 20)
            bar = '█' * bar_len + '░' * (20 - bar_len)

            html += (
                f"<tr>"
                f"<td style='color:{colors['text']};'>"
                f"{phase.name}</td>"
                f"<td align='right' "
                f"style='color:{color};'>"
                f"<b>{phase.display}</b></td>"
                f"<td style='color:{color}; "
                f"font-family:monospace;'>"
                f" {bar} {impact}</td></tr>")

        html += "</table>"

        if analysis.assembly_time_s > 3.0:
            html += (
                f"<p style='color:{colors['warning']};'>"
                f"Assembly loading took "
                f"{analysis.assembly_time_s:.2f}s. "
                f"More C# mods = longer load time.</p>")

        return html

    def _render_memory(self, analysis, colors) -> str:
        """Render the memory stats HTML table."""
        html = (
            f"<hr><h3 style='color:{colors['accent']};'>"
            f"Peak Memory Usage</h3>"
            f"<table width='100%' cellspacing='4'>")

        total_mb = sum(
            s.peak_mb for s in analysis.memory_stats)

        for stat in sorted(
                analysis.memory_stats,
                key=lambda s: s.peak_mb, reverse=True):
            if stat.peak_mb >= 512:
                color = colors['error']
            elif stat.peak_mb >= 256:
                color = colors['warning']
            else:
                color = colors['text']

            display = (f"{stat.peak_mb / 1024:.2f} GB"
                       if stat.peak_mb >= 1024
                       else f"{stat.peak_mb:.0f} MB")

            html += (
                f"<tr>"
                f"<td style='color:{colors['text']};'>"
                f"{stat.name}</td>"
                f"<td align='right' "
                f"style='color:{color};'>"
                f"<b>{display}</b></td></tr>")

        html += "</table>"

        if total_mb >= 3072:
            html += (
                f"<p style='color:{colors['error']};'>"
                f"Total peak memory exceeds 3 GB. "
                f"Consider reducing mod count if "
                f"experiencing crashes.</p>")
        elif total_mb >= 2048:
            html += (
                f"<p style='color:{colors['warning']};'>"
                f"Total peak memory is high "
                f"({total_mb / 1024:.1f} GB). "
                f"Monitor for out-of-memory issues.</p>")

        return html

    def _render_assembly_info(self, analysis,
                              colors) -> str:
        """Render the assembly info section."""
        return (
            f"<hr>"
            f"<h3 style='color:{colors['accent']};'>"
            f"Assembly Info</h3>"
            f"<p>Assemblies loaded: "
            f"<b>{analysis.csharp_mod_count}</b></p>"
            f"<p style='color:{colors['text_dim']};'>"
            f"Each C# mod adds to startup time. "
            f"XML-only mods load much faster.</p>")

    def _render_tips(self, analysis, colors) -> str:
        """Render the tips section based on detected mods."""
        html = (
            f"<hr><h3 style='color:{colors['accent']};'>"
            f"Tips</h3><ul>")

        if analysis.assembly_time_s > 5.0:
            html += (
                f"<li style='color:{colors['warning']};'>"
                f"Assembly load time is high "
                f"({analysis.assembly_time_s:.1f}s). "
                f"Harmony and Prepatcher reduce this "
                f"for subsequent launches.</li>")

        log_text = self.log_parser.raw_text
        if 'performanceoptimizer' in log_text.lower():
            html += (
                f"<li style='color:{colors['success']};'>"
                f"Performance Optimizer detected — "
                f"good for large modlists.</li>")
        if ('vr.missilegirl' in log_text.lower()
                or 'rocketman' in log_text.lower()):
            html += (
                f"<li style='color:{colors['success']};'>"
                f"RocketMan/MissileGirl detected — "
                f"helps with runtime performance.</li>")
        if ('FasterGameLoading' in log_text
                or 'GAGARIN' in log_text):
            html += (
                f"<li style='color:{colors['success']};'>"
                f"Faster Game Loading detected — "
                f"XML caching active.</li>")

        html += "</ul>"
        return html

    def _on_issue_selected(self, item):
        """Show detail for the selected issue."""
        issue = item.data(Qt.ItemDataRole.UserRole)
        if issue:
            colors  = _c()
            related = (
                f"<p><b>Related mod:</b> "
                f"{issue.related_mod}</p>"
                if issue.related_mod else '')
            self.issue_detail.setHtml(
                f"<h3 style='color:{colors['accent']}'>"
                f"{issue.title}</h3>"
                f"<p><b>Severity:</b> "
                f"{issue.severity.upper()}</p>"
                f"<p><b>Occurrences:</b> "
                f"{issue.count}</p>"
                f"<p><b>Description:</b> "
                f"{issue.description}</p>"
                f"<p style='color:{colors['success']}'>"
                f"<b>Suggestion:</b> "
                f"{issue.suggestion}</p>"
                f"{related}")

    def _generate_summary(self, issues: list[LogIssue]):
        """Generate and display the log summary HTML."""
        errors   = self.log_parser.get_error_count()
        warnings = self.log_parser.get_warning_count()
        total    = len(self.log_parser.entries)

        colors = _c()
        html = (
            f"<h2 style='color: {colors['accent']}'>"
            f"Log Analysis Summary</h2>"
            f"<p>Total log lines: <b>{total}</b></p>"
            f"<p style='color: {colors['error']}'>"
            f"Errors: <b>{errors}</b></p>"
            f"<p style='color: {colors['warning']}'>"
            f"Warnings: <b>{warnings}</b></p>"
            f"<hr><h3>Detected Issues ({len(issues)})"
            f"</h3>")

        if issues:
            for issue in issues:
                icon = {
                    'error': '🔴', 'warning': '🟡',
                    'info': 'ℹ️',
                }.get(issue.severity, '')
                html += (
                    f"<p>{icon} <b>{issue.title}</b> "
                    f"(×{issue.count}) — "
                    f"{issue.suggestion}</p>")
        else:
            html += (
                f"<p style='color: {colors['success']}'>"
                f"No known issues detected.</p>")

        html += (
            "<hr><h3>General Tips</h3><ul>"
            "<li>Errors during startup are usually "
            "mod-related</li>"
            "<li>NullReferenceException often means "
            "mod conflicts or missing dependencies</li>"
            "<li>Check load order if you see "
            "\"patch operation failed\" errors</li>"
            "<li>Cross-reference errors mean a mod is "
            "referencing defs from another mod that's "
            "not loaded</li>"
            "<li>Harmless errors (like RocketMan "
            "leftovers) can be safely ignored</li>"
            "</ul>")

        if self.instance:
            html += (
                f"<hr><h3>Instance Info</h3>"
                f"<p>Instance: "
                f"<b>{self.instance.name}</b></p>"
                f"<p>Active mods: "
                f"<b>{self.instance.mod_count}</b></p>"
                f"<p>Save files: "
                f"<b>{self.instance.save_count}</b></p>")

        self.summary_text.setHtml(html)

    def _export_summary(self):
        """Export the summary to a file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Summary", "log_summary.html",
            "HTML Files (*.html);;Text Files (*.txt)")
        if path:
            if path.endswith('.html'):
                with open(path, 'w',
                          encoding='utf-8') as f:
                    f.write(self.summary_text.toHtml())
            else:
                with open(path, 'w',
                          encoding='utf-8') as f:
                    f.write(
                        self.summary_text.toPlainText())
