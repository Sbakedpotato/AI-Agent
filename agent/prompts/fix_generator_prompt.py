"""
LLM prompts for fix generation.

These prompts guide the Gemini model to generate appropriate fixes
for identified errors.
"""

FIX_GENERATOR_SYSTEM_PROMPT = """You are an expert C++ developer specializing in payment systems. Your job is to generate fixes for errors identified in a payment switch application.

You will receive:
1. Error analysis with root cause
2. Relevant source code
3. Error type classification

You must generate:
1. For CODE issues: Exact code changes with line numbers
2. For CONFIG issues: Configuration parameters to add
3. For DATA issues: SQL or Redis commands to insert missing data

Your fixes must be:
- Precise and minimal (only change what's necessary)
- Safe (include validation, null checks, error handling)
- Well-documented (explain why the change fixes the issue)
- Consistent with the existing code style
"""


def get_fix_generator_prompt(
    error_analysis: dict,
    source_code: str,
    file_path: str,
    error_type: str,
    is_code_issue: bool
) -> str:
    """
    Generate the fix generation prompt for the LLM.
    
    Args:
        error_analysis: The error analysis from the analyzer
        source_code: The source code that needs to be fixed
        file_path: Path to the source file
        error_type: Classification of the error
        is_code_issue: Whether this requires code changes
    
    Returns:
        Formatted prompt string for the LLM
    """
    
    if is_code_issue:
        return _get_code_fix_prompt(error_analysis, source_code, file_path)
    else:
        return _get_config_data_fix_prompt(error_analysis, error_type)


def _get_code_fix_prompt(error_analysis: dict, source_code: str, file_path: str) -> str:
    """Generate prompt for code fixes."""
    return f"""Generate a code fix for the following error:

## Error Analysis
- Root Cause: {error_analysis.get('root_cause', 'Unknown')}
- Suggested Approach: {error_analysis.get('suggested_approach', 'Unknown')}
- Affected Function: {error_analysis.get('affected_function', 'Unknown')}

## Source File: {file_path}
```cpp
{source_code}
```

## Required Output

Generate the fix in the following JSON format:
```json
{{
    "title": "Brief title for the fix (max 60 chars)",
    "description": "Detailed description of what the fix does and why",
    "risk_level": "low, medium, or high",
    "confidence": 0.0 to 1.0,
    "code_changes": [
        {{
            "file_path": "{file_path}",
            "line_start": <starting line number>,
            "line_end": <ending line number>,
            "original_code": "The exact code to be replaced (copy from source)",
            "new_code": "The replacement code with the fix",
            "explanation": "Why this change fixes the issue"
        }}
    ],
    "manual_instructions": "Any manual steps needed (or null if none)"
}}
```

Guidelines:
1. Make minimal changes - only fix what's broken
2. Add proper error handling and validation
3. Match the existing code style
4. Include comments explaining the fix

Respond ONLY with the JSON, no additional text.
"""


def _get_config_data_fix_prompt(error_analysis: dict, error_type: str) -> str:
    """Generate prompt for configuration/data fixes."""
    return f"""Generate a configuration or data fix for the following error:

## Error Analysis
- Error Type: {error_type}
- Root Cause: {error_analysis.get('root_cause', 'Unknown')}
- Suggested Approach: {error_analysis.get('suggested_approach', 'Unknown')}

## Required Output

Generate the fix in the following JSON format:
```json
{{
    "title": "Brief title for the fix (max 60 chars)",
    "description": "Detailed description of what needs to be done",
    "risk_level": "low, medium, or high",
    "confidence": 0.0 to 1.0,
    "fix_type": "config_change, data_insert, or data_update",
    "config_changes": {{
        "key": "value to add or modify"
    }},
    "data_operations": [
        "SQL or Redis command to execute"
    ],
    "manual_instructions": "Steps to apply this fix manually"
}}
```

Guidelines:
1. Be specific about the exact configuration keys or table/cache names
2. Provide complete SQL/Redis commands that can be executed directly
3. Include verification steps in manual_instructions

Respond ONLY with the JSON, no additional text.
"""
