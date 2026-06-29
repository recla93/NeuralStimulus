"""Neuron v3.1 — Interactive chat.

Usage:
  python run_interactive.py
  python run_interactive.py --provider ollama
  python run_interactive.py --provider openai --api-key sk-...
  python run_interactive.py --provider azure --azure-endpoint https://xxx.openai.azure.com --api-key sk-...
  python run_interactive.py --provider compatible --base-url http://localhost:1234/v1
"""

import argparse
import json
import os
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from neuron.engine import (
    create_local,
    create_openai,
    create_anthropic,
    create_gemini,
    create_azure,
    create_compatible,
)

CONFIG_DIR = Path.home() / ".neuron"
CONFIG_FILE = CONFIG_DIR / "config.json"

PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "ollama": {"model": "qwen2.5:14b", "fast_model": "qwen2.5:3b"},
    "openai": {"model": "gpt-4o", "fast_model": "gpt-4o-mini"},
    "anthropic": {"model": "claude-sonnet-4-5", "fast_model": "claude-haiku-3-5-20241022"},
    "gemini": {"model": "gemini-2.5-pro", "fast_model": "gemini-2.0-flash-lite"},
    "azure": {"model": "gpt-4o", "fast_model": "gpt-4o-mini"},
    "compatible": {"model": "mistral", "fast_model": None},
}

PROVIDER_ENV_KEYS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Config salvata in {CONFIG_FILE}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Neuron chat interattiva v3.1")
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "anthropic", "gemini", "azure", "compatible"],
        default="ollama",
        help="Provider LLM (default: ollama)",
    )
    parser.add_argument("--api-key", help="API key (non necessaria per Ollama)")
    parser.add_argument(
        "--azure-endpoint",
        help="Endpoint Azure OpenAI (es. https://tizio-caio-sempronio.openai.azure.com)",
    )
    parser.add_argument(
        "--azure-api-version",
        default="2024-10-21",
        help="Versione API Azure OpenAI (default: 2024-10-21)",
    )
    parser.add_argument(
        "--base-url",
        help="URL base per provider compatible (es. http://localhost:1234/v1)",
    )
    parser.add_argument("--model", help="Modello principale")
    parser.add_argument("--fast-model", help="Modello leggero per estrazione")
    parser.add_argument("--dedup", action="store_true", help="Deduplica keyword")
    parser.add_argument(
        "--summary-every", type=int, default=0, help="Riassunto ogni N turni (0=off)"
    )
    parser.add_argument(
        "--db-path", default="graph.db", help="File SQLite per persistenza (default: graph.db)"
    )
    parser.add_argument(
        "--save-config",
        action="store_true",
        help="Salva i parametri correnti come default in ~/.neuron/config.json",
    )
    return parser.parse_args()


def resolve_key(provider: str, api_key: str | None) -> str | None:
    if api_key:
        return api_key
    env_var = PROVIDER_ENV_KEYS.get(provider)
    if env_var and env_var in os.environ:
        return os.environ[env_var]
    return api_key


def build_ns(args: argparse.Namespace):
    cfg = load_config()
    provider = args.provider or cfg.get("provider", "ollama")
    defaults = PROVIDER_DEFAULTS.get(provider, {})

    kwargs = {
        "deduplicate_keywords": args.dedup if args.dedup else cfg.get("dedup", False),
        "periodic_summary_every": args.summary_every or cfg.get("summary_every", 0),
        "db_path": args.db_path or cfg.get("db_path", "graph.db"),
    }

    model = args.model or cfg.get("model") or defaults.get("model")
    fast_model = args.fast_model or cfg.get("fast_model") or defaults.get("fast_model")

    if provider == "ollama":
        return create_local(model=model, fast_model=fast_model, **kwargs)

    api_key = resolve_key(provider, args.api_key)

    if provider == "openai":
        if not api_key:
            print("ERROR: --api-key o variabile d'ambiente OPENAI_API_KEY richiesto per provider openai")
            sys.exit(1)
        return create_openai(api_key=api_key, model=model, fast_model=fast_model, **kwargs)

    if provider == "anthropic":
        if not api_key:
            print("ERROR: --api-key o variabile d'ambiente ANTHROPIC_API_KEY richiesto")
            sys.exit(1)
        return create_anthropic(api_key=api_key, model=model, fast_model=fast_model, **kwargs)

    if provider == "gemini":
        if not api_key:
            print("ERROR: --api-key o variabile d'ambiente GEMINI_API_KEY richiesto")
            sys.exit(1)
        return create_gemini(api_key=api_key, model=model, fast_model=fast_model, **kwargs)

    if provider == "azure":
        if not api_key:
            print("ERROR: --api-key o AZURE_OPENAI_API_KEY richiesto per Azure OpenAI")
            sys.exit(1)
        azure_endpoint = args.azure_endpoint or cfg.get("azure_endpoint")
        if not azure_endpoint:
            print("ERROR: --azure-endpoint richiesto per provider azure")
            sys.exit(1)
        return create_azure(
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=args.azure_api_version or cfg.get("azure_api_version", "2024-10-21"),
            model=model,
            fast_model=fast_model,
            **kwargs,
        )

    if provider == "compatible":
        base_url = args.base_url or cfg.get("base_url")
        if not base_url:
            print("ERROR: --base-url richiesto per provider compatible")
            sys.exit(1)
        return create_compatible(
            base_url=base_url,
            model=model,
            api_key=api_key or "not-needed",
            fast_model=fast_model,
            **kwargs,
        )

    print(f"ERROR: provider sconosciuto '{provider}'")
    sys.exit(1)


def main():
    args = parse_args()

    if args.save_config:
        cfg = {
            "provider": args.provider,
            "model": args.model,
            "fast_model": args.fast_model,
            "dedup": args.dedup,
            "summary_every": args.summary_every,
            "db_path": args.db_path,
        }
        if args.azure_endpoint:
            cfg["azure_endpoint"] = args.azure_endpoint
            cfg["azure_api_version"] = args.azure_api_version
        if args.base_url:
            cfg["base_url"] = args.base_url
        save_config(cfg)
        return

    ns = build_ns(args)

    print(f"\n  Neuron v3.1 — provider: {args.provider or load_config().get('provider', 'ollama')}")
    print(f"  Comandi: /neuron status | /neuron summary | /neuron prune | /neuron flash | /neuron export | /neuron reset")
    print(f"  Esci: Ctrl+C o /exit\n")

    try:
        while True:
            user_input = input(">>> ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("/exit", "/quit"):
                break
            response = ns.chat(user_input)
            print(response)
            print()
    except (KeyboardInterrupt, EOFError):
        print("\nArrivederci!")
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
