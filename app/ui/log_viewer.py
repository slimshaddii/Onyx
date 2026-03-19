from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QGroupBox, QListWidget, QListWidgetItem,
    QTabWidget, QWidget, QFileDialog, QComboBox, QSplitter
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCharFormat, QColor, QFont

from app.core.log_parser import LogParser, LogIssue, StartupAnalysis
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
        self.log_path_label.setObjectName("statLabel")
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
        self.log_view.setFont(QFont("Consolas", 12))
        self.log_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        log_layout.addWidget(self.log_view)

        # Stats bar
        self.stats_label = QLabel("")
        self.stats_label.setObjectName("subheading")
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

        startup_tab = QWidget()
        startup_layout = QVBoxLayout(startup_tab)

        self.startup_text = QTextEdit()
        self.startup_text.setReadOnly(True)
        startup_layout.addWidget(self.startup_text)

        tabs.addTab(startup_tab, "⚡ Startup Analysis")

        layout.addWidget(tabs)

        # Close
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _auto_load_log(self):
        instance_path = self.instance.path if self.instance else None
        log_path      = self.log_parser.find_player_log(instance_path)
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
                    "No log file found. Launch the game first.")

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

        from app.core.app_settings import AppSettings
        from app.ui.styles import get_colors
        c = get_colors(AppSettings.instance().theme)

        error_fmt = QTextCharFormat()
        error_fmt.setForeground(QColor(c['error']))
        error_fmt.setFontWeight(QFont.Weight.Bold)
        warn_fmt = QTextCharFormat()
        warn_fmt.setForeground(QColor(c['warning']))
        info_fmt = QTextCharFormat()
        info_fmt.setForeground(QColor(c['text']))

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

                from app.core.app_settings import AppSettings
                from app.ui.styles import get_colors
                _c = get_colors(AppSettings.instance().theme)
                color = {
                    'error':   QColor(_c['error']),
                    'warning': QColor(_c['warning']),
                    'info':    QColor(_c['accent']),
                }.get(issue.severity, QColor(_c['text']))
                item.setForeground(color)
                self.issues_list.addItem(item)

        # Generate summary and startup analysis
        self._generate_summary(issues)
        self._generate_startup_analysis()


    def _generate_startup_analysis(self):
        """Parse and display startup timing and memory analysis."""
        from app.core.app_settings import AppSettings
        from app.ui.styles import get_colors
        _c = get_colors(AppSettings.instance().theme)

        analysis = self.log_parser.parse_startup_analysis()

        if not analysis.phases and not analysis.memory_stats:
            no_data_color = _c['text_dim']
            self.startup_text.setHtml(
                f"<p style='color:{no_data_color};'>"
                f"No startup data found. Launch the game and reload the log.</p>")
            return

        html = f"<h2 style='color:{_c['accent']};'>Startup Analysis</h2>"

        # Game info
        if analysis.game_version:
            html += (f"<p>RimWorld <b>{analysis.game_version}</b></p>")

        if analysis.total_startup_s > 0:
            html += (f"<p>Estimated total startup: "
                     f"<b style='color:{_c['warning']};'>"
                     f"{analysis.total_startup_s:.1f}s</b></p>")

        # Startup phases
        if analysis.phases:
            html += f"<hr><h3 style='color:{_c['accent']};'>Startup Phases</h3>"
            html += "<table width='100%' cellspacing='4'>"
            html += (f"<tr>"
                     f"<th align='left' style='color:{_c['text_dim']};'>Phase</th>"
                     f"<th align='right' style='color:{_c['text_dim']};'>Duration</th>"
                     f"<th align='left' style='color:{_c['text_dim']};'>Impact</th>"
                     f"</tr>")

            # Sort by duration descending
            sorted_phases = sorted(
                analysis.phases, key=lambda p: p.seconds, reverse=True)

            max_sec = max(p.seconds for p in sorted_phases) if sorted_phases else 1

            for phase in sorted_phases:
                pct = phase.seconds / max_sec if max_sec > 0 else 0

                if pct >= 0.7:
                    color = _c['error']
                    impact = 'High'
                elif pct >= 0.3:
                    color = _c['warning']
                    impact = 'Medium'
                else:
                    color = _c['success']
                    impact = 'Low'

                bar_len = int(pct * 20)
                bar = '█' * bar_len + '░' * (20 - bar_len)

                html += (
                    f"<tr>"
                    f"<td style='color:{_c['text']};'>{phase.name}</td>"
                    f"<td align='right' style='color:{color};'>"
                    f"<b>{phase.display}</b></td>"
                    f"<td style='color:{color}; font-family:monospace;'>"
                    f" {bar} {impact}</td>"
                    f"</tr>")

            html += "</table>"

            # Assembly time callout
            if analysis.assembly_time_s > 3.0:
                html += (
                    f"<p style='color:{_c['warning']};'>"
                    f"Assembly loading took {analysis.assembly_time_s:.2f}s. "
                    f"More C# mods = longer load time.</p>")

        # Memory stats
        if analysis.memory_stats:
            html += f"<hr><h3 style='color:{_c['accent']};'>Peak Memory Usage</h3>"
            html += "<table width='100%' cellspacing='4'>"

            total_mb = sum(s.peak_mb for s in analysis.memory_stats)

            for stat in sorted(
                    analysis.memory_stats, key=lambda s: s.peak_mb, reverse=True):
                if stat.peak_mb >= 512:
                    color = _c['error']
                elif stat.peak_mb >= 256:
                    color = _c['warning']
                else:
                    color = _c['text']

                if stat.peak_mb >= 1024:
                    display = f"{stat.peak_mb / 1024:.2f} GB"
                else:
                    display = f"{stat.peak_mb:.0f} MB"

                html += (
                    f"<tr>"
                    f"<td style='color:{_c['text']};'>{stat.name}</td>"
                    f"<td align='right' style='color:{color};'>"
                    f"<b>{display}</b></td>"
                    f"</tr>")

            html += "</table>"

            if total_mb >= 3072:
                html += (
                    f"<p style='color:{_c['error']};'>"
                    f"Total peak memory exceeds 3 GB. "
                    f"Consider reducing mod count if experiencing crashes.</p>")
            elif total_mb >= 2048:
                html += (
                    f"<p style='color:{_c['warning']};'>"
                    f"Total peak memory is high ({total_mb/1024:.1f} GB). "
                    f"Monitor for out-of-memory issues.</p>")

        # C# mod info
        html += (
            f"<hr><h3 style='color:{_c['accent']};'>Assembly Info</h3>"
            f"<p>Assemblies loaded: <b>{analysis.csharp_mod_count}</b></p>"
            f"<p style='color:{_c['text_dim']};'>"
            f"Each C# mod adds to startup time. "
            f"XML-only mods load much faster.</p>")

        # Tips based on data
        html += f"<hr><h3 style='color:{_c['accent']};'>Tips</h3><ul>"
        if analysis.assembly_time_s > 5.0:
            html += (f"<li style='color:{_c['warning']};'>"
                     f"Assembly load time is high ({analysis.assembly_time_s:.1f}s). "
                     f"Harmony and Prepatcher reduce this for subsequent launches.</li>")

        # Check for known performance mods in log
        log_text = self.log_parser.raw_text
        if 'performanceoptimizer' in log_text.lower():
            html += (f"<li style='color:{_c['success']};'>"
                     f"Performance Optimizer detected — good for large modlists.</li>")
        if 'vr.missilegirl' in log_text.lower() or 'rocketman' in log_text.lower():
            html += (f"<li style='color:{_c['success']};'>"
                     f"RocketMan/MissileGirl detected — helps with runtime performance.</li>")
        if 'FasterGameLoading' in log_text or 'GAGARIN' in log_text:
            html += (f"<li style='color:{_c['success']};'>"
                     f"Faster Game Loading detected — XML caching active.</li>")

        html += "</ul>"

        self.startup_text.setHtml(html)

    def _on_issue_selected(self, item):
        issue = item.data(Qt.ItemDataRole.UserRole)
        if issue:
            from app.core.app_settings import AppSettings
            from app.ui.styles import get_colors
            _c = get_colors(AppSettings.instance().theme)
            accent  = _c['accent']
            success = _c['success']
            related = (f"<p><b>Related mod:</b> {issue.related_mod}</p>"
                       if issue.related_mod else '')
            self.issue_detail.setHtml(
                f"<h3 style='color:{accent}'>{issue.title}</h3>"
                f"<p><b>Severity:</b> {issue.severity.upper()}</p>"
                f"<p><b>Occurrences:</b> {issue.count}</p>"
                f"<p><b>Description:</b> {issue.description}</p>"
                f"<p style='color:{success}'><b>Suggestion:</b> {issue.suggestion}</p>"
                f"{related}"
            )

    def _generate_summary(self, issues: list[LogIssue]):
        errors = self.log_parser.get_error_count()
        warnings = self.log_parser.get_warning_count()
        total = len(self.log_parser.entries)

        from app.core.app_settings import AppSettings
        from app.ui.styles import get_colors
        _c = get_colors(AppSettings.instance().theme)
        html = f"""
        <h2 style='color: {_c['accent']}'>Log Analysis Summary</h2>
        <p>Total log lines: <b>{total}</b></p>
        <p style='color: {_c['error']}'>Errors: <b>{errors}</b></p>
        <p style='color: {_c['warning']}'>Warnings: <b>{warnings}</b></p>
        <hr>
        <h3>Detected Issues ({len(issues)})</h3>
        """

        if issues:
            for issue in issues:
                icon = {'error': '🔴', 'warning': '🟡', 'info': 'ℹ️'}.get(issue.severity, '')
                html += f"<p>{icon} <b>{issue.title}</b> (×{issue.count}) — {issue.suggestion}</p>"
        else:
            html += f"<p style='color: {_c['success']}'>No known issues detected.</p>"

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