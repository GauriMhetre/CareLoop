# CareLoop - Medication Reminder MCP Server

A Python MCP (Model Context Protocol) server for tracking medication doses with automatic alerts, built with the official mcp SDK and SQLite.

## Setup

### 1. Create Virtual Environment (Windows)

```powershell
cd careloop
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install Dependencies

```powershell
pip install "mcp[cli]" requests fastapi uvicorn
```

### 3. Run the Server

```powershell
python server.py
```

The server starts with:
- **MCP Server**: stdio transport (for MCP clients like Claude)
- **HTTP Server**: http://localhost:8000
  - Dashboard: `http://localhost:8000/`
  - API: `http://localhost:8000/api/state`

## Features

### MCP Tools

Access these tools through any MCP-compatible client:

- **`add_dose(name, due_time)`** - Schedule a new medication dose
  - `name`: Medication name (string)
  - `due_time`: ISO format datetime (e.g., `2024-01-15T09:00:00`)

- **`confirm_dose(name)`** - Mark a dose as taken
  - `name`: Medication name to confirm

- **`whats_next()`** - Get the next pending dose
  - Returns: Next dose with alert level and minutes until/late

- **`log_ring_event(kind)`** - Log user interactions
  - `kind`: Event type (e.g., `button_pressed`, `snooze`, `reminder_shown`)

### HTTP Routes

- **`GET /api/state`** - Get JSON state of all doses
  - Includes alert counts (warning/urgent)
  - Flags chronic misses (2+ missed in last 3 days)
  - Real-time minutes late calculation

- **`GET /`** - Dark theme dashboard with 3-second polling
  - Large, readable medication list
  - Alert badges (urgent/warning)
  - Chronic miss indicators
  - Auto-updating every 3 seconds

### Background Alerting

The server runs a background thread that monitors doses:

- **2 minutes late**: Sends warning alert via ntfy.sh (if enabled)
- **5 minutes late**: Sends urgent alert via ntfy.sh (if enabled)

Alerts are sent to `https://ntfy.sh/<your-topic>` (configure via NTFY_TOPIC environment variable).

## Configuration

### NTFY_TOPIC Environment Variable

The ntfy.sh topic is configured via the `NTFY_TOPIC` environment variable. This prevents the topic from being exposed in the repository.

**Important:** ntfy.sh topics are public. Choose a unique, hard-to-guess name to prevent unauthorized users from receiving your alerts.

#### Setting the topic:

**PowerShell (Windows):**
```powershell
$env:NTFY_TOPIC="your-random-topic-12345"
python server.py
```

**macOS/Linux:**
```bash
export NTFY_TOPIC="your-random-topic-12345"
python server.py
```

**Verify it's set:** You should see `ntfy topic: your-random-topic-12345` in the server startup output.

#### Subscribing to alerts:

1. Install the ntfy.sh app (available on iOS and Android)
2. Subscribe to your chosen topic in the app
3. You'll receive notifications when doses are late

## Database

Uses SQLite (`doses.db`) with two tables:

```sql
doses (id, name, due_time, confirmed, confirmed_at, created_at)
ring_events (id, kind, dose_id, timestamp)
```

## Medical Disclaimer

⚠️ **No Medical Advice**: This system is a reminder tool only. It does not provide medical advice and should not replace professional medical guidance. Always consult healthcare providers for medication decisions.

## Example Usage

### Add a dose via HTTP

```bash
# Not directly via HTTP - use MCP tools instead
# Example via MCP client or programmatically
```

### Check state via HTTP

```bash
curl http://localhost:8000/api/state
```

Response:
```json
{
  "doses": [
    {
      "id": 1,
      "name": "Aspirin",
      "due_time": "2024-01-15T14:30:00",
      "confirmed": false,
      "confirmed_at": null,
      "minutes_late": 5.5,
      "alert_level": "urgent",
      "chronic_miss": false
    }
  ],
  "alerts": {
    "warning_count": 0,
    "urgent_count": 1
  },
  "timestamp": "2024-01-15T14:35:32.123456"
}
```

### View Dashboard

Open `http://localhost:8000/` in your browser for the dark-themed dashboard.

## Integration with MCP Clients

### Using with Claude Desktop

1. Create a configuration file at `~/.config/claude-desktop/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "careloop": {
      "command": "python",
      "args": ["/path/to/careloop/server.py"]
    }
  }
}
```

2. Restart Claude Desktop to connect.

3. Use the CareLoop tools in your conversations with Claude.

## Testing

Run the test script:
```powershell
python test_server.py
```

## Customization

- **Alert Topic**: Modify `send_alert()` function to use custom ntfy.sh topic
- **Port**: Change port 8000 in the main script to use a different port
- **Database Path**: Set `DB_PATH` variable to store database elsewhere
- **Alert Timing**: Adjust 2-minute and 5-minute thresholds in `alert_worker()`

## Architecture

- **Backend**: Python with mcp SDK, FastAPI, SQLite
- **Frontend**: Single-page app with vanilla JavaScript
- **Transport**: stdio for MCP protocol, HTTP for dashboard
- **Alerting**: Background thread with ntfy.sh integration
