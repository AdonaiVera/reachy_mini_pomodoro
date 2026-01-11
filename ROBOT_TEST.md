# Testing on Robot via SSH

## 1. Copy Code to Robot

From your computer:

```bash
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='.git' --exclude='build' --exclude='*.egg-info' --exclude='.claude' <YOUR_PROJECT_PATH>/ pollen@reachy-mini.local:~/<YOUR_PROJECT_NAME>/
```

Example:
```bash
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='.git' --exclude='build' --exclude='*.egg-info' --exclude='.claude' /Users/ado/Documents/reachy_mini_pomodoro/ pollen@reachy-mini.local:~/reachy_mini_pomodoro/
```

## 2. Install the App

From your computer:

```bash
ssh pollen@reachy-mini.local "/venvs/apps_venv/bin/pip install -e ~/<YOUR_PROJECT_NAME>"
```

Example:
```bash
ssh pollen@reachy-mini.local "/venvs/apps_venv/bin/pip install -e ~/reachy_mini_pomodoro"
```

## 3. Run from Dashboard

1. Open http://reachy-mini.local in your browser
2. Find your app in the apps list
3. Click to launch it

## 4. Open the App

```
http://reachy-mini.local:8042
```

## 5. Debug API Endpoints

### Voice Status
```
http://reachy-mini.local:8042/api/compita/status
```

Expected response for robot audio:
```json
{
  "enabled": true,
  "running": true,
  "has_api_key": true,
  "voice_mode": "robot",
  "robot_voice_available": true,
  "robot_voice_debug": {
    "input_sample_rate": 16000,
    "output_sample_rate": 16000,
    "session_active": true
  }
}
```

If `input_sample_rate` is `null`, robot audio failed to initialize.

### Voice Settings
```
http://reachy-mini.local:8042/api/compita/settings
```

### App Status
```
http://reachy-mini.local:8042/api/status
```

### Tasks
```
http://reachy-mini.local:8042/api/tasks
```

### Debug
```
http://reachy-mini.local:8042/api/compita/debug
```

### Manual Voice Activation
If wake word detection isn't working (openWakeWord not installed), you can:
1. Click the microphone icon in the web UI, OR
2. Call the activate endpoint via curl:
```bash
curl -X POST http://reachy-mini.local:8042/api/compita/activate
```

## Quick Copy + Install (One Command)

```bash
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='.git' --exclude='build' --exclude='*.egg-info' --exclude='.claude' <YOUR_PROJECT_PATH>/ pollen@reachy-mini.local:~/<YOUR_PROJECT_NAME>/ && ssh pollen@reachy-mini.local "/venvs/apps_venv/bin/pip install -e ~/<YOUR_PROJECT_NAME>"
```

Example:
```bash
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='.git' --exclude='build' --exclude='*.egg-info' --exclude='.claude' /Users/ado/Documents/reachy_mini_pomodoro/ pollen@reachy-mini.local:~/reachy_mini_pomodoro/ && ssh pollen@reachy-mini.local "/venvs/apps_venv/bin/pip install -e ~/reachy_mini_pomodoro"
```

Then launch from the dashboard.

## SSH Access (if needed)

```bash
ssh pollen@reachy-mini.local
```

Password: `reachy`
