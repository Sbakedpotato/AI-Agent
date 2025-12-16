"""
Tests for include file parsing and fetching.
"""

import pytest
from agent.nodes.error_analyzer import _parse_includes, _get_source_with_includes


class TestParseIncludes:
    """Tests for _parse_includes function."""
    
    def test_parse_double_quote_includes(self):
        """Test parsing #include "file.h" style includes."""
        source = '''
#include "translator.h"
#include "utils/helper.h"

void main() {}
'''
        includes = _parse_includes(source)
        
        assert "translator.h" in includes
        assert "helper.h" in includes  # Should extract just filename
    
    def test_parse_angle_bracket_includes(self):
        """Test parsing #include <file.h> style includes."""
        source = '''
#include <iostream>
#include <customlib.h>

void main() {}
'''
        includes = _parse_includes(source)
        
        assert "iostream" in includes
        assert "customlib.h" in includes
    
    def test_parse_mixed_includes(self):
        """Test parsing both styles of includes."""
        source = '''
#include <iostream>
#include "myheader.h"
#include <vector>
#include "utils/config.h"
'''
        includes = _parse_includes(source)
        
        assert "iostream" in includes
        assert "myheader.h" in includes
        assert "vector" in includes
        assert "config.h" in includes
    
    def test_no_duplicate_includes(self):
        """Test that duplicate includes are not repeated."""
        source = '''
#include "header.h"
#include "header.h"
#include "header.h"
'''
        includes = _parse_includes(source)
        
        assert includes.count("header.h") == 1
    
    def test_empty_source(self):
        """Test parsing empty source returns empty list."""
        includes = _parse_includes("")
        assert includes == []
    
    def test_no_includes(self):
        """Test parsing source with no includes."""
        source = '''
void main() {
    printf("Hello World");
}
'''
        includes = _parse_includes(source)
        assert includes == []
    
    def test_complex_paths(self):
        """Test parsing includes with complex paths."""
        source = '''
#include "core/models/transaction.h"
#include "../shared/utils.h"
#include "../../common/logger.h"
'''
        includes = _parse_includes(source)
        
        # Should extract just the final filename
        assert "transaction.h" in includes
        assert "utils.h" in includes
        assert "logger.h" in includes


class TestGetSourceWithIncludes:
    """Tests for _get_source_with_includes function (requires MCP/GitHub)."""
    
    @pytest.fixture
    def mock_github_config(self, monkeypatch):
        """Mock GitHub configuration."""
        # This would need actual mocking of the MCP client
        pass
    
    def test_returns_none_for_nonexistent_file(self):
        """Test that nonexistent files return None."""
        # This test requires MCP to be running
        result = _get_source_with_includes("nonexistent_file_xyz123.cpp")
        assert result is None
    
    # Note: Full integration tests would require:
    # 1. MCP server running
    # 2. Valid GitHub credentials
    # 3. Actual files in the repo
    # 
    # For unit testing, we would mock the MCP client responses


if __name__ == "__main__":
    # Run basic tests without pytest
    print("Testing _parse_includes...")
    
    # Test 1
    source = '#include "test.h"\n#include <iostream>'
    result = _parse_includes(source)
    assert "test.h" in result, f"Expected 'test.h' in {result}"
    assert "iostream" in result, f"Expected 'iostream' in {result}"
    print("✅ Parse includes: PASSED")
    
    # Test 2
    source = '#include "path/to/file.h"'
    result = _parse_includes(source)
    assert "file.h" in result, f"Expected 'file.h' in {result}"
    print("✅ Path extraction: PASSED")
    
    # Test 3
    result = _parse_includes("")
    assert result == [], f"Expected empty list, got {result}"
    print("✅ Empty source: PASSED")
    
    print("\n🎉 All include parsing tests passed!")
