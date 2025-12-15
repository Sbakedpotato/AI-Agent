"""
MCP (Model Context Protocol) Client for GitHub Integration.

Connects to the GitHub MCP server and provides tools to LangChain agents.
"""

import asyncio
import os
import subprocess
import sys
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from .config import get_config


# Global MCP client instance
_mcp_client: MultiServerMCPClient | None = None


def _get_mcp_client() -> MultiServerMCPClient:
    """
    Get or create the MCP client connected to GitHub server.
    
    Returns:
        Configured MultiServerMCPClient instance
    """
    global _mcp_client
    
    if _mcp_client is not None:
        return _mcp_client
    
    config = get_config()
    
    # Configure the GitHub MCP server
    _mcp_client = MultiServerMCPClient({
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {
                **os.environ,
                "GITHUB_PERSONAL_ACCESS_TOKEN": config.github_token,
            },
            "transport": "stdio",
        }
    })
    
    return _mcp_client


async def _call_tool_async(tool_name: str, arguments: dict[str, Any]) -> Any:
    """
    Call a specific GitHub MCP tool asynchronously.
    
    Args:
        tool_name: Name of the tool to call (e.g., "get_file_contents")
        arguments: Tool arguments
    
    Returns:
        Tool execution result
    """
    client = _get_mcp_client()
    
    # Get tools (new API - not a context manager)
    tools = await client.get_tools()
    
    # Find the tool by name
    for tool in tools:
        if tool.name == tool_name:
            result = await tool.ainvoke(arguments)
            return result
    
    raise ValueError(f"Tool '{tool_name}' not found in GitHub MCP server")


def get_file_contents_sync(owner: str, repo: str, path: str, branch: str = "main") -> str | None:
    """
    Synchronous wrapper to get file contents from GitHub via MCP.
    
    Args:
        owner: Repository owner
        repo: Repository name
        path: File path in the repository
        branch: Branch name (default: main)
    
    Returns:
        File contents as string, or None if not found
    """
    try:
        result = asyncio.run(_call_tool_async(
            "get_file_contents",
            {
                "owner": owner,
                "repo": repo,
                "path": path,
                "branch": branch,
            }
        ))
        
        # Extract content from result
        if isinstance(result, str):
            return result
        elif hasattr(result, 'content'):
            return result.content
        elif isinstance(result, dict) and 'content' in result:
            return result['content']
        return str(result) if result else None
        
    except Exception as e:
        print(f"⚠️ MCP get_file_contents failed: {e}")
        return None


def create_pull_request_sync(
    owner: str,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main"
) -> str | None:
    """
    Synchronous wrapper to create a pull request via MCP.
    
    Args:
        owner: Repository owner
        repo: Repository name
        title: PR title
        body: PR description
        head: Source branch
        base: Target branch (default: main)
    
    Returns:
        PR URL if successful, None otherwise
    """
    try:
        result = asyncio.run(_call_tool_async(
            "create_pull_request",
            {
                "owner": owner,
                "repo": repo,
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            }
        ))
        
        # Extract URL from result
        if isinstance(result, str):
            return result
        elif hasattr(result, 'html_url'):
            return result.html_url
        elif isinstance(result, dict) and 'html_url' in result:
            return result['html_url']
        return str(result) if result else None
        
    except Exception as e:
        print(f"⚠️ MCP create_pull_request failed: {e}")
        return None


def create_branch_sync(owner: str, repo: str, branch: str, from_branch: str = "main") -> bool:
    """
    Synchronous wrapper to create a branch via MCP.
    
    Args:
        owner: Repository owner
        repo: Repository name
        branch: New branch name
        from_branch: Base branch (default: main)
    
    Returns:
        True if successful
    """
    try:
        asyncio.run(_call_tool_async(
            "create_branch",
            {
                "owner": owner,
                "repo": repo,
                "branch": branch,
                "from_branch": from_branch,
            }
        ))
        return True
    except Exception as e:
        print(f"⚠️ MCP create_branch failed: {e}")
        return False


def push_files_sync(
    owner: str,
    repo: str,
    branch: str,
    files: list[dict],
    message: str
) -> bool:
    """
    Synchronous wrapper to push files to GitHub via MCP.
    
    Args:
        owner: Repository owner
        repo: Repository name
        branch: Target branch
        files: List of {"path": str, "content": str} dicts
        message: Commit message
    
    Returns:
        True if successful
    """
    try:
        asyncio.run(_call_tool_async(
            "push_files",
            {
                "owner": owner,
                "repo": repo,
                "branch": branch,
                "files": files,
                "message": message,
            }
        ))
        return True
    except Exception as e:
        print(f"⚠️ MCP push_files failed: {e}")
        return False


def cleanup_mcp():
    """Clean up MCP client."""
    global _mcp_client
    _mcp_client = None
