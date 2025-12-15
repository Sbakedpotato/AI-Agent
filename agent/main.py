"""
CLI Interface for the Log Analyzer Agent.

Provides an interactive command-line interface for analyzing logs,
reviewing fix proposals, and creating GitHub PRs.
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich import print as rprint

from .graph import compile_agent, AgentState
from .nodes.log_parser import parse_log_file, parse_log_content, extract_errors
from .nodes.error_analyzer import analyze_error_sync, create_llm
from .nodes.fix_generator import generate_fix_sync
from .nodes.github_integration import GitHubIntegration, apply_code_change
from .utils.config import get_config, Config
from .models.log_entry import LogEntry
from .models.error_report import ErrorReport
from .models.fix_proposal import FixProposal


# Initialize CLI app
app = typer.Typer(
    name="log-analyzer",
    help="AI-powered log analyzer for C++ payment switch applications"
)
console = Console()


def check_config() -> Config:
    """Check configuration and display any issues."""
    config = get_config()
    missing = config.validate()
    
    if missing:
        console.print("\n[bold red]⚠️ Configuration Issues:[/bold red]")
        for item in missing:
            console.print(f"  [yellow]• {item}[/yellow]")
        console.print("\n[dim]Copy .env.example to .env and fill in the values.[/dim]\n")
    
    return config


def display_error_report(report: ErrorReport) -> None:
    """Display an error report in a nice format."""
    # Create panel for the error
    severity_color = "red" if report.primary_error.is_critical() else "yellow"
    
    content = f"""[bold]File:[/bold] {report.affected_file}:{report.affected_line}
[bold]Function:[/bold] {report.primary_error.function_name}
[bold]Type:[/bold] {report.error_type.value}
[bold]Is Code Issue:[/bold] {"Yes" if report.is_code_issue else "No (Config/Data)"}

[bold]Message:[/bold]
{report.primary_error.message}

[bold]Root Cause:[/bold]
{report.root_cause}

[bold]Suggested Approach:[/bold]
{report.suggested_approach}

[dim]Confidence: {report.confidence:.0%}[/dim]"""
    
    panel = Panel(
        content,
        title=f"[{severity_color}]🔍 Error Analysis[/{severity_color}]",
        border_style=severity_color
    )
    console.print(panel)


def display_fix_proposal(fix: FixProposal) -> None:
    """Display a fix proposal in a nice format."""
    risk_color = {"low": "green", "medium": "yellow", "high": "red"}.get(fix.risk_level, "white")
    
    content = f"""[bold]Type:[/bold] {fix.fix_type.value}
[bold]Risk:[/bold] [{risk_color}]{fix.risk_level}[/{risk_color}]
[bold]Confidence:[/bold] {fix.confidence:.0%}

[bold]Description:[/bold]
{fix.description}
"""
    
    # Show code changes
    if fix.code_changes:
        content += "\n[bold]📝 Code Changes:[/bold]\n"
        for change in fix.code_changes:
            content += f"\n  [cyan]{change.file_path}[/cyan] (lines {change.line_start}-{change.line_end})\n"
            content += f"  [dim]{change.explanation}[/dim]\n"
    
    # Show config/data changes
    if fix.config_changes:
        content += "\n[bold]⚙️ Configuration Changes:[/bold]\n"
        for key, value in fix.config_changes.items():
            content += f"  {key} = {value}\n"
    
    if fix.data_operations:
        content += "\n[bold]🗃️ Data Operations:[/bold]\n"
        for op in fix.data_operations:
            content += f"  {op}\n"
    
    if fix.manual_instructions:
        content += f"\n[bold yellow]⚠️ Manual Steps Required:[/bold yellow]\n{fix.manual_instructions}\n"
    
    panel = Panel(
        content,
        title=f"[blue]💡 Fix Proposal: {fix.title}[/blue]",
        border_style="blue"
    )
    console.print(panel)
    
    # Show code diff if available
    if fix.code_changes:
        for change in fix.code_changes:
            if change.original_code and change.new_code:
                console.print("\n[bold]Original Code:[/bold]")
                syntax = Syntax(change.original_code, "cpp", theme="monokai", line_numbers=True)
                console.print(syntax)
                
                console.print("\n[bold]New Code:[/bold]")
                syntax = Syntax(change.new_code, "cpp", theme="monokai", line_numbers=True)
                console.print(syntax)


def run_interactive_analysis(
    log_content: str,
    source_dir: Path,
    repo_root: Path,
    dry_run: bool = False
) -> None:
    """
    Run interactive analysis on log content.
    
    Analyzes related errors TOGETHER for better context understanding.
    
    Args:
        log_content: Pre-filtered log content to analyze
        source_dir: Path to source files
        repo_root: Path to repository root
        dry_run: If True, don't create PRs
    """
    from .nodes.log_parser import group_errors_by_context, get_full_context_for_group
    
    config = check_config()
    
    if not config.is_configured:
        provider = config.llm_provider.upper()
        console.print(f"[red]Cannot proceed without {provider} API key configured.[/red]")
        return
    
    # Parse logs
    console.print("\n[bold]📋 Parsing logs...[/bold]")
    entries = parse_log_content(log_content)
    errors = extract_errors(entries)
    
    if not errors:
        console.print("[green]✅ No errors found in the logs![/green]")
        return
    
    # Group related errors
    error_groups = group_errors_by_context(entries, errors)
    
    console.print(f"[cyan]Found {len(errors)} error(s) grouped into {len(error_groups)} issue(s) to analyze.[/cyan]")
    console.print(f"[dim]Errors are grouped by source file and function for holistic analysis.[/dim]\n")
    
    # Create LLM instance based on config
    llm = create_llm()
    
    # Process each error GROUP
    for i, error_group in enumerate(error_groups, 1):
        # Get the primary error (first in group) for display
        primary_error = error_group[0]
        
        console.rule(f"[bold]Issue {i}/{len(error_groups)} - {primary_error.source_file}:{primary_error.function_name}[/bold]")
        
        # Show all errors in this group
        console.print(f"\n[bold yellow]📌 {len(error_group)} related error(s) in this group:[/bold yellow]")
        for error in error_group:
            level_color = "red" if error.is_critical() else "yellow"
            console.print(f"  [{level_color}]{error.level}[/{level_color}] {error.source_file}:{error.line_number} - {error.message[:60]}...")
        console.print()
        
        # Get full context (all log entries from affected threads)
        context_entries = get_full_context_for_group(entries, error_group)
        
        console.print(f"[dim]Analyzing with {len(context_entries)} context log entries...[/dim]\n")
        
        # Analyze the PRIMARY error but with ALL context
        with console.status("[bold cyan]Analyzing error group with AI...[/bold cyan]"):
            try:
                # Send all context for better understanding
                report = analyze_error_sync(primary_error, context_entries, source_dir, llm)
                
                # Update the report to mention all related errors
                if len(error_group) > 1:
                    report.root_cause = f"[Group of {len(error_group)} related errors]\n\n{report.root_cause}"
            except Exception as e:
                console.print(f"[red]Error during analysis: {e}[/red]")
                continue
        
        display_error_report(report)
        
        # Generate fix
        with console.status("[bold blue]Generating fix proposal...[/bold blue]"):
            try:
                fix = generate_fix_sync(report, source_dir, llm)
            except Exception as e:
                console.print(f"[red]Error generating fix: {e}[/red]")
                continue
        
        console.print()
        display_fix_proposal(fix)
        
        # Ask for confirmation
        console.print()
        if dry_run:
            console.print("[dim]Dry run mode - skipping PR creation[/dim]")
            if not Confirm.ask("Continue to next issue?", default=True):
                break
            continue
        
        if fix.requires_pr and config.has_github_access:
            if Confirm.ask("[bold]Create a PR with this fix?[/bold]", default=False):
                with console.status("[bold green]Creating GitHub PR...[/bold green]"):
                    try:
                        gh = GitHubIntegration(
                            token=config.github_token,
                            repo_name=config.github_repo,
                            target_branch=config.github_target_branch
                        )
                        
                        from datetime import datetime
                        branch_name = f"fix/auto-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                        gh.create_branch(branch_name)
                        
                        for change in fix.code_changes:
                            file_path = repo_root / change.file_path
                            if file_path.exists():
                                new_content = apply_code_change(file_path, change)
                                gh.update_file(
                                    file_path=change.file_path,
                                    new_content=new_content,
                                    branch=branch_name,
                                    commit_message=f"fix: {change.explanation}"
                                )
                        
                        pr_url = gh.create_pull_request(
                            title=fix.title,
                            body=fix.get_pr_body(),
                            head_branch=branch_name
                        )
                        
                        console.print(f"\n[bold green]✅ PR created successfully![/bold green]")
                        console.print(f"[link={pr_url}]{pr_url}[/link]\n")
                    except Exception as e:
                        console.print(f"[red]Failed to create PR: {e}[/red]")
        else:
            if not fix.requires_pr:
                console.print("[yellow]This fix requires manual steps (not a code change)[/yellow]")
            elif not config.has_github_access:
                console.print("[yellow]GitHub access not configured - cannot create PR[/yellow]")
        
        # Continue to next issue?
        if i < len(error_groups):
            if not Confirm.ask("\nContinue to next issue?", default=True):
                break
    
    console.print("\n[bold green]✅ Analysis complete![/bold green]\n")


@app.command()
def analyze(
    log_input: str = typer.Argument(
        ...,
        help="Path to log file or raw log content"
    ),
    source_dir: str = typer.Option(
        "src",
        "--source", "-s",
        help="Path to C++ source files"
    ),
    repo_root: str = typer.Option(
        ".",
        "--repo", "-r",
        help="Path to repository root"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run", "-d",
        help="Analyze without creating PRs"
    ),
    interactive: bool = typer.Option(
        True,
        "--interactive/--batch", "-i/-b",
        help="Interactive mode (confirm each fix)"
    )
):
    """
    Analyze log files and propose fixes for errors.
    
    The log input can be:
    - A path to a log file (e.g., "logs for reference/log_sample.o")
    - Raw log content (if piped or as a string)
    
    Example:
        python -m agent.main analyze "logs for reference/log_sample.o"
        python -m agent.main analyze "logs for reference/log_sample.o" --dry-run
    """
    console.print(Panel.fit(
        "[bold cyan]🔍 Log Analyzer AI Agent[/bold cyan]\n"
        "[dim]Powered by Google Gemini[/dim]",
        border_style="cyan"
    ))
    
    # Determine if input is file path or content
    log_path = Path(log_input)
    if log_path.exists():
        console.print(f"[dim]Loading log file: {log_path}[/dim]")
        log_content = log_path.read_text(encoding='utf-8', errors='replace')
    else:
        log_content = log_input
    
    source_path = Path(source_dir)
    repo_path = Path(repo_root)
    
    if interactive:
        run_interactive_analysis(log_content, source_path, repo_path, dry_run)
    else:
        # Batch mode - just list errors
        entries = parse_log_content(log_content)
        errors = extract_errors(entries)
        
        if not errors:
            console.print("[green]✅ No errors found![/green]")
            return
        
        table = Table(title=f"Found {len(errors)} Error(s)")
        table.add_column("Level", style="bold")
        table.add_column("File")
        table.add_column("Line")
        table.add_column("Function")
        table.add_column("Message", max_width=50)
        
        for error in errors:
            level_style = "red" if error.is_critical() else "yellow"
            table.add_row(
                f"[{level_style}]{error.level}[/{level_style}]",
                error.source_file,
                str(error.line_number),
                error.function_name,
                error.message[:50] + "..." if len(error.message) > 50 else error.message
            )
        
        console.print(table)


@app.command()
def config():
    """Show current configuration status."""
    cfg = get_config()
    console.print("\n[bold]Current Configuration:[/bold]\n")
    console.print(str(cfg))
    
    missing = cfg.validate()
    if missing:
        console.print("\n[bold red]Missing Configuration:[/bold red]")
        for item in missing:
            console.print(f"  [yellow]• {item}[/yellow]")
    else:
        console.print("\n[bold green]✅ All configuration is set![/bold green]")


@app.command()
def setup():
    """Interactive setup wizard for configuration."""
    console.print(Panel.fit(
        "[bold cyan]⚙️ Configuration Setup[/bold cyan]",
        border_style="cyan"
    ))
    
    env_path = Path(".env")
    example_path = Path(".env.example")
    
    if not env_path.exists() and example_path.exists():
        console.print("\nCreating .env from .env.example...")
        env_path.write_text(example_path.read_text())
    
    console.print("\n[bold]Step 1: Google Gemini API Key[/bold]")
    console.print("Get your free API key from: [link=https://aistudio.google.com/apikey]https://aistudio.google.com/apikey[/link]")
    api_key = Prompt.ask("Enter your Google API Key", password=True)
    
    console.print("\n[bold]Step 2: GitHub Personal Access Token[/bold]")
    console.print("Create at: [link=https://github.com/settings/tokens/new]https://github.com/settings/tokens/new[/link]")
    console.print("[dim]Required scope: 'repo'[/dim]")
    github_token = Prompt.ask("Enter your GitHub Token", password=True)
    
    console.print("\n[bold]Step 3: GitHub Repository[/bold]")
    github_repo = Prompt.ask("Enter repository (owner/repo format)")
    
    # Update .env file
    if env_path.exists():
        content = env_path.read_text()
        content = content.replace("your_gemini_api_key_here", api_key)
        content = content.replace("your_github_token_here", github_token)
        content = content.replace("Sbakedpotato/Dummy-Log-Creation-Code", github_repo)
        env_path.write_text(content)
        console.print("\n[bold green]✅ Configuration saved to .env[/bold green]")
    else:
        console.print("[red]Could not find .env file to update[/red]")


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
