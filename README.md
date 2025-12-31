---
title: Reachy Mini Pomodoro
emoji: 🍅
colorFrom: red
colorTo: yellow
sdk: static
pinned: false
short_description: Pomodoro productivity timer with Compita voice assistant
tags:
  - reachy_mini
  - reachy_mini_python_app
  - pomodoro
  - productivity
  - compita
---

# Reachy Mini Pomodoro

> **⚠️ Experimental:** This app is under active development. Features may change and bugs may occur. Use at your own risk and feel free to report issues!

A Pomodoro productivity timer app for Reachy Mini robot featuring **Compita**, an AI voice assistant that helps you stay focused and productive.

## Features

- **Compita Voice Assistant**: Talk to your robot companion using natural voice commands
- **Wake Word Detection**: Say "Compita" to activate the assistant
- **Pomodoro Timer**: 25-minute focus sessions with 5-minute short breaks and 15-minute long breaks
- **Task Management**: Create and organize tasks with estimated pomodoro counts, priorities, and tags
- **Robot Expressions**: Reachy Mini provides encouragement and celebrates your progress
- **Break Activities**: Breathing exercises and stretches demonstrated by Reachy during breaks
- **Progress Tracking**: View productivity statistics and session history

## Installation

### From Hugging Face

```bash
pip install git+https://huggingface.co/spaces/adonaivera/reachy_mini_pomodoro
```

### From Source

```bash
git clone https://github.com/AdonaiVera/reachy_mini_pomodoro
cd reachy_mini_pomodoro
pip install -e .
```

### Using uv

```bash
git clone https://github.com/AdonaiVera/reachy_mini_pomodoro
cd reachy_mini_pomodoro
uv venv --python 3.12
source .venv/bin/activate
uv sync
```

## Configuration

### OpenAI API Key (Required for Compita Voice Assistant)

Compita requires an OpenAI API key to enable voice interactions. Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys).

```bash
export OPENAI_API_KEY="sk-your-api-key-here"
```

**Note:** Compita uses OpenAI's Realtime API (`gpt-4o-realtime-preview`) for natural voice conversations. If no API key is configured, the app will still work but without voice assistant features.

## Usage

### Via Reachy Mini Dashboard

Install from the Reachy Mini Dashboard app store, then launch from the dashboard.

### Command Line

**Wireless Robot (Network Connection):**
```bash
python -m reachy_mini_pomodoro --wireless
```

**USB Robot (Local Connection):**
```bash
python -m reachy_mini_pomodoro
```

The web UI will be available at http://localhost:8042

## Compita Voice Commands

Say "Compita" to wake up your assistant, then ask:

| Command | Example |
|---------|---------|
| Check timer | "How much time is left?" |
| Start focus | "Start a focus session" |
| Pause/Resume | "Pause the timer" / "Resume" |
| Skip session | "Skip this session" |
| Start break | "I need a break" |
| Create task | "Add a task called review code" |
| List tasks | "What are my tasks?" |
| Complete task | "Mark this task as done" |
| Get stats | "How productive was I today?" |
| Break activity | "What's the break activity?" |
| Demo activity | "Show me the breathing exercise" |

## Robot Behaviors

| State | Reachy's Behavior |
|-------|-------------------|
| Listening | Subtle nod |
| Speaking | Talking animation (nods and tilts) |
| Focus Start | Wake up animation |
| During Focus | Gentle breathing |
| Focus Complete | Celebration |
| Break Time | Breathing/stretch demo |
| Task Complete | Victory dance |

## API Endpoints

The app exposes a REST API at `http://localhost:8042/api/`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Timer and task status |
| `/api/timer/start` | POST | Start focus session |
| `/api/timer/pause` | POST | Pause timer |
| `/api/timer/resume` | POST | Resume timer |
| `/api/timer/stop` | POST | Stop timer |
| `/api/timer/skip` | POST | Skip current session |
| `/api/timer/break` | POST | Start break |
| `/api/tasks` | GET | List tasks |
| `/api/tasks` | POST | Create task |
| `/api/tasks/{id}/complete` | POST | Complete task |
| `/api/stats` | GET | Productivity statistics |
| `/api/compita/status` | GET | Voice assistant status |
| `/api/compita/stream` | WebSocket | Voice streaming |

## Requirements

- Reachy Mini robot (wireless or USB)
- Python 3.10+
- OpenAI API key (for Compita voice assistant)
- Modern web browser with microphone access (for voice commands via web UI)

## Dependencies

- `reachy-mini>=1.0.0`
- `pydantic>=2.0.0`
- `websockets>=12.0`
- `numpy>=1.26.0`
- `scipy>=1.11.0`
- `uvicorn>=0.27.0`
- `openai>=1.0.0`

## Author

Created by [@adonaivera](https://huggingface.co/adonaivera)

## License

MIT
