# Wordle Stats Historian — Setup Guide

Hey, so I built a Discord bot that tracks Wordle stats for our server. Here's everything you need to do to get it running — just follow the steps in order.

---

## Step 1 — Install Python

Go to https://www.python.org/downloads/ and download Python 3.11 or newer. When the installer opens, **make sure you check the box that says "Add Python to PATH"** before hitting Install. If you skip that, nothing will work.

Verify it worked by opening a terminal (search "cmd" or "PowerShell" in the Start menu) and typing:

```
python --version
```

You should see something like `Python 3.11.x`.

---

## Step 2 — Get the bot files

Click the green **Code** button at the top of this page, then **Download ZIP**. Extract the folder somewhere easy to find, like your Desktop or Documents. It contains these files:

```
wordle_bot/
├── main.py
├── parser.py
├── database.py
├── stats.py
└── requirements.txt
```

---

## Step 3 — Create the Discord Application

This is where you create the actual bot account on Discord's side.

1. Go to https://discord.com/developers/applications and log in with your Discord account.
2. Click **"New Application"** in the top right. Give it a name like "Wordle Stats Bot" and hit **Create**.
3. In the left sidebar, click **"Bot"**.
4. Scroll down to **"Privileged Gateway Intents"** and turn on **both** of these:
   - **Server Members Intent**
   - **Message Content Intent**
5. Click **"Save Changes"**.
6. Still on the Bot page, click **"Reset Token"**, confirm it, then **copy the token** it shows you. This is a long string like `MTExNTk3...`. **Save this somewhere safe and don't share it with anyone** — it's the bot's password.

---

## Step 4 — Invite the bot to your server

1. In the left sidebar on the developer portal, click **"OAuth2"**, then **"URL Generator"**.
2. Under **Scopes**, check: `bot` and `applications.commands`.
3. Under **Bot Permissions**, check:
   - `Read Messages / View Channels`
   - `Read Message History`
4. Scroll down, copy the **Generated URL**, paste it in your browser, and invite the bot to whatever server you want.

---

## Step 5 — Install the bot's dependencies

Open a terminal and navigate to the `wordle_bot` folder. The easiest way: open the folder in File Explorer, click the address bar at the top, type `cmd`, and press Enter — that opens a terminal already in the right place.

Then run:

```
pip install -r requirements.txt
```

Wait for it to finish. It installs the three libraries the bot needs.

---

## Step 6 — Give the bot its token

The bot needs to know the token you copied in Step 3. In the same terminal, run this (replace the part in quotes with your actual token):

**On Windows (Command Prompt):**
```
set DISCORD_TOKEN=paste-your-token-here
```

**On Windows (PowerShell):**
```
$env:DISCORD_TOKEN="paste-your-token-here"
```

> **Important:** You have to do this every time you open a new terminal window. If you want it to be permanent so you never have to do it again, search "Environment Variables" in the Start menu → "Edit the system environment variables" → "Environment Variables" → New → name it `DISCORD_TOKEN`, value is the token.

---

## Step 7 — Run the bot

In the same terminal window (after setting the token), run:

```
python main.py
```

You should see:

```
Logged in as Wordle Stats Bot#1234 (ID: ...)
Slash commands synced. Ready.
```

The bot is now online. **Don't close the terminal** — closing it shuts the bot down.

---

## Step 8 — Use it in Discord

Go to the channel where the Wordle results bot posts. Then:

| Command | What it does |
|---|---|
| `/scan` | Run this **first, one time**. Crawls the entire channel history and builds the stats database. Requires Manage Server permission. |
| `/stats` | Shows your own Wordle stats (all time). |
| `/stats 3 months` | Your stats for the last 3 months. |
| `/stats_for @someone 1 year` | Stats for any other person in the server. |

After the first `/scan`, the bot keeps itself up to date automatically — you never need to run `/scan` again unless you want to force a full refresh.

---

## Keeping it running 24/7 (optional)

Right now the bot only works while the terminal is open on your PC. If you want it always online, the easiest free option is to host it on [Railway](https://railway.app) or [Render](https://render.com) — both have free tiers that can run a Python script continuously. Let me know if you want help with that part and I'll walk you through it.
