"""
Log Parser Node for LangGraph.

Parses log files and extracts error entries for analysis.
The agent receives pre-filtered relevant logs, so this parser
focuses on structuring the input rather than filtering.
"""

import re
from pathlib import Path
from typing import Any

from ..models.log_entry import LogEntry


# Regex pattern for parsing log lines
# Format: Time \t Level \t FileName \t LineNumber \t FunctionName \t ThreadID Message
LOG_PATTERN = re.compile(
    r'^(\d{2}:\d{2}:\d{2}\.\d{3})\s+'      # Timestamp: HH:MM:SS.mmm
    r'(\w+)\s+'                              # Level: INFO, ERROR, etc.
    r'(\S+)\s+'                              # Source file
    r'(\d{4})\s+'                            # Line number (4 digits)
    r'(\S+)\s+'                              # Function name
    r'(\d+)\s*'                              # Thread ID
    r'(.*)$'                                 # Message (rest of line)
)


def parse_log_line(line: str) -> LogEntry | None:
    """
    Parse a single log line into a LogEntry object.
    
    Args:
        line: Raw log line string
    
    Returns:
        LogEntry if parsing succeeded, None otherwise
    """
    line = line.strip()
    if not line:
        return None
    
    match = LOG_PATTERN.match(line)
    if not match:
        return None
    
    try:
        return LogEntry(
            timestamp=match.group(1),
            level=match.group(2).upper(),
            source_file=match.group(3),
            line_number=int(match.group(4)),
            function_name=match.group(5),
            thread_id=match.group(6),
            message=match.group(7).strip(),
            raw_line=line
        )
    except (ValueError, IndexError):
        return None


def parse_log_content(content: str) -> list[LogEntry]:
    """
    Parse log content (string) into a list of LogEntry objects.
    
    Args:
        content: Raw log file content as string
    
    Returns:
        List of parsed LogEntry objects
    """
    entries = []
    for line in content.split('\n'):
        entry = parse_log_line(line)
        if entry:
            entries.append(entry)
    return entries


def parse_log_file(file_path: str | Path) -> list[LogEntry]:
    """
    Parse a log file and return list of LogEntry objects.
    
    Args:
        file_path: Path to the log file
    
    Returns:
        List of parsed LogEntry objects
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {file_path}")
    
    content = path.read_text(encoding='utf-8', errors='replace')
    return parse_log_content(content)


def extract_errors(entries: list[LogEntry]) -> list[LogEntry]:
    """
    Filter log entries to only include errors.
    
    Args:
        entries: List of all log entries
    
    Returns:
        List of ERROR and CRITICAL level entries
    """
    return [entry for entry in entries if entry.is_error()]


def group_related_entries(
    entries: list[LogEntry],
    target_entry: LogEntry,
    context_lines: int = 5
) -> list[LogEntry]:
    """
    Get related log entries around a target error entry.
    
    Finds entries with the same thread_id and close timestamps
    to provide context for analysis.
    
    Args:
        entries: All log entries
        target_entry: The error entry to find context for
        context_lines: Number of entries before/after to include
    
    Returns:
        List of related entries including the target
    """
    # Find entries with the same thread ID
    same_thread = [e for e in entries if e.thread_id == target_entry.thread_id]
    
    # Find index of target in filtered list
    try:
        target_idx = next(
            i for i, e in enumerate(same_thread)
            if e.raw_line == target_entry.raw_line
        )
    except StopIteration:
        return [target_entry]
    
    # Get surrounding entries
    start = max(0, target_idx - context_lines)
    end = min(len(same_thread), target_idx + context_lines + 1)
    
    return same_thread[start:end]


def group_errors_by_context(
    entries: list[LogEntry],
    errors: list[LogEntry]
) -> list[list[LogEntry]]:
    """
    Group related errors together for holistic analysis.
    
    Groups errors by:
    1. Same source file (likely same bug)
    2. Same thread ID (likely same transaction/flow)
    3. Similar error message patterns
    
    Args:
        entries: All log entries
        errors: Only error entries
    
    Returns:
        List of error groups, each group is a list of related errors
    """
    if not errors:
        return []
    
    # Group by source file + function combination
    groups: dict[str, list[LogEntry]] = {}
    
    for error in errors:
        # Create a key based on source file and error pattern
        # This groups errors that likely have the same root cause
        key = f"{error.source_file}:{error.function_name}"
        
        if key not in groups:
            groups[key] = []
        groups[key].append(error)
    
    return list(groups.values())


def get_full_context_for_group(
    entries: list[LogEntry],
    error_group: list[LogEntry]
) -> list[LogEntry]:
    """
    Get all relevant log entries for analyzing a group of errors.
    
    Includes:
    - All entries from threads that have errors
    - Maintains chronological order
    
    Args:
        entries: All log entries
        error_group: Group of related errors
    
    Returns:
        Full context entries for analysis
    """
    # Get all thread IDs from the error group
    thread_ids = set(e.thread_id for e in error_group)
    
    # Get all entries from those threads
    context_entries = [e for e in entries if e.thread_id in thread_ids]
    
    return context_entries


def parse_logs_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph node for parsing logs.
    
    Expects state to contain:
        - log_content: str - The pre-filtered log content to analyze
        OR
        - log_file_path: str - Path to a log file
    
    Updates state with:
        - log_entries: List[LogEntry] - All parsed entries
        - error_groups: List[List[LogEntry]] - Grouped related errors
        - current_group_index: int - Index of current error group
        - total_groups: int - Total number of error groups
    """
    # Get log content - either from content string or file path
    if "log_content" in state and state["log_content"]:
        entries = parse_log_content(state["log_content"])
    elif "log_file_path" in state and state["log_file_path"]:
        entries = parse_log_file(state["log_file_path"])
    else:
        raise ValueError("State must contain either 'log_content' or 'log_file_path'")
    
    # Extract errors
    errors = extract_errors(entries)
    
    # Group related errors
    error_groups = group_errors_by_context(entries, errors)
    
    return {
        **state,
        "log_entries": entries,
        "error_entries": errors,
        "error_groups": error_groups,
        "current_group_index": 0,
        "total_groups": len(error_groups),
        # Keep legacy fields for compatibility
        "current_error_index": 0,
        "total_errors": len(errors)
    }
