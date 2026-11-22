# Telegram Job Aggregator

The backend reads messages from Telegram groups/channels, classifies them with
Gemini or Ollama, and forwards relevant original messages to your Telegram bot.
It uses FastAPI and PostgreSQL.

## Requirements

- Python 3.10+
- PostgreSQL
- A Telegram account that belongs to the groups/channels you want to monitor
- A Telegram bot
- Either a Gemini API key or a running Ollama server/model

## 1. Create Telegram API credentials

These credentials let Telethon sign in as your Telegram user account. They are
different from the bot token used for sending notifications.

1. Sign in at [my.telegram.org](https://my.telegram.org).
2. Open **API development tools** and create an application.
3. Copy the numeric **App api_id** and **App api_hash**.
4. Save both values for the `backend/.env` setup below.
5. Also note the account phone number, including the country code, such as
   `+15551234567`.

## 2. Create the notification bot and get its chat ID

1. In Telegram, open the verified **@BotFather** account.
2. Send `/newbot`, follow its prompts, and save the bot token.
3. Open the new bot's private chat and send `/start`.
4. Save the numeric chat ID for the `/start` message:
   - From the `backend` directory, with its virtual environment active, run
     `python scripts/test_bot.py`.
   - Find `result[...].message.chat.id` in the printed `getUpdates` response.
     If `result` is empty, send `/start` to the bot again and rerun the script.
5. Save this ID as `TELEGRAM_CHAT_ID`. This is the destination chat for job
   notifications; it is **not** the ID of a group you want to monitor.

## 3. Configure secrets in `backend/.env`

From the project root, create your local environment file:

```powershell
Copy-Item backend\.env.example backend\.env
```

Edit `backend/.env` and provide the database connection and credentials:

```dotenv
DATABASE_URL="postgresql+asyncpg://postgres:your_password@localhost:5432/telegram_job_aggregator"
TELEGRAM_API_ID="your_numeric_api_id"
TELEGRAM_API_HASH="your_api_hash"
TELEGRAM_PHONE="+15551234567"
TELEGRAM_BOT_TOKEN="your_bot_token"
TELEGRAM_CHAT_ID="your_bot_chat_id"
GEMINI_API_KEY="your_gemini_api_key"
```

Only credentials and secrets belong in `.env`. Do not add the provider, model,
batch size, or prompt path there.

## 4. Set defaults in `backend/config.py`

Edit the Python values near the top of `backend/config.py` to configure the
classifier:

```python
LLM_PROVIDER = "ollama"  # "gemini" or "ollama"
LLM_BATCH_SIZE = 5
GEMINI_MODEL = "gemini-3.8-flash"
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "phi3:latest"
LLM_PROMPT_PATH = Path("prompts/job_filter.txt")
```

- Set `LLM_PROVIDER = "gemini"` to use Gemini; set it to `"ollama"` to use
  Ollama. Gemini requires `GEMINI_API_KEY` in `backend/.env`.
- `LLM_BATCH_SIZE` is the maximum number of pending messages sent to the model
  in one request. It must be a positive integer.
- Set the desired provider's model name in `GEMINI_MODEL` or `OLLAMA_MODEL`.
- The prompt path is relative to the `backend` directory, not the current
  terminal directory. Change `LLM_PROMPT_PATH` in `config.py` to point to a
  different file.

The prompt directory is intentionally Git-ignored so personal job criteria
stay local. Create the configured prompt file if it is not present in your
checkout:

```powershell
New-Item -ItemType Directory -Force backend\prompts
notepad backend\prompts\job_filter.txt
```

Write the job-matching criteria you want. The prompt must tell the model to
return valid JSON with exactly one result per input message, copying each
`channel_id` and `message_id`, and setting `is_relevant` to `true` or `false`.
The classifier raises an error if any input message is missing from the
response.

## 5. Install dependencies and prepare PostgreSQL

From the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create a PostgreSQL database matching the database name in `DATABASE_URL`.
With the virtual environment active and the terminal still in `backend`, run:

```powershell
alembic upgrade head
```

For Ollama, install/start Ollama separately and make sure the model configured
as `OLLAMA_MODEL` is available. Gemini uses the already-listed `google-genai`
Python dependency.

## 6. Start the API and authenticate Telegram

From the `backend` directory, start the server:

```powershell
uvicorn main:app --reload
```

Check `http://127.0.0.1:8000/` for the running status. The interactive API
reference is at `http://127.0.0.1:8000/docs`.

The server connects to Telegram on startup. To sign in for the first time:

1. Request a login code:

   ```powershell
   Invoke-RestMethod -Method Post "http://127.0.0.1:8000/telegram/login"
   ```

2. Submit the code received in Telegram:

   ```powershell
   Invoke-RestMethod -Method Post "http://127.0.0.1:8000/telegram/login?code=YOUR_CODE"
   ```

3. If Telegram asks for the two-step verification password, submit it with the
   code as `&password=YOUR_PASSWORD`.

The Telethon session is saved locally. Later server starts reuse that session;
do not share or commit it.

## 7. Find and add groups/channels to monitor

You must add the groups/channels to the backend before syncing their messages.
The Telegram user account used above must already be a member of each target
group/channel.

1. Get the groups and channels visible to the signed-in account:

   ```powershell
   Invoke-RestMethod "http://127.0.0.1:8000/telegram/channels"
   ```

   The response contains each item's `id`, `name`, and `type`. Copy the `id`
   for each group/channel you want to monitor.

2. Add one or more IDs to the backend database. The endpoint accepts a JSON
   array of objects, even when adding only one group:

   ```powershell
   $body = '[{"channel_id":-1001234567890}]'
   Invoke-RestMethod -Method Post `
     -Uri "http://127.0.0.1:8000/telegram/channels" `
     -ContentType "application/json" -Body $body
   ```

   Replace the example with an ID from the previous response. To add multiple
   groups in one request, include multiple objects, for example
   `'[{"channel_id":-1001234567890},{"channel_id":-1009876543210}]'`.
   A successful response lists the saved `channel_id` and `channel_name`.

3. Optionally preview messages from an added group:

   ```powershell
   Invoke-RestMethod "http://127.0.0.1:8000/telegram/messages/-1001234567890?limit=5"
   ```

## 8. Sync, classify, and check notifications

Run the complete workflow after adding groups:

```powershell
curl.exe -N -X POST "http://127.0.0.1:8000/telegram/jobs/run"
```

It syncs new messages from the groups saved in step 7, classifies pending
messages in batches of `LLM_BATCH_SIZE`, then forwards relevant original
messages to the bot chat configured by `TELEGRAM_CHAT_ID`. The response streams
progress events; look for `status` values such as `channel_completed`,
`batch_started`, `message_completed`, and `completed`. Check the bot chat for
forwarded messages.

For separate checks instead of the full workflow:

1. Sync messages from all saved groups with `POST /telegram/messages/sync`.
2. Classify pending messages with `POST /telegram/jobs/process`.

Both endpoints can also be run from `/docs`. `POST /telegram/channels` must be
completed first or there will be no saved channels to sync.

## Local files and secrets

Do not commit `backend/.env`, API keys, bot tokens, or Telethon session files.
The root and backend `.gitignore` files exclude Telethon session files and the
entire `backend/prompts/` directory. Keep a private backup of your prompt if
you need it on another machine.
