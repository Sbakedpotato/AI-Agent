"""
Log Entry data model.

Represents a single parsed log line from the C++ application logs.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class LogEntry:
    """
    Represents a single log entry parsed from log files.
    
    Log format: Time \t Level \t FileName \t LineNumber \t FunctionName \t ThreadID Message
    Example: 17:13:30.548 	INFO 	translator.cpp     	0078 	ProcessIncomin 	58197610545000 STEP1: Message fields parsed
    """
    
    timestamp: str          # "17:13:30.548"
    level: str              # INFO, ERROR, WARNING, CRITICAL
    source_file: str        # "translator.cpp"
    line_number: int        # 78
    function_name: str      # "ProcessIncomin"
    thread_id: str          # "58197610545000"
    message: str            # "STEP1: Message fields parsed successfully"
    raw_line: str           # Original unparsed line
    
    def is_error(self) -> bool:
        """Check if this log entry represents an error."""
        return self.level in ("ERROR", "CRITICAL")
    
    def is_critical(self) -> bool:
        """Check if this is a critical error."""
        return self.level == "CRITICAL"
    
    @property
    def source_location(self) -> str:
        """Get formatted source location (file:line)."""
        return f"{self.source_file}:{self.line_number}"
    
    def to_context_string(self) -> str:
        """Format log entry for LLM context."""
        return (
            f"[{self.level}] {self.source_file}:{self.line_number} "
            f"in {self.function_name}() - {self.message}"
        )
    
    def __str__(self) -> str:
        return f"{self.timestamp} {self.level} {self.source_location} {self.message}"
