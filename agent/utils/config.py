"""
Configuration management for the Log Analyzer Agent.

Loads settings from environment variables and .env file.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


class Config:
    """
    Configuration manager for the agent.
    
    Loads configuration from environment variables, with fallback to .env file.
    """
    
    _instance: Optional["Config"] = None
    
    def __new__(cls) -> "Config":
        """Singleton pattern to ensure single config instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize configuration (only runs once due to singleton)."""
        if self._initialized:
            return
        
        # Find and load .env file
        self._load_env()
        
        # Google Gemini API
        self.google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
        
        # GitHub settings
        self.github_token: str = os.getenv("GITHUB_TOKEN", "")
        self.github_repo: str = os.getenv("GITHUB_REPO", "")
        self.github_target_branch: str = os.getenv("GITHUB_TARGET_BRANCH", "main")
        
        # Paths
        self.source_path: str = os.getenv("SOURCE_PATH", "src")
        self.logs_path: str = os.getenv("LOGS_PATH", "logs for reference")
        
        # LLM Provider settings
        # Options: "gemini" or "groq"
        self.llm_provider: str = os.getenv("LLM_PROVIDER", "groq")  # Default to Groq
        
        # Gemini settings
        self.google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
        
        # Groq settings (free tier with Llama models)
        self.groq_api_key: str = os.getenv("GROQ_API_KEY", "")
        self.groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        
        # General settings
        self.temperature: float = float(os.getenv("TEMPERATURE", "0.2"))
        
        self._initialized = True
    
    def _load_env(self) -> None:
        """Load .env file if it exists."""
        # Try to find .env in current directory or parent directories
        current = Path.cwd()
        for _ in range(5):  # Search up to 5 levels up
            env_path = current / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                return
            current = current.parent
        
        # Also try the agent module directory
        agent_dir = Path(__file__).parent.parent.parent
        env_path = agent_dir / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    
    @property
    def is_configured(self) -> bool:
        """Check if required configuration is present."""
        if self.llm_provider == "groq":
            return bool(self.groq_api_key)
        return bool(self.google_api_key)
    
    @property
    def has_github_access(self) -> bool:
        """Check if GitHub access is configured."""
        return bool(self.github_token and self.github_repo)
    
    def validate(self) -> list[str]:
        """
        Validate configuration and return list of missing items.
        
        Returns:
            List of missing configuration items (empty if all valid)
        """
        missing = []
        
        if self.llm_provider == "groq":
            if not self.groq_api_key:
                missing.append("GROQ_API_KEY - Get from https://console.groq.com/keys")
        else:
            if not self.google_api_key:
                missing.append("GOOGLE_API_KEY - Get from https://aistudio.google.com/apikey")
        
        if not self.github_token:
            missing.append("GITHUB_TOKEN - Create at https://github.com/settings/tokens/new")
        
        if not self.github_repo:
            missing.append("GITHUB_REPO - Format: owner/repo (e.g., Sbakedpotato/Dummy-Log-Creation-Code)")
        
        return missing
    
    def get_source_dir(self, repo_root: Path) -> Path:
        """Get absolute path to source directory."""
        return repo_root / self.source_path
    
    def get_logs_dir(self, repo_root: Path) -> Path:
        """Get absolute path to logs directory."""
        return repo_root / self.logs_path
    
    def __repr__(self) -> str:
        return (
            f"Config(\n"
            f"  google_api_key={'***' if self.google_api_key else 'NOT SET'},\n"
            f"  github_token={'***' if self.github_token else 'NOT SET'},\n"
            f"  github_repo={self.github_repo or 'NOT SET'},\n"
            f"  github_target_branch={self.github_target_branch},\n"
            f"  source_path={self.source_path},\n"
            f"  model_name={self.model_name}\n"
            f")"
        )


def get_config() -> Config:
    """Get the configuration singleton."""
    return Config()
