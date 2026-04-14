# Mentor AI

Your personal learning companion powered by a local LLM (Ollama).

Four built-in mentors — customizable and extensible:
- 🔌 **Embedded Systems & EE** — C, STM32, ARM, RTOS, CAN, circuits
- 🧪 **QA & Test Automation** — Selenium, CI/CD, API testing, strategy
- 💻 **LeetCode & DSA** — Algorithms, patterns, interview prep
- ⚙️ **Mechanical Engineering** — Thermodynamics, materials, CAD, design

## Features

- **Web UI** — Chat interface with mentor selection, file uploads, markdown + code highlighting
- **CLI mode** — Interactive terminal chat with streaming responses
- **File context** — Upload code/docs/PDFs; the mentor can read and explain them
- **Streaming** — Real-time token-by-token responses from Ollama
- **Customizable** — Add new mentors by editing `app/mentors.py`

## Quick Start

```bash
# Install
cd mentor-ai
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Web UI (open http://localhost:8888)
mentor

# Terminal chat
mentor cli
mentor cli -m embedded
```

## Requirements

- Python 3.10+
- [Ollama](https://ollama.ai) running locally with a model pulled:
  ```bash
  ollama pull qwen2.5-coder:7b
  ```

## Usage

```bash
mentor              # Web UI on port 8888
mentor web -p 9000  # Web UI on custom port
mentor cli          # Terminal chat (choose mentor interactively)
mentor cli -m qa    # Jump straight to QA mentor
mentor cli -m leetcode --model llama3:8b  # Use different model
```

### CLI Commands (inside chat)

| Command | Action |
|---------|--------|
| `/file <path>` | Load a file for context |
| `/files` | List loaded files |
| `/switch` | Change mentor |
| `/clear` | Reset chat history |
| `/quit` | Exit |

## Adding a New Mentor

Edit `app/mentors.py` and add an entry to the `MENTORS` dict:

```python
"your_mentor": {
    "name": "Display Name",
    "icon": "🎯",
    "description": "Short description for sidebar",
    "system_prompt": "Detailed instructions for the LLM...",
}
```

## Architecture

```
mentor-ai/
├── mentor.py           # Entry point (CLI + web server launcher)
├── app/
│   ├── server.py       # FastAPI backend (chat, files, SSE streaming)
│   ├── cli.py          # Terminal chat mode
│   ├── mentors.py      # Mentor persona definitions
│   ├── file_parser.py  # PDF/DOCX/code file parsing
│   └── static/         # Web UI (HTML/CSS/JS)
├── uploads/            # Uploaded files storage
└── requirements.txt
```
