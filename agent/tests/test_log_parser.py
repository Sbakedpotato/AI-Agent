"""
Unit tests for the log parser module.
"""

import pytest
from pathlib import Path

from agent.nodes.log_parser import (
    parse_log_line,
    parse_log_content,
    extract_errors,
    group_related_entries
)
from agent.models.log_entry import LogEntry


# Sample log lines for testing
SAMPLE_INFO_LINE = "17:13:30.548 \tINFO \ttranslator.cpp     \t0078 \tProcessIncomin \t58197610545000 STEP1: Message fields parsed successfully"
SAMPLE_ERROR_LINE = "17:13:30.550 \tERROR \ttranslator.cpp     \t1654 \tCheckCondition \t58197610545000 Condition unmatched"
SAMPLE_CRITICAL_LINE = "17:13:34.662 \tCRITICAL \ttranslatormasterca \t0204 \tmapIncomingFie \t58197610545001 failed to parse additionalPOSInformation basic_string::substr: __pos (which is 3) > this->size() (which is 0)"


class TestParseLogLine:
    """Tests for parse_log_line function."""
    
    def test_parse_info_line(self):
        """Test parsing an INFO level log line."""
        entry = parse_log_line(SAMPLE_INFO_LINE)
        
        assert entry is not None
        assert entry.timestamp == "17:13:30.548"
        assert entry.level == "INFO"
        assert entry.source_file == "translator.cpp"
        assert entry.line_number == 78
        assert entry.function_name == "ProcessIncomin"
        assert entry.thread_id == "58197610545000"
        assert "STEP1: Message fields parsed" in entry.message
    
    def test_parse_error_line(self):
        """Test parsing an ERROR level log line."""
        entry = parse_log_line(SAMPLE_ERROR_LINE)
        
        assert entry is not None
        assert entry.level == "ERROR"
        assert entry.is_error() is True
        assert entry.is_critical() is False
    
    def test_parse_critical_line(self):
        """Test parsing a CRITICAL level log line."""
        entry = parse_log_line(SAMPLE_CRITICAL_LINE)
        
        assert entry is not None
        assert entry.level == "CRITICAL"
        assert entry.is_error() is True
        assert entry.is_critical() is True
        assert "basic_string::substr" in entry.message
    
    def test_parse_empty_line(self):
        """Test parsing an empty line returns None."""
        assert parse_log_line("") is None
        assert parse_log_line("   ") is None
    
    def test_parse_malformed_line(self):
        """Test parsing a malformed line returns None."""
        assert parse_log_line("This is not a valid log line") is None
        assert parse_log_line("17:13:30 INFO incomplete") is None


class TestParseLogContent:
    """Tests for parse_log_content function."""
    
    def test_parse_multiple_lines(self):
        """Test parsing multiple log lines."""
        content = f"{SAMPLE_INFO_LINE}\n{SAMPLE_ERROR_LINE}\n{SAMPLE_CRITICAL_LINE}"
        entries = parse_log_content(content)
        
        assert len(entries) == 3
        assert entries[0].level == "INFO"
        assert entries[1].level == "ERROR"
        assert entries[2].level == "CRITICAL"
    
    def test_parse_with_empty_lines(self):
        """Test parsing content with empty lines."""
        content = f"{SAMPLE_INFO_LINE}\n\n{SAMPLE_ERROR_LINE}\n\n"
        entries = parse_log_content(content)
        
        assert len(entries) == 2
    
    def test_parse_empty_content(self):
        """Test parsing empty content."""
        entries = parse_log_content("")
        assert len(entries) == 0


class TestExtractErrors:
    """Tests for extract_errors function."""
    
    def test_extract_errors_only(self):
        """Test that only ERROR and CRITICAL entries are extracted."""
        content = f"{SAMPLE_INFO_LINE}\n{SAMPLE_ERROR_LINE}\n{SAMPLE_CRITICAL_LINE}"
        entries = parse_log_content(content)
        errors = extract_errors(entries)
        
        assert len(errors) == 2
        assert all(e.is_error() for e in errors)
    
    def test_extract_no_errors(self):
        """Test extraction when there are no errors."""
        entries = parse_log_content(SAMPLE_INFO_LINE)
        errors = extract_errors(entries)
        
        assert len(errors) == 0


class TestGroupRelatedEntries:
    """Tests for group_related_entries function."""
    
    def test_group_same_thread(self):
        """Test grouping entries by thread ID."""
        # All entries have the same thread ID
        content = f"{SAMPLE_INFO_LINE}\n{SAMPLE_ERROR_LINE}"
        entries = parse_log_content(content)
        target = entries[1]  # The ERROR entry
        
        related = group_related_entries(entries, target, context_lines=5)
        
        # Should include both entries (same thread)
        assert len(related) == 2
    
    def test_group_different_threads(self):
        """Test that different thread IDs are excluded."""
        # INFO and ERROR have thread 58197610545000, CRITICAL has 58197610545001
        content = f"{SAMPLE_INFO_LINE}\n{SAMPLE_ERROR_LINE}\n{SAMPLE_CRITICAL_LINE}"
        entries = parse_log_content(content)
        target = entries[2]  # The CRITICAL entry with different thread
        
        related = group_related_entries(entries, target, context_lines=5)
        
        # Should only include the CRITICAL entry (different thread)
        assert len(related) == 1
        assert related[0].level == "CRITICAL"


class TestLogEntryMethods:
    """Tests for LogEntry methods."""
    
    def test_source_location(self):
        """Test source_location property."""
        entry = parse_log_line(SAMPLE_ERROR_LINE)
        assert entry.source_location == "translator.cpp:1654"
    
    def test_to_context_string(self):
        """Test to_context_string method."""
        entry = parse_log_line(SAMPLE_ERROR_LINE)
        context = entry.to_context_string()
        
        assert "[ERROR]" in context
        assert "translator.cpp:1654" in context
        assert "CheckCondition()" in context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
