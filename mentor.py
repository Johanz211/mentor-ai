#!/usr/bin/env python3
"""
Mentor AI — Your personal learning companion powered by local LLM.

Usage:
    mentor              # Start web UI (default)
    mentor web          # Start web UI on port 8888
    mentor cli          # Interactive terminal chat
    mentor cli --mentor embedded
    mentor web --port 9000
"""

import sys
import os
import argparse

# Ensure the project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(
        description="Mentor AI — Personal learning companion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mentor              Start web UI at http://localhost:8888
  mentor cli          Terminal chat mode
  mentor cli -m qa    Start QA mentor directly
  mentor web -p 9000  Web UI on custom port
        """,
    )
    parser.add_argument(
        "mode", nargs="?", default="web", choices=["web", "cli"],
        help="'web' for browser UI (default), 'cli' for terminal chat",
    )
    parser.add_argument("-p", "--port", type=int, default=8888, help="Port for web server (default: 8888)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("-m", "--mentor", type=str, default=None, help="Mentor: embedded, qa, leetcode, mechanical")
    parser.add_argument("--model", type=str, default=None, help="Override Ollama model name")

    args = parser.parse_args()

    if args.model:
        os.environ["OLLAMA_MODEL"] = args.model

    if args.mode == "cli":
        from app.cli import run_cli
        run_cli(mentor=args.mentor)
    else:
        import uvicorn

        model = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
        print()
        print("  ┌─────────────────────────────────────────────┐")
        print("  │           🎓  Mentor AI                     │")
        print("  │                                             │")
        print(f"  │   Local:   http://localhost:{args.port}            │")
        print(f"  │   Network: http://0.0.0.0:{args.port}             │")
        print(f"  │   Model:   {model:<33}│")
        print("  │                                             │")
        print("  │   Press Ctrl+C to stop                      │")
        print("  └─────────────────────────────────────────────┘")
        print()

        uvicorn.run("app.server:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
