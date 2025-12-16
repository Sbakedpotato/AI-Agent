"""
Test script for MCP GitHub integration.

Tests branch creation, file push, and PR creation via MCP.
"""

import asyncio
from datetime import datetime

# Add parent to path for imports
import sys
sys.path.insert(0, ".")

from agent.utils.mcp_client import (
    create_branch_sync,
    push_files_sync,
    create_pull_request_sync,
    get_file_contents_sync,
)
from agent.utils.config import get_config


def test_get_file():
    """Test getting a file from GitHub via MCP."""
    config = get_config()
    owner, repo = config.github_repo.split("/")
    
    print("=" * 50)
    print("TEST: Get file contents via MCP")
    print("=" * 50)
    
    result = get_file_contents_sync(
        owner=owner,
        repo=repo,
        path="README.md",
        branch=config.github_target_branch
    )
    
    if result:
        print(f"✅ SUCCESS! Got {len(result)} characters")
        print(f"   First 100 chars: {result[:100]}...")
    else:
        print("❌ FAILED to get file")
    
    return result is not None


def test_create_branch():
    """Test creating a branch via MCP."""
    config = get_config()
    owner, repo = config.github_repo.split("/")
    
    branch_name = f"test/mcp-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    print()
    print("=" * 50)
    print(f"TEST: Create branch '{branch_name}' via MCP")
    print("=" * 50)
    
    result = create_branch_sync(
        owner=owner,
        repo=repo,
        branch=branch_name,
        from_branch=config.github_target_branch
    )
    
    if result:
        print(f"✅ SUCCESS! Created branch: {branch_name}")
    else:
        print("❌ FAILED to create branch")
    
    return branch_name if result else None


def test_push_files(branch_name: str):
    """Test pushing files via MCP."""
    config = get_config()
    owner, repo = config.github_repo.split("/")
    
    print()
    print("=" * 50)
    print(f"TEST: Push file to '{branch_name}' via MCP")
    print("=" * 50)
    
    test_content = f"""# MCP Test File
    
This file was created via MCP (Model Context Protocol).

Created at: {datetime.now().isoformat()}
"""
    
    result = push_files_sync(
        owner=owner,
        repo=repo,
        branch=branch_name,
        files=[{"path": "test_mcp.md", "content": test_content}],
        message="test: MCP push_files test"
    )
    
    if result:
        print(f"✅ SUCCESS! Pushed test_mcp.md to {branch_name}")
    else:
        print("❌ FAILED to push files")
    
    return result


def test_create_pr(branch_name: str):
    """Test creating a PR via MCP."""
    config = get_config()
    owner, repo = config.github_repo.split("/")
    
    print()
    print("=" * 50)
    print(f"TEST: Create PR from '{branch_name}' via MCP")
    print("=" * 50)
    
    result = create_pull_request_sync(
        owner=owner,
        repo=repo,
        title="[TEST] MCP Integration Test",
        body="This PR was created automatically to test MCP GitHub integration.\n\n**You can safely close this PR.**",
        head=branch_name,
        base=config.github_target_branch
    )
    
    if result:
        print(f"✅ SUCCESS! Created PR: {result}")
    else:
        print("❌ FAILED to create PR")
    
    return result


if __name__ == "__main__":
    print("\n🧪 MCP GitHub Integration Test\n")
    
    # Test 1: Get file
    if not test_get_file():
        print("\n⚠️ File fetching failed, but continuing with other tests...")
    
    # Test 2: Create branch
    branch = test_create_branch()
    if not branch:
        print("\n❌ Cannot continue without a branch")
        exit(1)
    
    # Test 3: Push files
    if not test_push_files(branch):
        print("\n❌ Cannot create PR without pushing files")
        exit(1)
    
    # Test 4: Create PR
    pr_url = test_create_pr(branch)
    
    print()
    print("=" * 50)
    print("TEST COMPLETE")
    print("=" * 50)
    
    if pr_url:
        print(f"\n🎉 All tests passed!")
        print(f"   PR URL: {pr_url}")
        print(f"\n   Don't forget to close the test PR!")
    else:
        print("\n⚠️ Some tests failed. Check the output above.")
