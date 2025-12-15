"""
GitHub Integration Node for LangGraph.

Handles creating branches, applying code changes, and creating PRs.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from github import Github, GithubException
from git import Repo, GitCommandError

from ..models.fix_proposal import FixProposal, CodeChange
from ..utils.config import get_config


class GitHubIntegration:
    """
    Handles all GitHub operations for the agent.
    """
    
    def __init__(self, token: str, repo_name: str, target_branch: str = "main"):
        """
        Initialize GitHub integration.
        
        Args:
            token: GitHub Personal Access Token
            repo_name: Repository name in format "owner/repo"
            target_branch: Branch to target for PRs
        """
        self.github = Github(token)
        self.repo_name = repo_name
        self.target_branch = target_branch
        self.repo = self.github.get_repo(repo_name)
    
    def create_branch(self, branch_name: str) -> str:
        """
        Create a new branch from the target branch.
        
        Args:
            branch_name: Name for the new branch
        
        Returns:
            Full ref name of the created branch
        """
        # Get the target branch's latest commit
        target_ref = self.repo.get_branch(self.target_branch)
        target_sha = target_ref.commit.sha
        
        # Create new branch ref
        ref_name = f"refs/heads/{branch_name}"
        try:
            self.repo.create_git_ref(ref_name, target_sha)
        except GithubException as e:
            if e.status == 422:  # Branch already exists
                # Delete and recreate
                try:
                    existing_ref = self.repo.get_git_ref(f"heads/{branch_name}")
                    existing_ref.delete()
                except:
                    pass
                self.repo.create_git_ref(ref_name, target_sha)
            else:
                raise
        
        return ref_name
    
    def update_file(
        self,
        file_path: str,
        new_content: str,
        branch: str,
        commit_message: str
    ) -> bool:
        """
        Update a file in the repository.
        
        Args:
            file_path: Path to the file (relative to repo root)
            new_content: New content for the file
            branch: Branch to commit to
            commit_message: Commit message
        
        Returns:
            True if successful
        """
        try:
            # Get current file to get its SHA
            contents = self.repo.get_contents(file_path, ref=branch)
            
            # Update the file
            self.repo.update_file(
                path=file_path,
                message=commit_message,
                content=new_content,
                sha=contents.sha,
                branch=branch
            )
            return True
        except GithubException as e:
            print(f"Error updating file {file_path}: {e}")
            return False
    
    def create_pull_request(
        self,
        title: str,
        body: str,
        head_branch: str,
        labels: Optional[list[str]] = None
    ) -> str:
        """
        Create a pull request.
        
        Args:
            title: PR title
            body: PR description body
            head_branch: Branch with changes
            labels: Optional labels to add
        
        Returns:
            URL of the created PR
        """
        pr = self.repo.create_pull(
            title=title,
            body=body,
            head=head_branch,
            base=self.target_branch
        )
        
        # Add labels if provided
        if labels:
            try:
                pr.add_to_labels(*labels)
            except GithubException:
                pass  # Labels might not exist
        
        return pr.html_url


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
        # Create GitHub integration
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
                
                # Update on GitHub
                gh.update_file(
                    file_path=change.file_path,
                    new_content=new_content,
                    branch=branch_name,
                    commit_message=f"fix: {change.explanation}"
                )
        
        # Create PR
        pr_url = gh.create_pull_request(
            title=fix_proposal.title,
            body=fix_proposal.get_pr_body(),
            head_branch=branch_name,
            labels=["automated-fix", "ai-generated"]
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
