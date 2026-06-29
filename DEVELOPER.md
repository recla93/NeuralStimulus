# Developer Guide — Neuron

## Table of Contents

- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Dependencies](#dependencies)
- [Vector Embeddings](#vector-embeddings)
- [Fallback Chain](#fallback-chain)
- [MCP Client Configuration](#mcp-client-configuration)
- [Interactive CLI Mode](#interactive-cli-mode)
- [Development Setup](#development-setup)
- [CI/CD](#cicd)
- [License](#license)

---

## Architecture

```
YOUR MCP CLIENT (OpenCode, Claude Desktop, Cursor, etc.)
     │  calls MCP tools (stdin/stdout)
     ▼
┌──────────────────────────────────────────────────────────┐
│  mcp_server.py  (Python)                                 │
│  ├── 14 MCP tools                                         │
│  ├── vector embedding (384-dim semantic)                   │
│  └── search: Turso vector_distance_cos() or Python        │
└────────────────────────────────┬─────────────────────────┘
                                 ▼
┌────────────────────────────────┬─────────────────────────┐
│  Turso Database (pyturso) — native vector search          │
│  ├── graph.db (nodes, links, embedding vectors)           │
│  ├── vector_distance_cos() inside Turso                   │
│  └── Python fallback (cosine similarity in memory)        │
└───────────────────────────────────────────────────────────┘
```

The MCP server runs as a **stdio subprocess** of the MCP client. It has no HTTP layer, no daemon, no background process — every LLM tool call starts the server, processes the request, and waits for the next one.

## Project Structure

```
Neuron/
├── src/
│   └── neuron/
│       ├── __init__.py        # Package init, version
│       ├── __main__.py        # `python -m neuron` entry point
│       ├── engine.py          # Engine: graph CRUD, embedding, LLM clients
│       └── server.py          # MCP server (14 tools, Turso/SQLite)
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_server.py         # Smoke tests
├── scripts/
│   ├── run_interactive.py     # Interactive CLI chat (6 LLM providers)
│   ├── run_mcp.bat            # Windows MCP stdio launcher
│   ├── check.ps1              # Dependency check + repair
│   ├── neuron-summary.ps1     # Terminal graph summary
│   └── neuron_summary_query.py
├── skills/
│   ├── SKILL_base.md          # Minimal LLM instructions
│   ├── SKILL_full.md          # Full LLM instructions
│   └── auto-context.md        # Auto-context priming
├── install.ps1                # Windows installer
├── pyproject.toml
├── opencode.example.json
├── README.md
├── DEVELOPER.md
├── LICENSE
├── .gitignore
└── .github/workflows/ci.yml
```

## Dependencies

| Package | Required | Purpose |
|---|---|---|
| `mcp>=1.28.0` | yes | MCP SDK |
| `fastembed>=0.5.0` | yes | 384-dim semantic embedding |
| `pyturso>=0.6.1` | yes | Turso DB engine (vector_distance_cos) |
| `ollama` | no | LLM provider for chat mode |
| `openai` | no | LLM provider for chat mode |
| `anthropic` | no | LLM provider for chat mode |
| `google-generativeai` | no | LLM provider for chat mode |

The MCP server runs with only the first 3. The LLM providers are only for `run_interactive.py`.

## Vector Embeddings

384-dim semantic embeddings via `fastembed` (sentence-transformers/all-MiniLM-L6-v2, ONNX runtime ~80MB model).
Downloaded on first `import`.

```python
from fastembed import TextEmbedding
embedder = TextEmbedding()
vec = list(embedder.embed("database"))[0]  # 384-dim float32
```

## Fallback Chain

### Installer

| Component | URL 1 | URL 2 | URL 3 | Final |
|---|---|---|---|---|
| `rustup-init.exe` | `win.rustup.rs` | `static.rust-lang.org` | GitHub raw | exit 1 |
| Windows SDK | `fwlink/2120843` | Microsoft mirror | — | skip |
| MSVC Build Tools | `aka.ms/vs/17/release` | Microsoft mirror | — | 3 tries → GNU MinGW |
| GNU fallback | — | — | — | exit 1 if GNU fails |
| pip (mcp, fastembed, pyturso) | PyPI (3 retries) | — | — | exit 1 |

### Runtime (`mcp_server.py`)

| Component | Primary | Fallback |
|---|---|---|
| Embedding | fastembed 384-dim | — |
| Database | pyturso (Turso) | sqlite3 (no vector search) |
| Vector search | `vector_distance_cos()` SQL | Python cosine in memory |

## MCP Client Configuration

### OpenCode

```json
{
  "mcp": {
    "neuron": {
      "command": ["cmd", "/c", "%LOCALAPPDATA%\\Programs\\neuron\\scripts\\run_mcp.bat"],
      "type": "local"
    }
  }
}
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "neuron": {
      "command": "cmd",
      "args": ["/c", "%LOCALAPPDATA%\\Programs\\neuron\\scripts\\run_mcp.bat"]
    }
  }
}
```

### Claude Code (`.mcp.json` or `~/.claude.json`)

```json
{
  "mcpServers": {
    "neuron": {
      "command": "python3",
      "args": ["-m", "neuron"]
    }
  }
}
```

### Cursor (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "neuron": {
      "command": "python3",
      "args": ["-m", "neuron"]
    }
  }
}
```

### Cline / Roocode (`~/.vscode/globalStorage/.../mcp_config.json`)

```json
{
  "mcpServers": {
    "neuron": {
      "command": "python3",
      "args": ["-m", "neuron"]
    }
  }
}
```

### VS Code (Copilot)

In `.vscode/settings.json`:

```json
{
  "github.copilot.mcpServers": {
    "neuron": {
      "command": "python3",
      "args": ["-m", "neuron"]
    }
  }
}
```

### Windsurf (`~/.codeium/windsurf/mcp_config.json`)

```json
{
  "mcpServers": {
    "neuron": {
      "command": "python3",
      "args": ["-m", "neuron"]
    }
  }
}
```

### Zed (`~/.config/zed/settings.json`)

```json
{
  "mcp_servers": {
    "neuron": {
      "command": "python3",
      "args": ["-m", "neuron"]
    }
  }
}
```

### Continue.dev (`~/.continue/config.json`)

```json
{
  "experimental": {
    "mcpServers": {
      "neuron": {
        "command": "python3",
        "args": ["-m", "neuron"]
      }
    }
  }
}
```

### Cody (`~/.cody/mcp.json`)

```json
{
  "mcpServers": {
    "neuron": {
      "command": "python3",
      "args": ["-m", "neuron"]
    }
  }
}
```

### Amazon Q Developer (`~/.aws/amazon-q/mcp.json`)

```json
{
  "mcpServers": {
    "neuron": {
      "command": "python3",
      "args": ["-m", "neuron"]
    }
  }
}
```

### Config by client reference

| Client | Config file | Server key | Restart |
|---|---|---|---|
| **OpenCode** | `~/.config/opencode/opencode.json` | `mcp` | `/mcp reload` |
| **Claude Code** | `.mcp.json` or `~/.claude.json` | `mcpServers` | `/mcp` or restart |
| **Claude Desktop** | `claude_desktop_config.json` | `mcpServers` | app restart |
| **Cursor** | `~/.cursor/mcp.json` | `mcpServers` | app restart |
| **Cline / Roocode** | VS Code global storage | `mcpServers` | app restart |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` | `mcpServers` | app restart |
| **VS Code (Copilot)** | `.vscode/settings.json` | `github.copilot.mcpServers` | app restart |
| **Zed** | `~/.config/zed/settings.json` | `mcp_servers` | project restart |
| **Continue.dev** | `~/.continue/config.json` | `experimental.mcpServers` | IDE restart |
| **Cody** | `~/.cody/mcp.json` | `mcpServers` | IDE restart |
| **Amazon Q** | `~/.aws/amazon-q/mcp.json` | `mcpServers` | IDE restart |

On Linux/macOS, replace `cmd /c %LOCALAPPDATA%...` with `python3 -m neuron`.

---

## Interactive CLI Mode

Neuron includes a standalone chat mode (`run_interactive.py`) that connects directly to an LLM.
This is separate from the MCP server — it exists for testing and terminal use.

### Supported Providers

| Provider | Package | Flag | Default model | Fast model |
|---|---|---|---|---|
| **Ollama** (local) | `ollama` | `--provider ollama` | `qwen2.5:14b` | `qwen2.5:3b` |
| **OpenAI** | `openai` | `--provider openai` | `gpt-4o` | `gpt-4o-mini` |
| **Azure OpenAI** | `openai` | `--provider azure` | `gpt-4o` | `gpt-4o-mini` |
| **Anthropic** | `anthropic` | `--provider anthropic` | `claude-sonnet-4-5` | `claude-haiku-3-5` |
| **Gemini** | `google-generativeai` | `--provider gemini` | `gemini-2.5-pro` | `gemini-2.0-flash-lite` |
| **Compatible** | `openai` | `--provider compatible --base-url ...` | `mistral` | same as main |

### Provider CLI

```bash
# Ollama (locale, nessuna API key)
python scripts/run_interactive.py --provider ollama

# OpenAI
python scripts/run_interactive.py --provider openai --api-key sk-...

# Anthropic Claude
python scripts/run_interactive.py --provider anthropic --api-key sk-ant-...

# Compatible (LM Studio, Groq, Perplexity, DeepSeek, vLLM, LiteLLM...)
python scripts/run_interactive.py --provider compatible --base-url http://localhost:1234/v1
```

### API Key Resolution

Keys are resolved in this order (see `resolve_key()` in `run_interactive.py`):

1. `--api-key` CLI argument
2. Environment variable (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `AZURE_OPENAI_API_KEY`)
3. `~/.neuron/config.json` (saved with `--save-config`)

### In-Chat Commands

| Command | Action |
|---|---|
| `/neuron status` | Graph state |
| `/neuron summary` | Graph summary |
| `/neuron prune` | Prune tangential links |
| `/neuron flash` | Toggle semantic flashbacks |
| `/neuron export` | Export graph as JSON |
| `/neuron reset` | Clear graph |
| `/exit` or Ctrl+C | Exit |

---

## Development Setup

```bash
git clone https://github.com/<your-user>/Neuron.git
cd Neuron
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
```

### Available commands

```bash
python -m neuron                      # Start MCP server (stdio)
python scripts/run_interactive.py     # Start interactive chat
python scripts/run_interactive.py --provider ollama  # Chat with local LLM
```

### Verify syntax

```bash
python -m compileall src/
```

## CI/CD

GitHub Actions workflow in `.github/workflows/ci.yml`:

```yaml
on: [push, pull_request]
jobs:
  check:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install mcp fastembed pyturso
      - run: python -m compileall src/
      - run: python -c "import mcp; import turso; from fastembed import TextEmbedding; print('OK')"
```

On PR: verifies syntax + imports on Windows. Linux/macOS can be added per contributor request.

## License

PolyForm Noncommercial License 1.0.0. See [LICENSE](LICENSE).
