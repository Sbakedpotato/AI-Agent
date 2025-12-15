"""
GitHub Integration Node for LangGraph.

Handles creating branches, applying code changes, and creating PRs via MCP.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..models.fix_proposal import FixProposal, CodeChange
from ..utils.config import get_config
from ..utils.mcp_client import (
    create_branch_sync,
    push_files_sync,
    create_pull_request_sync,
    get_file_contents_sync,
)


class GitHubIntegration:
    """
    Handles all GitHub operations for the agent via MCP.
    """
    
    def __init__(self, token: str, repo_name: str, target_branch: str = "main"):
        """
        Initialize GitHub integration.
        
        Args:
            token: GitHub Personal Access Token (used by MCP server)
            repo_name: Repository name in format "owner/repo"
            target_branch: Branch to target for PRs
        """
        self.token = token
        self.repo_name = repo_name
        self.target_branch = target_branch
        
        # Parse owner/repo
        try:
            self.owner, self.repo = repo_name.split("/")
        except ValueError:
            raise ValueError(f"Invalid repo_name format: {repo_name}. Expected 'owner/repo'")
    
    def create_branch(self, branch_name: str) -> str:
        """
        Create a new branch from the target branch via MCP.
        
        Args:
            branch_name: Name for the new branch
        
        Returns:
            Full ref name of the created branch
        """
        success = create_branch_sync(
            owner=self.owner,
            repo=self.repo,
            branch=branch_name,
            from_branch=self.target_branch
        )
        
        if success:
            print(f"✅ Created branch: {branch_name}")
            return f"refs/heads/{branch_name}"
        else:
            raise Exception(f"Failed to create branch: {branch_name}")
    
    def update_file(
        self,
        file_path: str,
        new_content: str,
        branch: str,
        commit_message: str
    ) -> bool:
        """
        Update a file in the repository via MCP push_files.
        
        Args:
            file_path: Path to the file (relative to repo root)
            new_content: New content for the file
            branch: Branch to commit to
            commit_message: Commit message
        
        Returns:
            True if successful
        
        Raises:
            Exception: If file update fails
        """
        # Normalize path separators
        file_path = file_path.replace("\\", "/")
        
        # Remove leading ./ or / if present
        if file_path.startswith("./"):
            file_path = file_path[2:]
        if file_path.startswith("/"):
            file_path = file_path[1:]
        
        success = push_files_sync(
            owner=self.owner,
            repo=self.repo,
            branch=branch,
            files=[{"path": file_path, "content": new_content}],
            message=commit_message
        )
        
        if success:
            print(f"✅ Updated {file_path} on branch {branch}")
            return True
        else:
            raise Exception(f"Failed to update file: {file_path}")
    
    def create_pull_request(
        self,
        title: str,
        body: str,
        head_branch: str,
        labels: Optional[list[str]] = None
    ) -> str:
        """
        Create a pull request via MCP.
        
        Args:
            title: PR title
            body: PR description body
            head_branch: Branch with changes
            labels: Optional labels (not supported via MCP yet)
        
        Returns:
            URL of the created PR
        """
        result = create_pull_request_sync(
            owner=self.owner,
            repo=self.repo,
            title=title,
            body=body,
            head=head_branch,
            base=self.target_branch
        )
        
        if result:
            print(f"✅ Created PR: {result}")
            return result
        else:
            raise Exception("Failed to create pull request")


def apply_code_change(
    file_path: Path,
    change: CodeChange
) -> str:
    """
    Apply a code change to a file and return the new content.
    
    Args:
        file_path: Full path to the file
        change: CodeChange to apply
    
    Returns:
        New file content with the change applied
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    content = file_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    # Find the original code and replace it
    original = change.original_code.strip()
    new = change.new_code
    
    # Try exact replacement first
    if original in content:
        new_content = content.replace(original, new, 1)
        return new_content
    
    # If exact match fails, try line-based replacement
    if change.line_start > 0 and change.line_end > 0:
        # Replace lines in the range
        start_idx = change.line_start - 1  # Convert to 0-indexed
        end_idx = change.line_end  # Exclusive end
        
        # Replace the lines
        new_lines = lines[:start_idx] + new.split('\n') + lines[end_idx:]
        return '\n'.join(new_lines)
    
    # Fallback: append the new code as a comment showing the suggested fix
    return content + f"\n\n/* SUGGESTED FIX:\n{new}\n*/\n"


def create_pr_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph node for creating GitHub PRs.
    
    Expects state to contain:
        - fix_proposal: FixProposal - The fix to apply
        - user_approved: bool - Whether user approved the fix
        - repo_root: Path - Local path to repository root
    
    Updates state with:
        - pr_url: str - URL of created PR (if successful)
        - pr_created: bool - Whether PR was created
        - pr_error: str - Error message if failed
    """
    config = get_config()
    
    fix_proposal = state.get("fix_proposal")
    user_approved = state.get("user_approved", False)
    
    if not user_approved or fix_proposal is None:
        return {
            **state,
            "pr_created": False,
            "pr_url": None,
            "pr_error": "Fix not approved or no fix available"
        }
    
    if not fix_proposal.requires_pr:
        return {
            **state,
            "pr_created": False,
            "pr_url": None,
            "pr_error": "This fix does not require a PR (config/data change)"
        }
    
    if not config.has_github_access:
        return {
            **state,
            "pr_created": False,
            "pr_url": None,
            "pr_error": "GitHub access not configured"
        }
    
    try:
        # Create GitHub integration via MCP
        gh = GitHubIntegration(
            token=config.github_token,
            repo_name=config.github_repo,
            target_branch=config.github_target_branch
        )
        
        # Create unique branch name
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"fix/auto-{timestamp}"
        gh.create_branch(branch_name)
        
        # Apply each code change
        repo_root = Path(state.get("repo_root", "."))
        for change in fix_proposal.code_changes:
            file_path = repo_root / change.file_path
            
            if file_path.exists():
                new_content = apply_code_change(file_path, change)
                
                # Update on GitHub via MCP
                gh.update_file(
                    file_path=change.file_path,
                    new_content=new_content,
                    branch=branch_name,
                    commit_message=f"fix: {change.explanation}"
                )
        
        # Create PR via MCP
        pr_url = gh.create_pull_request(
            title=fix_proposal.title,
            body=fix_proposal.get_pr_body(),
            head_branch=branch_name
        )
        
        return {
            **state,
            "pr_created": True,
            "pr_url": pr_url,
            "pr_error": None
        }
    
    except Exception as e:
        return {
            **state,
            "pr_created": False,
            "pr_url": None,
            "pr_error": str(e)
        }
