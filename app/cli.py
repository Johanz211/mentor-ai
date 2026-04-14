"""CLI chat mode for Mentor AI."""

import sys
import os
import json
import httpx
from .mentors import MENTORS
from . import db

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")


def select_mentor():
    """Interactive mentor selection."""
    print("\n🎓 Choose your mentor:\n")
    keys = list(MENTORS.keys())
    for i, key in enumerate(keys, 1):
        m = MENTORS[key]
        print(f"  {i}. {m['icon']}  {m['name']}")
        print(f"     {m['description']}\n")

    while True:
        try:
            choice = input("  Enter number (or name): ").strip()
            if choice.lower() in MENTORS:
                return choice.lower()
            idx = int(choice) - 1
            if 0 <= idx < len(keys):
                return keys[idx]
        except (ValueError, KeyboardInterrupt):
            print()
            sys.exit(0)
        print("  Invalid choice, try again.\n")


def format_size(n):
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


def run_cli(mentor=None):
    """Run the interactive CLI chat."""
    if mentor is None or mentor not in MENTORS:
        mentor = select_mentor()

    m = MENTORS[mentor]
    print(f"\n{'═' * 60}")
    print(f"  {m['icon']}  {m['name']} Mentor")
    print(f"  Model: {OLLAMA_MODEL}")
    print(f"{'═' * 60}")
    print(f"  Commands: /quit  /clear  /switch  /file <path>")

    # Load persisted history
    history = db.get_history(mentor, limit=200)
    if history:
        count = db.get_message_count(mentor)
        print(f"  📜 Restored {count} messages from previous session")
    print(f"  Ask anything — I'll teach you step by step.\n")

    system_prompt = m["system_prompt"]
    loaded_files = {}

    while True:
        try:
            user_input = input("  You ❯ ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  👋 See you next time!")
            break

        if not user_input:
            continue

        # Commands
        if user_input.startswith("/"):
            cmd = user_input.split()[0].lower()
            if cmd in ("/quit", "/exit", "/q"):
                print("\n  👋 See you next time!")
                break
            elif cmd == "/clear":
                db.clear_history(mentor)
                history = []
                print("  🗑️  Chat cleared!\n")
                continue
            elif cmd == "/switch":
                mentor = select_mentor()
                m = MENTORS[mentor]
                system_prompt = m["system_prompt"]
                history = db.get_history(mentor, limit=200)
                loaded_files = {}
                count = len(history)
                print(f"\n  Switched to {m['icon']}  {m['name']}")
                if count:
                    print(f"  📜 Restored {count} messages")
                print()
                continue
            elif cmd == "/file":
                path = user_input[5:].strip()
                if not path:
                    print("  Usage: /file <path>")
                    if loaded_files:
                        print("  Loaded files:")
                        for name in loaded_files:
                            print(f"    📄 {name}")
                    print()
                    continue
                path = os.path.expanduser(path)
                if not os.path.isfile(path):
                    print(f"  ❌ File not found: {path}\n")
                    continue
                try:
                    with open(path, "rb") as f:
                        content = f.read()
                    from .file_parser import parse_file
                    text = parse_file(os.path.basename(path), content)
                    loaded_files[os.path.basename(path)] = text[:6000]
                    print(f"  📄 Loaded: {os.path.basename(path)} ({format_size(len(content))})\n")
                except Exception as e:
                    print(f"  ❌ Error reading file: {e}\n")
                continue
            elif cmd == "/files":
                if loaded_files:
                    print("  Loaded files:")
                    for name in loaded_files:
                        print(f"    📄 {name}")
                else:
                    print("  No files loaded. Use /file <path> to add one.")
                print()
                continue
            else:
                print(f"  Unknown command: {cmd}\n")
                continue

        # Build context with files
        full_system = system_prompt
        if loaded_files:
            full_system += "\n\n--- REFERENCE FILES ---\n"
            for name, content in loaded_files.items():
                full_system += f"\n### File: {name}\n```\n{content}\n```\n"

        history.append({"role": "user", "content": user_input})
        db.save_message(mentor, "user", user_input)
        messages = [{"role": "system", "content": full_system}] + history[-20:]

        print(f"\n  {m['icon']}  ", end="", flush=True)

        try:
            response_text = ""
            with httpx.Client(timeout=120) as client:
                with client.stream(
                    "POST",
                    f"{OLLAMA_URL}/api/chat",
                    json={"model": OLLAMA_MODEL, "messages": messages, "stream": True},
                ) as resp:
                    for line in resp.iter_lines():
                        if line:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                print(token, end="", flush=True)
                                response_text += token

            print("\n")
            history.append({"role": "assistant", "content": response_text})
            db.save_message(mentor, "assistant", response_text)

        except httpx.ConnectError:
            print(f"\n  ❌ Cannot connect to Ollama at {OLLAMA_URL}")
            print(f"     Make sure Ollama is running: ollama serve\n")
            history.pop()
            # Remove the saved user message since it failed
            db.clear_history(mentor)
            for msg in history:
                db.save_message(mentor, msg["role"], msg["content"])
        except Exception as e:
            print(f"\n  ❌ Error: {e}\n")
            history.pop()
