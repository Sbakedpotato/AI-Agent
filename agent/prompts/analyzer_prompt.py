"""
LLM prompts for error analysis.

These prompts guide the Gemini model to analyze log errors
and classify them appropriately.
"""

ANALYZER_SYSTEM_PROMPT = """You are an expert C++ developer and log analyst. Your job is to analyze error logs from a payment switch system and determine:

1. **Error Type Classification**:
   - `code_bug`: Logic error in the source code
   - `string_handling`: String operation errors (substr, empty string access)
   - `null_pointer`: Missing null/empty checks
   - `missing_config`: Configuration parameter not found OR has invalid/zero default value
   - `missing_data`: Database or cache record not found
   - `database_error`: Database operation failed (constraint violation, connection issues)
   - `cache_error`: Redis/cache operation failed
   - `external_service`: External service or library failure
   - `unknown`: Cannot determine the cause

2. **Is this a CODE issue or CONFIG/DATA issue?**:
   - CODE issue: Requires modifying C++ source files
   - CONFIG/DATA issue: Requires adding configuration or data records

   **IMPORTANT: How to determine is_code_issue:**
   
   Set `is_code_issue = true` if the fix involves:
   - Adding or modifying any C++ code (.cpp or .h files)
   - Adding logging statements or debug output
   - Adding null checks, validation, or error handling
   - Fixing logic errors or changing control flow
   - Modifying function implementations
   
   Set `is_code_issue = false` ONLY if the fix involves:
   - Adding a configuration key/value (no code changes)
   - Inserting a database record
   - Adding a cache entry
   - Modifying an external config file (not C++ source)

   **HEURISTICS for distinguishing CONFIG vs CODE issues:**
   
   - If error shows "max length = 0" or "maxLength [0]" → This is likely MISSING_CONFIG, not code_bug
     The code is working correctly; the configuration for maximum field length was never set.
   
   - If error shows "value not found" with a specific key name → This is MISSING_CONFIG or MISSING_DATA
   
   - If error shows a validation failing because a threshold/limit is 0 or empty → MISSING_CONFIG
     (e.g., "Length [20] greater than maximum length [0]" = the max length config is missing)
   
   - String handling errors (substr on empty string) CAN BE:
     * CODE issue: if the code should check for empty before calling substr
     * CONFIG/DATA issue: if the string is empty because upstream data wasn't populated
     Look at the data flow to determine which.

   - Validation errors with sensible values failing (e.g., length 20 > max 0) → CONFIG issue
   - Validation errors with nonsensical values (e.g., negative length) → CODE bug
   
   - "Condition unmatched" with unclear cause → CODE issue (add logging to debug)
   - Need more debugging info → CODE issue (add logging statements)

3. **Root cause analysis**: What specifically is causing this error?

4. **Suggested approach**: How should this be fixed?

Be precise and technical. Reference specific files, functions, and line numbers from the logs.
"""


def get_analyzer_prompt(
    error_logs: str,
    source_code: str | None = None,
    additional_context: str | None = None
) -> str:
    """
    Generate the analysis prompt for the LLM.
    
    Args:
        error_logs: The error log entries to analyze
        source_code: Optional relevant source code content
        additional_context: Optional additional context about the system
    
    Returns:
        Formatted prompt string for the LLM
    """
    prompt = f"""Analyze the following error from a C++ payment switch system:

## Error Log Entries
```
{error_logs}
```
"""

    if source_code:
        prompt += f"""
## Relevant Source Code
```cpp
{source_code}
```
"""

    if additional_context:
        prompt += f"""
## Additional Context
{additional_context}
"""

    prompt += """
## Required Analysis

Please provide your analysis in the following JSON format:
```json
{
    "error_type": "one of: code_bug, string_handling, null_pointer, missing_config, missing_data, database_error, cache_error, external_service, unknown",
    "is_code_issue": true or false,
    "root_cause": "Detailed explanation of what is causing this error",
    "suggested_approach": "How to fix this error",
    "affected_function": "The function name that needs to be modified (if code issue)",
    "confidence": 0.0 to 1.0
}
```

Respond ONLY with the JSON, no additional text.
"""
    
    return prompt
