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


def _get_source_code(source_file: str, source_dir: Path) -> str | None:
    """
    Load source code for the given file.
    
    Args:
        source_file: Filename from the log (e.g., "translator.cpp")
        source_dir: Base directory for source files
    
    Returns:
        Source code content or None if not found
    """
    # Try to find the file - it might be abbreviated in logs
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
