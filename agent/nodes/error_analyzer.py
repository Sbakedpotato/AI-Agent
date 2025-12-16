"""
Error Analyzer Node for LangGraph.

Uses Gemini or Groq LLM to analyze errors and classify them.
"""

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ..models.log_entry import LogEntry
from ..models.error_report import ErrorReport, ErrorType
from ..prompts.analyzer_prompt import ANALYZER_SYSTEM_PROMPT, get_analyzer_prompt
from ..utils.config import get_config
from .log_parser import group_related_entries


def create_llm():
    """Create the LLM instance based on configuration."""
    config = get_config()
    
    if config.llm_provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=config.groq_model,
            api_key=config.groq_api_key,
            temperature=config.temperature
        )
    else:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=config.gemini_model,
            google_api_key=config.google_api_key,
            temperature=config.temperature
        )


def _get_source_from_github(source_file: str) -> str | None:
    """
    Fetch source code from the configured GitHub repository via MCP.
    
    Args:
        source_file: Filename from the log (e.g., "translator.cpp")
    
    Returns:
        Source code content or None if not found
    """
    from ..utils.mcp_client import get_file_contents_sync
    
    config = get_config()
    
    if not config.has_github_access:
        return None
    
    # Parse owner/repo from config
    try:
        owner, repo = config.github_repo.split("/")
    except ValueError:
        print(f"⚠️ Invalid GITHUB_REPO format: {config.github_repo}")
        return None
    
    # Try different path patterns
    possible_paths = [
        f"src/{source_file}",           # src/translator.cpp
        source_file,                     # translator.cpp
        f"source/{source_file}",         # source/translator.cpp
        f"include/{source_file}",        # include/translator.h
    ]
    
    # Also handle truncated names (e.g., "translatormasterca" -> "translatormastercard.cpp")
    base_name = source_file.replace('.cpp', '').replace('.h', '')
    if not source_file.endswith(('.cpp', '.h')):
        possible_paths.extend([
            f"src/{base_name}.cpp",
            f"src/{base_name}.h",
        ])
    
    for path in possible_paths:
        content = get_file_contents_sync(
            owner=owner,
            repo=repo,
            path=path,
            branch=config.github_target_branch
        )
        if content:
            print(f"📄 Loaded source from GitHub via MCP: {path}")
            return content
    
    return None


def _parse_includes(source_code: str) -> list[str]:
    """
    Parse #include statements from C++ source code.
    
    Args:
        source_code: C++ source code content
    
    Returns:
        List of included file names (without path, just filename)
    """
    import re
    
    includes = []
    
    # Match both #include "file.h" and #include <file.h>
    # We focus on local includes ("") as they're more likely to be in the repo
    patterns = [
        r'#include\s*"([^"]+)"',  # #include "file.h"
        r'#include\s*<([^>]+)>',  # #include <file.h> (less likely to be local)
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, source_code)
        for match in matches:
            # Extract just the filename, not the path
            filename = match.split('/')[-1]
            if filename not in includes:
                includes.append(filename)
    
    return includes


def _get_source_with_includes(source_file: str, max_includes: int = 5) -> str | None:
    """
    Fetch source code along with its included files for better context.
    
    Args:
        source_file: Main source file from the log
        max_includes: Maximum number of included files to fetch (to limit API calls)
    
    Returns:
        Combined source code with main file and includes, or None if not found
    """
    # Get the main source file
    main_content = _get_source_from_github(source_file)
    
    if not main_content:
        return None
    
    # Parse includes from the main file
    includes = _parse_includes(main_content)
    
    if not includes:
        return main_content
    
    # Build combined content with main file first
    combined_parts = [
        f"// ===== MAIN FILE: {source_file} =====",
        main_content,
    ]
    
    # Fetch included files (limit to prevent too many API calls)
    fetched_count = 0
    for include_file in includes[:max_includes]:
        # Skip system headers (likely not in repo)
        if include_file.startswith(('std', 'cstd', 'iostream', 'string', 'vector', 'map')):
            continue
        
        include_content = _get_source_from_github(include_file)
        if include_content:
            combined_parts.append(f"\n\n// ===== INCLUDED FILE: {include_file} =====")
            combined_parts.append(include_content)
            fetched_count += 1
    
    if fetched_count > 0:
        print(f"📎 Also loaded {fetched_count} included file(s)")
    
    return "\n".join(combined_parts)


def _get_source_code(source_file: str, source_dir: Path) -> str | None:
    """
    Load source code for the given file.
    
    First tries to fetch from GitHub (with includes), then falls back to local filesystem.
    
    Args:
        source_file: Filename from the log (e.g., "translator.cpp")
        source_dir: Base directory for source files (fallback)
    
    Returns:
        Source code content or None if not found
    """
    # Try GitHub first with includes (if configured)
    github_content = _get_source_with_includes(source_file)
    if github_content:
        return github_content
    
    # Fallback to local filesystem (no include parsing for local files)
    possible_names = [
        source_file,
        source_file.replace('.cpp', ''),
        source_file.replace('.h', ''),
    ]
    
    for name in possible_names:
        # Check direct match
        for ext in ['.cpp', '.h', '']:
            file_path = source_dir / f"{name}{ext}"
            if file_path.exists():
                return file_path.read_text(encoding='utf-8', errors='replace')
        
        # Also check for partial matches (logs often truncate names)
        if source_dir.exists():
            for file in source_dir.glob('*'):
                if file.is_file() and name in file.name:
                    return file.read_text(encoding='utf-8', errors='replace')
    
    return None


def _parse_llm_response(response: str) -> dict:
    """
    Parse JSON response from LLM, handling potential formatting issues.
    
    Args:
        response: Raw LLM response string
    
    Returns:
        Parsed dictionary
    """
    # Try to extract JSON from the response
    text = response.strip()
    
    # Remove markdown code blocks if present
    if text.startswith('```json'):
        text = text[7:]
    elif text.startswith('```'):
        text = text[3:]
    
    if text.endswith('```'):
        text = text[:-3]
    
    text = text.strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON in the response
        import re
        json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # Return default if parsing fails
        return {
            "error_type": "unknown",
            "is_code_issue": True,
            "root_cause": "Failed to parse LLM response",
            "suggested_approach": "Manual analysis required",
            "confidence": 0.0
        }


def _error_type_from_string(error_type_str: str) -> ErrorType:
    """Convert string error type to ErrorType enum."""
    mapping = {
        "code_bug": ErrorType.CODE_BUG,
        "string_handling": ErrorType.STRING_HANDLING,
        "null_pointer": ErrorType.NULL_POINTER,
        "missing_config": ErrorType.MISSING_CONFIG,
        "missing_data": ErrorType.MISSING_DATA,
        "database_error": ErrorType.DATABASE_ERROR,
        "cache_error": ErrorType.CACHE_ERROR,
        "external_service": ErrorType.EXTERNAL_SERVICE,
    }
    return mapping.get(error_type_str.lower(), ErrorType.UNKNOWN)


async def analyze_error_async(
    error_entry: LogEntry,
    all_entries: list[LogEntry],
    source_dir: Path,
    llm: Any
) -> ErrorReport:
    """
    Analyze a single error entry using the LLM.
    
    Args:
        error_entry: The error log entry to analyze
        all_entries: All log entries for context
        source_dir: Path to source code directory
        llm: The LLM instance to use
    
    Returns:
        ErrorReport with analysis results
    """
    # Get related context entries
    related = group_related_entries(all_entries, error_entry, context_lines=5)
    
    # Build log context string
    log_context = "\n".join(entry.to_context_string() for entry in related)
    
    # Try to load relevant source code
    source_code = _get_source_code(error_entry.source_file, source_dir)
    
    # Build the prompt
    prompt = get_analyzer_prompt(
        error_logs=log_context,
        source_code=source_code
    )
    
    # Call LLM
    messages = [
        SystemMessage(content=ANALYZER_SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ]
    
    response = await llm.ainvoke(messages)
    analysis = _parse_llm_response(response.content)
    
    # Build ErrorReport
    return ErrorReport(
        primary_error=error_entry,
        related_entries=related,
        error_type=_error_type_from_string(analysis.get("error_type", "unknown")),
        is_code_issue=analysis.get("is_code_issue", True),
        root_cause=analysis.get("root_cause", "Unknown"),
        suggested_approach=analysis.get("suggested_approach", "Unknown"),
        source_code_context=source_code,
        confidence=float(analysis.get("confidence", 0.5))
    )


def analyze_error_sync(
    error_entry: LogEntry,
    all_entries: list[LogEntry],
    source_dir: Path,
    llm: Any
) -> ErrorReport:
    """
    Synchronous version of error analysis.
    """
    # Get related context entries
    related = group_related_entries(all_entries, error_entry, context_lines=5)
    
    # Build log context string
    log_context = "\n".join(entry.to_context_string() for entry in related)
    
    # Try to load relevant source code
    source_code = _get_source_code(error_entry.source_file, source_dir)
    
    # Build the prompt
    prompt = get_analyzer_prompt(
        error_logs=log_context,
        source_code=source_code
    )
    
    # Call LLM
    messages = [
        SystemMessage(content=ANALYZER_SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ]
    
    response = llm.invoke(messages)
    analysis = _parse_llm_response(response.content)
    
    # Build ErrorReport
    return ErrorReport(
        primary_error=error_entry,
        related_entries=related,
        error_type=_error_type_from_string(analysis.get("error_type", "unknown")),
        is_code_issue=analysis.get("is_code_issue", True),
        root_cause=analysis.get("root_cause", "Unknown"),
        suggested_approach=analysis.get("suggested_approach", "Unknown"),
        source_code_context=source_code,
        confidence=float(analysis.get("confidence", 0.5))
    )


def analyze_error_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph node for analyzing the current error.
    
    Expects state to contain:
        - error_entries: List[LogEntry] - All error entries
        - log_entries: List[LogEntry] - All log entries for context
        - current_error_index: int - Index of current error
        - source_dir: Path - Path to source code
        - llm: ChatGoogleGenerativeAI - LLM instance
    
    Updates state with:
        - current_error_report: ErrorReport - Analysis of current error
    """
    config = get_config()
    
    # Get current error
    errors = state.get("error_entries", [])
    index = state.get("current_error_index", 0)
    
    if index >= len(errors):
        return {
            **state,
            "current_error_report": None,
            "analysis_complete": True
        }
    
    current_error = errors[index]
    all_entries = state.get("log_entries", errors)
    
    # Get paths
    source_dir = Path(state.get("source_dir", config.source_path))
    
    # Get or create LLM
    llm = state.get("llm")
    if llm is None:
        llm = create_llm()
    
    # Analyze the error
    report = analyze_error_sync(current_error, all_entries, source_dir, llm)
    
    return {
        **state,
        "current_error_report": report,
        "llm": llm,
        "analysis_complete": False
    }
