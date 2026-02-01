# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WebWatch is a Python-based Telegram bot that monitors WordPress websites for availability and health. It performs dual-layer health checks (HTTP status + WordPress health endpoint) and sends instant Telegram alerts to verified admins when sites go down or recover.

## Development Setup

### Initial Setup
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings (bot token, admin phones, domains API, etc.)
```

### Running the Bot
```bash
# Run directly
python3 main.py

# The bot runs continuously and will:
# - Check domains every CHECK_CYCLE seconds (default: 3600s/1hr)
# - Send Telegram notifications for status changes
# - Log events to logs/unreachable_domains.log
```

### Configuration Files
- `.env` - All runtime configuration (required, copy from .env.example)
- `bot_persistence.pkl` - Stores verified admin chat IDs (auto-generated)
- `ignored_domains.json` - Domains excluded from monitoring (auto-generated)
- `logs/unreachable_domains.log` - Domain status change log (auto-generated)

## Architecture

### Component Interaction Flow
```
main.py (orchestrator)
  ├─> bot.py (TelegramBot)
  │    ├─> Handles admin verification via phone number
  │    ├─> Processes commands (/ignore_add, /restart_checker, etc.)
  │    └─> Sends notifications to verified admins
  │
  └─> domain_checker.py (DomainChecker)
       ├─> Fetches domain list from DOMAINS_API
       ├─> Filters out ignored domains
       ├─> Performs dual-layer health checks:
       │    1. HEAD/GET to root domain (checks HTTP status)
       │    2. GET to /wp-json/wp-health-check/v1/status (checks WP health)
       ├─> Implements retry mechanism (MAX_FAILURES attempts)
       └─> Calls bot.send_notification_to_admins() on status changes
```

### Critical Design Patterns

**Async Architecture**: All I/O operations (HTTP checks, Telegram API calls) use asyncio. The bot uses `python-telegram-bot`'s async Application with JobQueue for scheduled checks.

**State Management**:
- `DomainChecker` maintains two key dictionaries:
  - `failure_counts: Dict[str, int]` - Tracks consecutive failures per domain
  - `unreachable_domains: Set[str]` - Currently down domains
- State transitions trigger notifications (unreachable → reachable or vice versa)

**Graceful Restart**: The `/restart_checker` command uses `asyncio.Event` (`stop_event`) to signal running jobs to abort, then clears state and reschedules. This prevents duplicate notifications when manually restarting checks.

**Phone Number Normalization**: Admin verification requires exact phone number matching. Both [config.py](config.py:85-93) and [bot.py](bot.py:89-97) normalize phone numbers to ensure they start with `+`. Log warnings if .env contains numbers without `+`.

### Domain Health Check Logic

The dual-layer check ([domain_checker.py](domain_checker.py:103-198)) ensures both HTTP availability and WordPress application health:

1. **Root HTTP Check** (HEAD, falls back to GET if 405):
   - Returns False if timeout, connection error, or status >= 400
   - Only proceeds to step 2 if status < 400

2. **WordPress Health Endpoint Check**:
   - Calls `/wp-json/wp-health-check/v1/status?api_key=...`
   - Expects JSON response: `{"status": "ok", "message": "..."}`
   - Returns False if status != "ok", invalid JSON, 401 (bad API key), or >= 400

**Why this matters**: A site can return HTTP 200 but have a broken WordPress backend (database error, fatal PHP error, etc.). The health endpoint catches these issues.

### Retry Mechanism

[domain_checker.py](domain_checker.py:270-321) implements immediate retries within the same check cycle:
- Failed domains retry up to `MAX_FAILURES` times with `retry_interval` (5s) between attempts
- Only marks domain unreachable after all retries exhausted
- Retries respect `stop_event` to allow graceful abort during `/restart_checker`

## Common Patterns

### Adding New Bot Commands
1. Define handler in [bot.py](bot.py) (async method taking `Update` and `ContextTypes.DEFAULT_TYPE`)
2. Check admin permission with `await self._check_admin_permission(update)`
3. Clear any ongoing conversation state if needed:
   ```python
   chat_id = update.effective_chat.id
   if chat_id in self.user_states:
       del self.user_states[chat_id]
   ```
4. Register handler in `setup_handlers()`:
   ```python
   self.application.add_handler(CommandHandler("your_command", self.your_handler))
   ```

### Multi-Step Conversations
Use `user_states` dictionary to track conversation flow (see `/ignore_add` and `/ignore_remove` implementation):
1. Set state: `self.user_states[chat_id] = YOUR_STATE_CONSTANT`
2. Handle input in `handle_domain_input()` based on state
3. Clear state after completion: `del self.user_states[chat_id]`
4. Allow cancellation via `/cancel` command

### Interacting with Domain Checker from Bot
The bot and checker are loosely coupled via callbacks:
- Bot passes `send_notification_to_admins` callback to checker at initialization ([main.py](main.py:36))
- Bot passes `get_current_ignored_domains` callback for real-time ignore list access
- Bot calls `domain_checker.reset_state()` and reschedules jobs for `/restart_checker`

## Important Behaviors

### Admin Verification
- Admins must share their Telegram contact (via KeyboardButton with `request_contact=True`)
- Bot verifies `contact.phone_number` against `ADMIN_PHONE_NUMBERS` from .env
- Verified chat IDs persist across restarts in `bot_persistence.pkl`
- Multiple admins supported (all receive notifications)

### Ignore List Persistence
- Stored as JSON array in `ignored_domains.json`
- Loaded at bot startup, modified via `/ignore_add` and `/ignore_remove`
- Checker fetches current list via callback on each cycle (no restart needed)

### Logging Strategy
- Console logging via `logging` module (INFO level by default)
- Domain status changes logged to file: `logs/unreachable_domains.log`
- Format: `YYYY-MM-DD HH:MM:SS TZ - [UNREACHABLE|REACHABLE]: domain.com`

### Signal Handling
[main.py](main.py:67-72) handles SIGINT/SIGTERM for graceful shutdown:
1. Stop polling for Telegram updates
2. Close httpx AsyncClient
3. Shutdown Telegram Application (flushes persistence)

## Environment Variables Reference

Required variables (must be set in .env):
- `TELEGRAM_BOT_TOKEN` - From @BotFather
- `ADMIN_PHONE_NUMBERS` - JSON array of phone numbers with `+` prefix
- `DOMAINS_API` - Endpoint returning JSON array of domain strings

Optional variables with defaults:
- `CHECK_CYCLE=3600` - Seconds between full domain checks
- `MAX_FAILURES=3` - Retry attempts before marking unreachable
- `TIMEOUT=30` - HTTP request timeout in seconds
- `VERIFY_SSL=true` - Set to `false` for self-signed certs (insecure)
- `WP_HEALTH_CHECK_API_KEY` - API key for WordPress health endpoint (if required)

## WordPress Plugin Requirements

Each monitored WordPress site must have the health check endpoint configured:

**Endpoint**: `/wp-json/wp-health-check/v1/status`

**Expected Response** (healthy site):
```json
{
  "status": "ok",
  "message": "WordPress is healthy"
}
```

**API Key Protection**: If `WP_HEALTH_CHECK_API_KEY` is set in .env, the checker appends `?api_key=YOUR_KEY` to requests. The WordPress plugin must validate this key.

**Plugin Recommendation**: Use "WP Health Check API" plugin or implement custom endpoint that returns the above JSON format.

## Debugging Tips

### Check if bot is receiving updates:
```python
# Temporarily add to bot.py start_command():
logger.info(f"User {user.id}, Username: {user.username}, Phone: {contact.phone_number if contact else 'N/A'}")
```

### Verify phone number normalization:
```bash
python3 config.py  # Runs the __main__ block in config.py to print loaded config
```

### Test single domain check manually:
```python
# Add temporary code in domain_checker.py:
async def test_single_domain():
    checker = DomainChecker(config, lambda msg: print(msg), lambda: set())
    result = await checker.check_domain_status("example.com")
    print(f"Result: {result}")
    await checker.close_client()
```

### Monitor job queue:
```python
# Add in main.py after scheduling jobs:
jobs = job_queue.get_jobs_by_name("Domain Check Cycle")
logger.info(f"Active jobs: {len(jobs)}, Next run: {jobs[0].next_t if jobs else 'None'}")
```

## Deployment Considerations

### Process Management
Use systemd, supervisor, or similar to keep the bot running:
```systemd
[Unit]
Description=WebWatch Telegram Bot
After=network.target

[Service]
Type=simple
User=webwatch
WorkingDirectory=/path/to/WebWatch
ExecStart=/path/to/WebWatch/.venv/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Security Hardening
- Store `.env` with restrictive permissions (600)
- Use separate user account with minimal privileges
- Enable `VERIFY_SSL=true` in production
- Protect WordPress health endpoints with strong API keys
- Regularly rotate `TELEGRAM_BOT_TOKEN` and `WP_HEALTH_CHECK_API_KEY`

### Performance Tuning
- Increase `CHECK_CYCLE` for large domain lists (>100 domains)
- Reduce `TIMEOUT` if dealing with consistently slow sites
- Consider rate limiting if DOMAINS_API has request limits
- Monitor memory usage if `unreachable_domains` set grows large
