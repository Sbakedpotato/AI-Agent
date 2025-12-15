# AI Log Analyzer Agent

An AI-powered agent that analyzes C++ payment switch logs, identifies errors, determines root causes, and proposes fixes with optional GitHub PR creation.

## Features

- 🔍 **Intelligent Error Analysis** - Uses LLM (Groq/Gemini) to analyze errors and classify them
- 📊 **Error Grouping** - Groups related errors by source file and function for holistic analysis
- 🎯 **Smart Classification** - Distinguishes between code bugs vs config/data issues
- 🔧 **Fix Proposals** - Generates code changes, config updates, or data operations
- 🚀 **GitHub Integration** - Creates PRs for code fixes with one click
- 💻 **Rich CLI** - Interactive command-line interface with beautiful output

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Run analysis
python -m agent.main analyze "path/to/logfile.o"
```

## Configuration

Create a `.env` file with:

```env
# LLM Provider (groq recommended - free tier)
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key

# Optional: Gemini (alternative)
# LLM_PROVIDER=gemini
# GOOGLE_API_KEY=your_gemini_api_key

# GitHub (for PR creation)
GITHUB_TOKEN=your_github_token
GITHUB_REPO=owner/repo
```

## Commands

```bash
# Interactive analysis (default)
python -m agent.main analyze "logfile.o"

# Batch mode - just list errors
python -m agent.main analyze "logfile.o" --batch

# Dry run - analyze without creating PRs
python -m agent.main analyze "logfile.o" --dry-run

# Show configuration
python -m agent.main config

# Interactive setup wizard
python -m agent.main setup
```

## Error Types Detected

| Type | Description |
|------|-------------|
| `code_bug` | Logic error in source code |
| `string_handling` | String operation errors (substr, empty access) |
| `null_pointer` | Missing null/empty checks |
| `missing_config` | Configuration parameter not found or invalid |
| `missing_data` | Database/cache record not found |
| `database_error` | Database operation failures |
| `cache_error` | Redis/cache operation failures |
| `external_service` | External service or library failure |

## Architecture

```
agent/
├── main.py              # CLI interface
├── graph.py             # LangGraph state machine
├── models/              # Data models
│   ├── log_entry.py     # Parsed log entry
│   ├── error_report.py  # Error analysis result
│   └── fix_proposal.py  # Proposed fix
├── nodes/               # LangGraph nodes
│   ├── log_parser.py    # Log parsing & grouping
│   ├── error_analyzer.py# LLM error analysis
│   ├── fix_generator.py # Fix proposal generation
│   └── github_integration.py # PR creation
├── prompts/             # LLM prompts
└── utils/               # Configuration
```

## License

MIT
