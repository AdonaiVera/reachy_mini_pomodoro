---
title: Reachy Mini Pomodoro
emoji: 🍅
colorFrom: red
colorTo: orange
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

A Pomodoro productivity timer app for Reachy Mini robot featuring **Compita**, an AI voice assistant that helps you stay focused and productive.

## Features

- **Compita Voice Assistant**: Talk to your robot companion using natural voice commands
- **Pomodoro Timer**: 25-minute focus sessions with 5-minute short breaks and 15-minute long breaks
- **Task Management**: Create and organize tasks with estimated pomodoro counts, priorities, and tags
- **Robot Expressions**: Reachy Mini provides encouragement and celebrates your progress
- **Break Activities**: Breathing exercises and stretches demonstrated by Reachy during breaks
- **Progress Tracking**: View productivity statistics and session history

## Installation

### Using pip

```bash
git clone <repo-url>
cd reachy_mini_pomodoro
python -m venv venv
source venv/bin/activate
pip install -e .
```

### Using uv

```bash
uv venv --python 3.12
source .venv/bin/activate
uv sync
```

## Configuration

### OpenAI API Key (Required for Compita Voice Assistant)

Compita requires an OpenAI API key to enable voice interactions. Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys).

**Option 1: Environment variable**
```bash
export OPENAI_API_KEY="sk-your-api-key-here"
```

**Option 2: Create a `.env` file** in the project root:
```
OPENAI_API_KEY=sk-your-api-key-here
```

**Note:** Compita uses OpenAI's Realtime API (`gpt-4o-realtime-preview`) for natural voice conversations. If no API key is configured, the app will still work but without voice assistant features.

## Usage

### Wireless Robot (Network Connection)

```bash
python -m reachy_mini_pomodoro --wireless
```

### USB Robot (Local Connection)

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
| Pause/Resume | "Pause the timer" |
| Start break | "I need a break" |
| Create task | "Add a task called review code" |
| List tasks | "What are my tasks?" |
| Complete task | "Mark this task as done" |
| Get stats | "How productive was I today?" |

## Robot Behaviors

| State | Reachy's Behavior |
|-------|-------------------|
| Focus Start | Wake up animation |
| During Focus | Gentle breathing |
| Focus Reminder | Encouraging nod |
| Focus Complete | Celebration |
| Break Time | Breathing demo to follow along |
| Task Complete | Victory dance |

## API Endpoints

The app exposes a REST API at `http://localhost:8042/api/`:

- `GET /api/status` - Timer and task status
- `POST /api/timer/start` - Start focus session
- `POST /api/timer/pause` - Pause timer
- `POST /api/timer/resume` - Resume timer
- `POST /api/timer/stop` - Stop timer
- `POST /api/timer/break` - Start break
- `GET /api/tasks` - List tasks
- `POST /api/tasks` - Create task
- `GET /api/stats` - Productivity statistics
- `GET /api/compita/status` - Voice assistant status

## Requirements

- Reachy Mini robot (wireless or USB)
- Python 3.10+
- OpenAI API key (for Compita voice assistant)

## License

MIT
