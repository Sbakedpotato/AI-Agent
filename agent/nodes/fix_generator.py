"""
Fix Generator Node for LangGraph.

Generates fix proposals based on error analysis.
"""

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ..models.error_report import ErrorReport
from ..models.fix_proposal import FixProposal, FixType, CodeChange
from ..prompts.fix_generator_prompt import FIX_GENERATOR_SYSTEM_PROMPT, get_fix_generator_prompt
from ..utils.config import get_config
from .error_analyzer import create_llm


def _parse_llm_response(response: str) -> dict:
    """Parse JSON response from LLM."""
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
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        return {
            "title": "Unable to generate fix",
            "description": "Failed to parse LLM response",
            "risk_level": "high",
            "confidence": 0.0,
            "code_changes": [],
            "manual_instructions": "Manual analysis required"
        }


def _fix_type_from_string(fix_type_str: str) -> FixType:
    """Convert string to FixType enum."""
    mapping = {
        "code_change": FixType.CODE_CHANGE,
        "config_change": FixType.CONFIG_CHANGE,
        "data_insert": FixType.DATA_INSERT,
        "data_update": FixType.DATA_UPDATE,
        "multiple": FixType.MULTIPLE,
    }
    return mapping.get(fix_type_str.lower(), FixType.CODE_CHANGE)


def generate_fix_sync(
    error_report: ErrorReport,
    source_dir: Path,
    llm: Any
) -> FixProposal:
    """
    Generate a fix proposal for an analyzed error.
    
    Args:
        error_report: The error analysis
        source_dir: Path to source code directory
        llm: The LLM instance
    
    Returns:
        FixProposal with suggested fix
    """
    # Build analysis dict for prompt
    error_analysis = {
        "root_cause": error_report.root_cause,
        "suggested_approach": error_report.suggested_approach,
        "affected_function": error_report.primary_error.function_name,
        "error_type": error_report.error_type.value
    }
    
    # Get source code
    source_code = error_report.source_code_context or "Source code not available"
    file_path = f"{source_dir}/{error_report.affected_file}"
    
    # Build prompt
    prompt = get_fix_generator_prompt(
        error_analysis=error_analysis,
        source_code=source_code,
        file_path=file_path,
        error_type=error_report.error_type.value,
        is_code_issue=error_report.is_code_issue
    )
    
    # Call LLM
    messages = [
        SystemMessage(content=FIX_GENERATOR_SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ]
    
    response = llm.invoke(messages)
    fix_data = _parse_llm_response(response.content)
    
    # Build CodeChange objects
    code_changes = []
    for change in fix_data.get("code_changes", []):
        code_changes.append(CodeChange(
            file_path=change.get("file_path", file_path),
            original_code=change.get("original_code", ""),
            new_code=change.get("new_code", ""),
            line_start=change.get("line_start", 0),
            line_end=change.get("line_end", 0),
            explanation=change.get("explanation", "")
        ))
    
    # Determine fix type
    if error_report.is_code_issue:
        fix_type = FixType.CODE_CHANGE
    else:
        fix_type = _fix_type_from_string(fix_data.get("fix_type", "config_change"))
    
    # Build FixProposal
    return FixProposal(
        error_summary=error_report.to_summary(),
        fix_type=fix_type,
        title=fix_data.get("title", "Fix error"),
        description=fix_data.get("description", ""),
        code_changes=code_changes,
        config_changes=fix_data.get("config_changes", {}),
        data_operations=fix_data.get("data_operations", []),
        manual_instructions=fix_data.get("manual_instructions"),
        confidence=float(fix_data.get("confidence", 0.5)),
        risk_level=fix_data.get("risk_level", "medium"),
        affected_files=[error_report.affected_file] if error_report.is_code_issue else []
    )


def generate_fix_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph node for generating fix proposals.
    
    Expects state to contain:
        - current_error_report: ErrorReport - The analyzed error
        - source_dir: Path - Path to source code
        - llm: ChatGoogleGenerativeAI - LLM instance
    
    Updates state with:
        - fix_proposal: FixProposal - The generated fix
    """
    config = get_config()
    
    error_report = state.get("current_error_report")
    if error_report is None:
        return {
            **state,
            "fix_proposal": None
        }
    
    source_dir = Path(state.get("source_dir", config.source_path))
    llm = state.get("llm")
    
    if llm is None:
        llm = create_llm()
    
    fix = generate_fix_sync(error_report, source_dir, llm)
    
    return {
        **state,
        "fix_proposal": fix,
        "llm": llm
    }
