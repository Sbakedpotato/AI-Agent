"""
Error Report data model.

Represents the analysis result of an error from the logs.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .log_entry import LogEntry


class ErrorType(Enum):
    """Classification of error types."""
    CODE_BUG = "code_bug"                    # Logic error in code
    STRING_HANDLING = "string_handling"       # String/substring errors
    NULL_POINTER = "null_pointer"             # Null/empty checks missing
    MISSING_CONFIG = "missing_config"         # Configuration not found
    MISSING_DATA = "missing_data"             # Database/cache record not found
    DATABASE_ERROR = "database_error"         # DB operation failed
    CACHE_ERROR = "cache_error"               # Redis/cache operation failed
    EXTERNAL_SERVICE = "external_service"     # External service failure
    UNKNOWN = "unknown"                       # Could not classify


@dataclass
class ErrorReport:
    """
    Represents the analysis of an error extracted from logs.
    
    This is produced by the error_analyzer node after analyzing
    log entries with the LLM.
    """
    
    # The primary error log entry
    primary_error: LogEntry
    
    # Related log entries (context before/after the error)
    related_entries: List[LogEntry] = field(default_factory=list)
    
    # Error classification
    error_type: ErrorType = ErrorType.UNKNOWN
    
    # Is this a code issue or config/data issue?
    is_code_issue: bool = True
    
    # Root cause analysis from LLM
    root_cause: str = ""
    
    # Suggested approach to fix
    suggested_approach: str = ""
    
    # Relevant source file content (if applicable)
    source_code_context: Optional[str] = None
    
    # Confidence score (0-1) from analysis
    confidence: float = 0.0
    
    @property
    def severity(self) -> str:
        """Get severity based on log level."""
        if self.primary_error.is_critical():
            return "CRITICAL"
        return "ERROR"
    
    @property
    def affected_file(self) -> str:
        """Get the source file that needs to be modified."""
        return self.primary_error.source_file
    
    @property
    def affected_line(self) -> int:
        """Get the line number in the source file."""
        return self.primary_error.line_number
    
    def to_summary(self) -> str:
        """Get a brief summary of the error."""
        return (
            f"[{self.severity}] {self.error_type.value} in {self.affected_file}:{self.affected_line}\n"
            f"Message: {self.primary_error.message}\n"
            f"Root Cause: {self.root_cause}"
        )
    
    def __str__(self) -> str:
        return self.to_summary()
