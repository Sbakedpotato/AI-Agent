"""
LangGraph State Machine for the Log Analyzer Agent.

Defines the graph structure with nodes and edges for
processing logs, analyzing errors, and creating fixes.
"""

from typing import Annotated, Any, TypedDict, Literal
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from .nodes.log_parser import parse_logs_node
from .nodes.error_analyzer import analyze_error_node
from .nodes.fix_generator import generate_fix_node
from .nodes.github_integration import create_pr_node
from .models.log_entry import LogEntry
from .models.error_report import ErrorReport
from .models.fix_proposal import FixProposal


class AgentState(TypedDict, total=False):
    """
    State for the Log Analyzer Agent graph.
    
    This state flows through all nodes and accumulates
    information as processing progresses.
    """
    # Input - either log content or file path
    log_content: str                    # Pre-filtered log content (primary input)
    log_file_path: str                  # Alternative: path to log file
    
    # Configuration
    source_dir: str                     # Path to C++ source files
    repo_root: str                      # Path to repository root
    
    # Parsed data
    log_entries: list[LogEntry]         # All parsed log entries
    error_entries: list[LogEntry]       # Only ERROR/CRITICAL entries
    
    # Processing state
    current_error_index: int            # Index of error being processed
    total_errors: int                   # Total number of errors found
    
    # Analysis results
    current_error_report: ErrorReport | None   # Analysis of current error
    fix_proposal: FixProposal | None           # Generated fix
    
    # Human-in-the-loop
    user_approved: bool                 # Whether user approved the fix
    user_feedback: str                  # Optional user feedback
    
    # GitHub output
    pr_url: str | None                  # URL of created PR
    pr_created: bool                    # Whether PR was created
    pr_error: str | None                # Error message if PR failed
    
    # Control flow
    analysis_complete: bool             # All errors processed
    should_continue: bool               # Continue to next error
    
    # LLM instance (cached)
    llm: Any                            # ChatGoogleGenerativeAI instance


def should_continue_processing(state: AgentState) -> Literal["analyze", "done"]:
    """
    Determine if there are more errors to process.
    """
    index = state.get("current_error_index", 0)
    total = state.get("total_errors", 0)
    
    if index < total:
        return "analyze"
    return "done"


def should_create_pr(state: AgentState) -> Literal["create_pr", "skip_pr", "next_error"]:
    """
    Determine if we should create a PR based on user approval.
    """
    if not state.get("user_approved", False):
        return "next_error"
    
    fix = state.get("fix_proposal")
    if fix is None or not fix.requires_pr:
        return "skip_pr"
    
    return "create_pr"


def advance_to_next_error(state: AgentState) -> AgentState:
    """
    Node to advance to the next error in the list.
    """
    current_index = state.get("current_error_index", 0)
    return {
        **state,
        "current_error_index": current_index + 1,
        "current_error_report": None,
        "fix_proposal": None,
        "user_approved": False,
        "pr_url": None,
        "pr_created": False,
        "pr_error": None
    }


def create_agent_graph() -> StateGraph:
    """
    Create the LangGraph state machine for the log analyzer agent.
    
    Graph structure:
    
    START -> parse_logs -> check_errors -> analyze_error -> generate_fix
                              |                                    |
                              v                                    v
                             END                        [INTERRUPT: user confirms]
                                                                   |
                                          +------------------------+------------------------+
                                          |                        |                        |
                                          v                        v                        v
                                     create_pr              skip_pr                   next_error
                                          |                        |                        |
                                          +------------------------+------------------------+
                                                                   |
                                                                   v
                                                           advance_error
                                                                   |
                                                                   v
                                                           check_errors (loop)
    """
    # Create the graph
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("parse_logs", parse_logs_node)
    graph.add_node("analyze_error", analyze_error_node)
    graph.add_node("generate_fix", generate_fix_node)
    graph.add_node("create_pr", create_pr_node)
    graph.add_node("advance_error", advance_to_next_error)
    
    # Define edges
    graph.set_entry_point("parse_logs")
    
    # After parsing, check if there are errors
    graph.add_conditional_edges(
        "parse_logs",
        should_continue_processing,
        {
            "analyze": "analyze_error",
            "done": END
        }
    )
    
    # After analysis, generate fix
    graph.add_edge("analyze_error", "generate_fix")
    
    # After fix generation, we interrupt for user confirmation
    # The CLI will handle the interrupt and set user_approved
    # Then resume with conditional routing
    graph.add_conditional_edges(
        "generate_fix",
        should_create_pr,
        {
            "create_pr": "create_pr",
            "skip_pr": "advance_error",
            "next_error": "advance_error"
        }
    )
    
    # After PR creation, advance to next error
    graph.add_edge("create_pr", "advance_error")
    
    # After advancing, check if more errors
    graph.add_conditional_edges(
        "advance_error",
        should_continue_processing,
        {
            "analyze": "analyze_error",
            "done": END
        }
    )
    
    return graph


def compile_agent():
    """
    Compile the agent graph for execution.
    
    Returns:
        Compiled LangGraph that can be invoked
    """
    graph = create_agent_graph()
    return graph.compile(
        # Interrupt after generate_fix for human confirmation
        interrupt_after=["generate_fix"]
    )


def run_agent_single_error(
    log_content: str,
    source_dir: str,
    repo_root: str
) -> tuple[AgentState, Any]:
    """
    Run the agent for a single error (first error in logs).
    
    This is a convenience function for processing one error at a time.
    
    Args:
        log_content: Pre-filtered log content
        source_dir: Path to source files
        repo_root: Path to repository root
    
    Returns:
        Tuple of (final state, compiled graph for resuming)
    """
    agent = compile_agent()
    
    initial_state = AgentState(
        log_content=log_content,
        source_dir=source_dir,
        repo_root=repo_root,
        current_error_index=0,
        user_approved=False,
        should_continue=True
    )
    
    # Run until interrupt (after generate_fix)
    result = agent.invoke(initial_state)
    
    return result, agent
