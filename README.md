# Neuron — Persistent semantic memory for AI

Neuron is an **MCP server** that gives LLMs long-term memory.
It builds a concept graph across conversations: each exchange saves keywords
with vector embeddings and semantic links, retrievable in later sessions.

## Installation

### Windows

```powershell
.\install.ps1
```

The installer handles everything: Python → Rust → Windows SDK + MSVC (C++ tools only)
→ pip (mcp, fastembed, pyturso, 3 retries, hard fail). **fastembed is mandatory** — 384-dim semantic embeddings.

At the end, it asks whether to install packages for the **standalone chat** (`run_interactive.py`).
If you use Neuron only as an MCP server (OpenCode/Claude/Cursor), choose **0 (None)**.

### Linux / macOS

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install mcp pyturso fastembed  # fastembed is mandatory
python -m neuron
```

## MCP Configuration

### OpenCode (`~/.config/opencode/opencode.json`)

```json
{
  "mcp": {
    "neuron": {
      "command": ["cmd", "/c", "%LOCALAPPDATA%\\Programs\\neuron\\scripts\\run_mcp.bat"],
      "type": "local"
    }
  },
  "instructions": [
    "path/to/skills/neural-stimulus/auto-context.md"
  ]
}
```

### Other clients

Claude Desktop, Cursor, Windsurf, VS Code, Zed — see [DEVELOPER.md](DEVELOPER.md#mcp-client-configuration).

## MCP Tools

| Tool | Description |
|---|---|
| `neuron_status` | Graph state |
| `neuron_auto(text)` | Extract, save, return context (recommended) |
| `neuron_get_context(keywords)` | Retrieve related nodes |
| `neuron_vector_search(keywords)` | Semantic vector search |
| `neuron_summary` | Graph summary |
| `neuron_store_turn` | Manually save a turn |
| `neuron_extract(text)` | Standalone semantic extraction |
| `neuron_find_candidates(keywords)` | Find similar keywords (pre-store) |
| `neuron_forgotten` | Concepts not touched in N turns |
| `neuron_prune` | Prune tangential links |
| `neuron_dedup` / `neuron_flash` | Toggle features |
| `neuron_export` / `neuron_reset` | Export / Reset graph |

## API Keys (standalone chat only)

Environment variables for cloud providers:
- `OPENAI_API_KEY` — OpenAI / Azure / Compatible
- `ANTHROPIC_API_KEY` — Claude
- `GEMINI_API_KEY` — Google Gemini

Or save the config with `--save-config`:

```bash
python scripts/run_interactive.py --provider openai --model gpt-4o --save-config
```

## License

PolyForm Noncommercial 1.0.0 — see [LICENSE](LICENSE).
