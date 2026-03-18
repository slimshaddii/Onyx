import os
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class LogEntry:
    level: str  # 'INFO', 'WARNING', 'ERROR', 'EXCEPTION'
    message: str
    line_number: int
    timestamp: str = ''
    source: str = ''


@dataclass
class LogIssue:
    severity: str  # 'error', 'warning', 'info'
    title: str
    description: str
    suggestion: str
    count: int = 1
    related_mod: str = ''


KNOWN_ISSUES = [
    {
        'pattern': r'Could not resolve cross-reference',
        'title': 'Cross-reference Error',
        'description': 'A mod is referencing a def that does not exist.',
        'suggestion': 'Check if a required mod is missing or if load order is wrong.',
        'severity': 'error',
    },
    {
        'pattern': r'MissingMethodException',
        'title': 'Missing Method Exception',
        'description': 'A mod is calling a method that does not exist in this game version.',
        'suggestion': 'The mod may be outdated. Check for an updated version.',
        'severity': 'error',
    },
    {
        'pattern': r'NullReferenceException',
        'title': 'Null Reference Exception',
        'description': 'A mod or the game accessed a null object.',
        'suggestion': 'Often caused by mod conflicts or missing dependencies.',
        'severity': 'error',
    },
    {
        'pattern': r'TypeLoadException',
        'title': 'Type Load Exception',
        'description': 'Failed to load a type from a mod assembly.',
        'suggestion': 'The mod may require a dependency like Harmony or HugsLib.',
        'severity': 'error',
    },
    {
        'pattern': r'XML error.*About\.xml',
        'title': 'Mod XML Error',
        'description': 'A mod has malformed About.xml.',
        'suggestion': 'The mod may be corrupted. Try redownloading.',
        'severity': 'warning',
    },
    {
        'pattern': r'sourcePrecept.*null',
        'title': 'Source Precept Null (Harmless)',
        'description': 'FloodLight or similar mod generating precept errors.',
        'suggestion': 'Generally harmless log noise. Can be ignored.',
        'severity': 'info',
    },
    {
        'pattern': r'RocketMan',
        'title': 'RocketMan Leftover Data',
        'description': 'RocketMan mod data found in save but mod not loaded.',
        'suggestion': 'Harmless log noise from a previously used mod.',
        'severity': 'info',
    },
    {
        'pattern': r'Could not find.*Def named',
        'title': 'Missing Def',
        'description': 'Game cannot find a definition referenced by a mod.',
        'suggestion': 'A mod might be missing or load order may be incorrect.',
        'severity': 'warning',
    },
    {
        'pattern': r'Shader.*not found',
        'title': 'Missing Shader',
        'description': 'A shader file could not be loaded.',
        'suggestion': 'Often harmless, but can indicate a graphics mod issue.',
        'severity': 'warning',
    },
    {
        'pattern': r'patch operation.*failed',
        'title': 'Patch Operation Failed',
        'description': 'An XML patch from a mod could not be applied.',
        'suggestion': 'Check load order. The target mod may need to load first.',
        'severity': 'warning',
    },
]


class LogParser:
    def __init__(self):
        self.entries: list[LogEntry] = []
        self.raw_text: str = ''

    def parse_file(self, log_path: Path) -> bool:
        if not log_path.exists():
            return False
        try:
            self.raw_text = log_path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            return False

        self.entries.clear()
        for i, line in enumerate(self.raw_text.splitlines(), 1):
            ll = line.lower()
            if any(x in ll for x in ('exception:', ': error', '[error]', 'error:')):
                level = 'ERROR'
            elif 'exception' in ll and not 'no exception' in ll:
                level = 'ERROR'
            elif 'warn' in ll:
                level = 'WARNING'
            else:
                level = 'INFO'
            self.entries.append(LogEntry(
                level=level,
                message=line,
                line_number=i,
            ))
        return True

    def find_player_log(self, instance_path: Optional[Path] = None) -> Optional[Path]:
        """
        Find Player.log — instance log takes strict priority.
        AppData is only checked when no instance path is given
        or the instance has no log yet.
        """
        import platform

        # Instance log — always prefer this if it exists
        if instance_path:
            inst_log = instance_path / 'Player.log'
            if inst_log.exists():
                return inst_log

        # No instance log — fall back to system default
        system = platform.system()
        if system == 'Windows':
            local_low = Path(os.environ.get(
                'LOCALAPPDATA',
                str(Path.home() / 'AppData' / 'Local')))
            local_low  = local_low.parent / 'LocalLow'
            rw_log_dir = (local_low / 'Ludeon Studios' /
                          'RimWorld by Ludeon Studios')
        elif system == 'Darwin':
            rw_log_dir = (Path.home() / 'Library' / 'Logs' /
                          'Ludeon Studios' / 'RimWorld by Ludeon Studios')
        else:
            rw_log_dir = (Path.home() / '.config' / 'unity3d' /
                          'Ludeon Studios' / 'RimWorld by Ludeon Studios')

        for log_name in ('Player.log', 'Player-prev.log'):
            p = rw_log_dir / log_name
            if p.exists():
                return p

        return None

    def analyze(self) -> list[LogIssue]:
        issues = []
        issue_counts = {}

        for entry in self.entries:
            for known in KNOWN_ISSUES:
                if re.search(known['pattern'], entry.message, re.IGNORECASE):
                    key = known['title']
                    if key in issue_counts:
                        issue_counts[key].count += 1
                    else:
                        issue = LogIssue(
                            severity=known['severity'],
                            title=known['title'],
                            description=known['description'],
                            suggestion=known['suggestion'],
                        )
                        issue_counts[key] = issue
                        issues.append(issue)

        return sorted(issues, key=lambda x: {'error': 0, 'warning': 1, 'info': 2}[x.severity])

    def get_error_count(self) -> int:
        return sum(1 for e in self.entries if e.level == 'ERROR')

    def get_warning_count(self) -> int:
        return sum(1 for e in self.entries if e.level == 'WARNING')

    def search(self, query: str, case_sensitive: bool = False) -> list[LogEntry]:
        if not case_sensitive:
            query = query.lower()
            return [e for e in self.entries if query in e.message.lower()]
        return [e for e in self.entries if query in e.message]