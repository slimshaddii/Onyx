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

@dataclass
class StartupPhase:
    name:     str
    duration: float
    unit:     str

    @property
    def seconds(self) -> float:
        return self.duration / 1000 if self.unit == 'ms' else self.duration

    @property
    def display(self) -> str:
        if self.seconds >= 1.0:
            return f"{self.seconds:.2f}s"
        return f"{self.seconds * 1000:.0f}ms"


@dataclass
class MemoryStat:
    name:     str
    peak_mb:  float
    category: str


@dataclass
class StartupAnalysis:
    phases:           list[StartupPhase]
    memory_stats:     list[MemoryStat]
    total_startup_s:  float
    assembly_time_s:  float
    csharp_mod_count: int
    game_version:     str
    mod_count:        int

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
    
    def parse_startup_analysis(self) -> 'StartupAnalysis':
        """
        Extract startup timing, memory stats, and assembly info from log.
        Works with RimWorld 1.6 log format.
        """
        import re

        phases:       list[StartupPhase] = []
        memory_stats: list[MemoryStat]   = []
        total_startup = 0.0
        assembly_time = 0.0
        csharp_mods   = 0
        game_version  = ''
        mod_count     = 0

        # Patterns to extract from log lines
        phase_patterns = [
            # GAGARIN/FasterGameLoading profiler lines
            (r'LoadModXML_Profiler.*?(\d+\.?\d*)\s*seconds?',
             'Load Mod XML', 's'),
            (r'CombineIntoUnifiedXML_Profiler.*?(\d+\.?\d*)\s*seconds?',
             'Combine XML', 's'),
            (r'ApplyPatches_Profiler.*?(\d+\.?\d*)\s*seconds?',
             'Apply Patches', 's'),
            (r'ParseAndProcessXML_Profiler.*?(\d+\.?\d*)\s*seconds?',
             'Parse XML', 's'),
            (r'XmlInheritance\.Resolve.*?(\d+\.?\d*)\s*seconds?',
             'XML Inheritance', 's'),
            (r'TKeySystem\.Parse.*?(\d+\.?\d*)\s*seconds?',
             'Translation Keys', 's'),
            # Prepatcher lines
            (r'vanilla load took\s+(\d+\.?\d*)s?',
             'Vanilla Load (Prepatcher)', 's'),
            (r'Game processing took\s+(\d+\.?\d*)ms',
             'Game Processing', 'ms'),
            (r'Serializing took\s+(\d+\.?\d*)ms',
             'Assembly Serialization', 'ms'),
            # Assembly loading
            (r'Loaded All Assemblies, in\s+(\d+\.?\d*)\s*seconds?',
             'Load All Assemblies', 's'),
        ]

        memory_patterns = [
            # ALLOC_DEFAULT_MAIN peak
            (r'\[ALLOC_DEFAULT_MAIN\]', 'Game Memory', 'main'),
            (r'\[ALLOC_GFX_MAIN\]',     'Graphics Memory', 'gfx'),
            (r'\[ALLOC_DEFAULT_THREAD\]', 'Thread Memory', 'thread'),
        ]

        current_alloc_section = None
        alloc_data: dict[str, float] = {}

        for entry in self.entries:
            line = entry.message

            # Game version
            if not game_version:
                m = re.search(r'RimWorld\s+(\d+\.\d+\.\d+)', line)
                if m:
                    game_version = m.group(1)

            # Mod count from loading line
            if not mod_count and 'Loading game from file' in line:
                pass  # mod count comes from subsequent lines

            # Phase timings
            for pattern, name, unit in phase_patterns:
                m = re.search(pattern, line, re.IGNORECASE)
                if m:
                    val = float(m.group(1))
                    phases.append(StartupPhase(name, val, unit))
                    if name == 'Load All Assemblies':
                        assembly_time = val if unit == 's' else val / 1000

            # Memory section tracking
            for section_marker, stat_name, category in memory_patterns:
                if section_marker in line:
                    current_alloc_section = (stat_name, category)
                    break

            # Peak memory within a section
            if current_alloc_section and 'Peak Allocated memory' in line:
                m = re.search(
                    r'Peak Allocated memory\s+([\d.]+)\s*(B|KB|MB|GB)',
                    line)
                if m:
                    val  = float(m.group(1))
                    unit = m.group(2)
                    mb   = {'B': val/1024/1024, 'KB': val/1024,
                            'MB': val, 'GB': val*1024}.get(unit, val)
                    stat_name, category = current_alloc_section
                    # Only record the first (highest) peak per section
                    if stat_name not in alloc_data:
                        alloc_data[stat_name] = mb
                        memory_stats.append(
                            MemoryStat(stat_name, mb, category))
                    current_alloc_section = None

            # C# mod assemblies (count unique mod sources in patch list)
            if 'Loaded All Assemblies' in line:
                m = re.search(
                    r'Loaded All Assemblies, in\s+([\d.]+)\s*seconds?',
                    line, re.IGNORECASE)
                if m:
                    assembly_time = float(m.group(1))

        # Deduplicate phases (same name can appear multiple times)
        seen_phases: set[str] = set()
        unique_phases: list[StartupPhase] = []
        for p in phases:
            if p.name not in seen_phases:
                seen_phases.add(p.name)
                unique_phases.append(p)

        # Total startup = sum of major phases
        total_startup = sum(
            p.seconds for p in unique_phases
            if p.name in ('Vanilla Load (Prepatcher)',
                          'Load All Assemblies',
                          'Load Mod XML',
                          'Combine XML',
                          'Parse XML'))

        # Count C# mods from assembly loading line count heuristic
        # Each mod with assemblies contributes to load time
        assembly_lines = [
            e.message for e in self.entries
            if 'Assembly-CSharp' not in e.message
            and re.search(r', Version=\d+\.\d+\.\d+\.\d+', e.message)
        ]
        csharp_mods = len(assembly_lines)

        return StartupAnalysis(
            phases=unique_phases,
            memory_stats=memory_stats,
            total_startup_s=total_startup,
            assembly_time_s=assembly_time,
            csharp_mod_count=csharp_mods,
            game_version=game_version,
            mod_count=mod_count,
        )
