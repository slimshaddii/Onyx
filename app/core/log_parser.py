"""
RimWorld Player.log parser — log entry classification, issue detection,
and startup performance analysis.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import re
from typing import Optional


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class LogEntry:
    """A single classified line from Player.log."""

    level:       str  # 'INFO', 'WARNING', 'ERROR'
    message:     str
    line_number: int
    timestamp:   str = ''
    source:      str = ''


@dataclass
class LogIssue:
    """An aggregated issue found by pattern-matching log entries."""

    severity:    str  # 'error', 'warning', 'info'
    title:       str
    description: str
    suggestion:  str
    count:       int = 1
    related_mod: str = ''


@dataclass
class StartupPhase:
    """A single measured phase of the RimWorld startup sequence."""

    name:     str
    duration: float
    unit:     str   # 's' or 'ms'

    @property
    def seconds(self) -> float:
        """Return duration converted to seconds."""
        if self.unit == 'ms':
            return self.duration / 1000
        return self.duration

    @property
    def display(self) -> str:
        """Return a human-readable duration string."""
        if self.seconds >= 1.0:
            return f"{self.seconds:.2f}s"
        return f"{self.seconds * 1000:.0f}ms"


@dataclass
class MemoryStat:
    """Peak memory recorded for one Unity allocator."""

    name:     str
    peak_mb:  float
    category: str


@dataclass
class StartupAnalysis:
    """Aggregated startup performance data extracted from Player.log."""

    phases:           list[StartupPhase]
    memory_stats:     list[MemoryStat]
    total_startup_s:  float
    assembly_time_s:  float
    csharp_mod_count: int
    game_version:     str
    mod_count:        int


# ── Known issue patterns — compiled once at module load ───────────────────────

_RAW_KNOWN_ISSUES = [
    {
        'pattern':     r'Could not resolve cross-reference',
        'title':       'Cross-reference Error',
        'description': ('A mod is referencing a def that '
                        'does not exist.'),
        'suggestion':  ('Check if a required mod is missing '
                        'or if load order is wrong.'),
        'severity':    'error',
    },
    {
        'pattern':     r'MissingMethodException',
        'title':       'Missing Method Exception',
        'description': ('A mod is calling a method that does '
                        'not exist in this game version.'),
        'suggestion':  ('The mod may be outdated. '
                        'Check for an updated version.'),
        'severity':    'error',
    },
    {
        'pattern':     r'NullReferenceException',
        'title':       'Null Reference Exception',
        'description': ('A mod or the game accessed '
                        'a null object.'),
        'suggestion':  ('Often caused by mod conflicts '
                        'or missing dependencies.'),
        'severity':    'error',
    },
    {
        'pattern':     r'TypeLoadException',
        'title':       'Type Load Exception',
        'description': ('Failed to load a type from '
                        'a mod assembly.'),
        'suggestion':  ('The mod may require a dependency '
                        'like Harmony or HugsLib.'),
        'severity':    'error',
    },
    {
        'pattern':     r'XML error.*About\.xml',
        'title':       'Mod XML Error',
        'description': 'A mod has malformed About.xml.',
        'suggestion':  ('The mod may be corrupted. '
                        'Try redownloading.'),
        'severity':    'warning',
    },
    {
        'pattern':     r'sourcePrecept.*null',
        'title':       'Source Precept Null (Harmless)',
        'description': ('FloodLight or similar mod generating '
                        'precept errors.'),
        'suggestion':  ('Generally harmless log noise. '
                        'Can be ignored.'),
        'severity':    'info',
    },
    {
        'pattern':     r'RocketMan',
        'title':       'RocketMan Leftover Data',
        'description': ('RocketMan mod data found in save '
                        'but mod not loaded.'),
        'suggestion':  ('Harmless log noise from a '
                        'previously used mod.'),
        'severity':    'info',
    },
    {
        'pattern':     r'Could not find.*Def named',
        'title':       'Missing Def',
        'description': ('Game cannot find a definition '
                        'referenced by a mod.'),
        'suggestion':  ('A mod might be missing or load '
                        'order may be incorrect.'),
        'severity':    'warning',
    },
    {
        'pattern':     r'Shader.*not found',
        'title':       'Missing Shader',
        'description': 'A shader file could not be loaded.',
        'suggestion':  ('Often harmless, but can indicate '
                        'a graphics mod issue.'),
        'severity':    'warning',
    },
    {
        'pattern':     r'patch operation.*failed',
        'title':       'Patch Operation Failed',
        'description': ('An XML patch from a mod could '
                        'not be applied.'),
        'suggestion':  ('Check load order. The target mod '
                        'may need to load first.'),
        'severity':    'warning',
    },
]

# Pre-compile patterns with IGNORECASE — avoids recompilation
# on every analyze() call and every log entry.
# Each tuple: (compiled_re, title, description, suggestion, severity).
KNOWN_ISSUES = _RAW_KNOWN_ISSUES  # kept for callers that read raw

_COMPILED_ISSUES: list[tuple[
        re.Pattern, str, str, str, str]] = [
    (
        re.compile(ki['pattern'], re.IGNORECASE),
        ki['title'],
        ki['description'],
        ki['suggestion'],
        ki['severity'],
    )
    for ki in _RAW_KNOWN_ISSUES
]

_SEVERITY_ORDER = {'error': 0, 'warning': 1, 'info': 2}

# ── Startup analysis constants ───────────────────────────────────────────────

_PHASE_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(
        r'LoadModXML_Profiler.*?(\d+\.?\d*)\s*seconds?',
        re.IGNORECASE), 'Load Mod XML', 's'),
    (re.compile(
        r'CombineIntoUnifiedXML_Profiler'
        r'.*?(\d+\.?\d*)\s*seconds?',
        re.IGNORECASE), 'Combine XML', 's'),
    (re.compile(
        r'ApplyPatches_Profiler.*?(\d+\.?\d*)\s*seconds?',
        re.IGNORECASE), 'Apply Patches', 's'),
    (re.compile(
        r'ParseAndProcessXML_Profiler'
        r'.*?(\d+\.?\d*)\s*seconds?',
        re.IGNORECASE), 'Parse XML', 's'),
    (re.compile(
        r'XmlInheritance\.Resolve.*?(\d+\.?\d*)\s*seconds?',
        re.IGNORECASE), 'XML Inheritance', 's'),
    (re.compile(
        r'TKeySystem\.Parse.*?(\d+\.?\d*)\s*seconds?',
        re.IGNORECASE), 'Translation Keys', 's'),
    (re.compile(
        r'vanilla load took\s+(\d+\.?\d*)s?',
        re.IGNORECASE), 'Vanilla Load (Prepatcher)', 's'),
    (re.compile(
        r'Game processing took\s+(\d+\.?\d*)ms',
        re.IGNORECASE), 'Game Processing', 'ms'),
    (re.compile(
        r'Serializing took\s+(\d+\.?\d*)ms',
        re.IGNORECASE), 'Assembly Serialization', 'ms'),
    (re.compile(
        r'Loaded All Assemblies, in\s+(\d+\.?\d*)'
        r'\s*seconds?',
        re.IGNORECASE), 'Load All Assemblies', 's'),
]

_MEMORY_MARKERS: list[tuple[str, str, str]] = [
    ('[ALLOC_DEFAULT_MAIN]',   'Game Memory',     'main'),
    ('[ALLOC_GFX_MAIN]',       'Graphics Memory', 'gfx'),
    ('[ALLOC_DEFAULT_THREAD]', 'Thread Memory',   'thread'),
]

_PEAK_PATTERN = re.compile(
    r'Peak Allocated memory\s+([\d.]+)\s*(B|KB|MB|GB)')
_VERSION_PATTERN = re.compile(
    r'RimWorld\s+(\d+\.\d+\.\d+)')
_ASSEMBLY_VERSION_PATTERN = re.compile(
    r', Version=\d+\.\d+\.\d+\.\d+')

# Format may vary across RimWorld versions
_MOD_COUNT_PATTERN = re.compile(
    r'Loading\s+(\d+)\s+active\s+mods?', re.IGNORECASE)

_TOTAL_STARTUP_PHASES = frozenset({
    'Vanilla Load (Prepatcher)',
    'Load All Assemblies',
    'Load Mod XML',
    'Combine XML',
    'Parse XML',
})

_MB_FACTORS: dict[str, float] = {
    'B':  1 / 1024 / 1024,
    'KB': 1 / 1024,
    'MB': 1.0,
    'GB': 1024.0,
}


# ── LogParser ─────────────────────────────────────────────────────────────────

class LogParser:
    """
    Parses RimWorld Player.log files into structured log entries
    and provides analysis helpers.
    """

    def __init__(self):
        self.entries:  list[LogEntry] = []
        self.raw_text: str            = ''

    def parse_file(self, log_path: Path) -> bool:
        """
        Read and classify all lines in log_path.

        Returns True on success, False if the file is missing
        or unreadable. Populates self.entries and self.raw_text.
        """
        if not log_path.exists():
            return False
        try:
            self.raw_text = log_path.read_text(
                encoding='utf-8', errors='replace')
        except OSError:
            return False

        self.entries.clear()
        for i, line in enumerate(self.raw_text.splitlines(), 1):
            self.entries.append(LogEntry(
                level=_classify_line(line),
                message=line,
                line_number=i,
            ))
        return True

    def find_player_log(
            self,
            instance_path: Optional[Path] = None,
    ) -> Optional[Path]:
        """
        Find Player.log — instance log takes strict priority.

        AppData / system log directories are only searched when
        no instance path is given, or when the instance has no
        log yet.
        """
        if instance_path:
            inst_log = instance_path / 'Player.log'
            if inst_log.exists():
                return inst_log

        rw_log_dir = _rw_log_directory()
        for log_name in ('Player.log', 'Player-prev.log'):
            p = rw_log_dir / log_name
            if p.exists():
                return p
        return None

    def analyze(self) -> list[LogIssue]:
        """
        Scan all log entries against known issue patterns.

        Returns a list of LogIssue, deduplicated and sorted by
        severity (error > warning > info). Repeated occurrences
        increment issue.count.
        """
        issue_counts: dict[str, LogIssue] = {}
        issues:       list[LogIssue]      = []

        for entry in self.entries:
            for (pattern, title, description,
                 suggestion, severity) in _COMPILED_ISSUES:
                if pattern.search(entry.message):
                    if title in issue_counts:
                        issue_counts[title].count += 1
                    else:
                        issue = LogIssue(
                            severity=severity,
                            title=title,
                            description=description,
                            suggestion=suggestion,
                        )
                        issue_counts[title] = issue
                        issues.append(issue)

        return sorted(
            issues,
            key=lambda x: _SEVERITY_ORDER[x.severity])

    def get_error_count(self) -> int:
        """Return the number of entries classified as ERROR."""
        return sum(
            1 for e in self.entries if e.level == 'ERROR')

    def get_warning_count(self) -> int:
        """Return the number of entries classified as WARNING."""
        return sum(
            1 for e in self.entries if e.level == 'WARNING')

    def search(self, query: str,
               case_sensitive: bool = False) -> list[LogEntry]:
        """Return all entries whose message contains query."""
        if not case_sensitive:
            q = query.lower()
            return [
                e for e in self.entries
                if q in e.message.lower()
            ]
        return [
            e for e in self.entries
            if query in e.message
        ]

    def parse_startup_analysis(self) -> 'StartupAnalysis':
        """
        Extract startup timing, memory stats, and assembly info.
        Works with RimWorld 1.6 log format.
        """
        phases:       list[StartupPhase] = []
        memory_stats: list[MemoryStat]   = []
        assembly_time = 0.0
        game_version  = ''
        mod_count     = 0

        current_alloc_section: Optional[
            tuple[str, str]] = None
        alloc_data: dict[str, float] = {}

        for entry in self.entries:
            line = entry.message

            if not game_version:
                game_version = _extract_game_version(line)

            if not mod_count:
                mc = _MOD_COUNT_PATTERN.search(line)
                if mc:
                    mod_count = int(mc.group(1))

            phase = _extract_phase(line)
            if phase:
                phases.append(phase)
                if phase.name == 'Load All Assemblies':
                    assembly_time = phase.seconds

            for marker, stat_name, category in \
                    _MEMORY_MARKERS:
                if marker in line:
                    current_alloc_section = (
                        stat_name, category)
                    break

            if (current_alloc_section
                    and 'Peak Allocated memory' in line):
                mb = _extract_memory_peak_mb(line)
                if mb is not None:
                    stat_name, category = (
                        current_alloc_section)
                    if stat_name not in alloc_data:
                        alloc_data[stat_name] = mb
                        memory_stats.append(
                            MemoryStat(
                                stat_name, mb, category))
                    current_alloc_section = None

            # Duplicate assembly_time extraction retained
            # from original to preserve identical behavior
            # in edge cases.
            if 'Loaded All Assemblies' in line:
                m = re.search(
                    r'Loaded All Assemblies, in\s+'
                    r'([\d.]+)\s*seconds?',
                    line, re.IGNORECASE)
                if m:
                    assembly_time = float(m.group(1))

        unique_phases = _deduplicate_phases(phases)
        total_startup = _compute_total_startup(unique_phases)
        csharp_mods   = _count_csharp_mods(self.entries)

        return StartupAnalysis(
            phases=unique_phases,
            memory_stats=memory_stats,
            total_startup_s=total_startup,
            assembly_time_s=assembly_time,
            csharp_mod_count=csharp_mods,
            game_version=game_version,
            mod_count=mod_count,
        )


# ── Module-level helpers ──────────────────────────────────────────────────────

def _classify_line(line: str) -> str:
    """
    Return 'ERROR', 'WARNING', or 'INFO' for a single log line.

    Matches the original classification logic exactly.
    """
    ll = line.lower()
    if any(x in ll for x in (
            'exception:', ': error', '[error]', 'error:')):
        return 'ERROR'
    if 'exception' in ll and 'no exception' not in ll:
        return 'ERROR'
    if 'warn' in ll:
        return 'WARNING'
    return 'INFO'


def _rw_log_directory() -> Path:
    """Return the platform-specific RimWorld log directory."""
    system = platform.system()
    if system == 'Windows':
        local_low = Path(os.environ.get(
            'LOCALAPPDATA',
            str(Path.home() / 'AppData' / 'Local'))
        ).parent / 'LocalLow'
        return (local_low / 'Ludeon Studios'
                / 'RimWorld by Ludeon Studios')
    if system == 'Darwin':
        return (Path.home() / 'Library' / 'Logs'
                / 'Ludeon Studios'
                / 'RimWorld by Ludeon Studios')
    return (Path.home() / '.config' / 'unity3d'
            / 'Ludeon Studios'
            / 'RimWorld by Ludeon Studios')


def _extract_game_version(line: str) -> str:
    """Return the game version found in line, or ''."""
    m = _VERSION_PATTERN.search(line)
    return m.group(1) if m else ''


def _extract_phase(line: str) -> Optional[StartupPhase]:
    """
    Try all phase patterns against line.

    Returns the first matching StartupPhase, or None.
    """
    for pattern, name, unit in _PHASE_PATTERNS:
        m = pattern.search(line)
        if m:
            return StartupPhase(
                name, float(m.group(1)), unit)
    return None


def _extract_memory_peak_mb(
        line: str) -> Optional[float]:
    """
    Parse 'Peak Allocated memory X UNIT' and return MB.

    Returns None if the pattern is not found.
    """
    m = _PEAK_PATTERN.search(line)
    if not m:
        return None
    val  = float(m.group(1))
    unit = m.group(2)
    return val * _MB_FACTORS.get(unit, 1.0)


def _deduplicate_phases(
        phases: list[StartupPhase]) -> list[StartupPhase]:
    """Return phases with duplicates removed, first-occurrence order."""
    seen:   set[str]           = set()
    result: list[StartupPhase] = []
    for p in phases:
        if p.name not in seen:
            seen.add(p.name)
            result.append(p)
    return result


def _compute_total_startup(
        unique_phases: list[StartupPhase]) -> float:
    """Sum seconds of phases contributing to total startup."""
    return sum(
        p.seconds for p in unique_phases
        if p.name in _TOTAL_STARTUP_PHASES)


def _count_csharp_mods(entries: list[LogEntry]) -> int:
    """
    Estimate C# mod count from assembly version lines.

    Counts lines containing a version pattern but not the
    base game Assembly-CSharp. This is a heuristic count.
    """
    return sum(
        1 for e in entries
        if 'Assembly-CSharp' not in e.message
        and _ASSEMBLY_VERSION_PATTERN.search(e.message)
    )
