import asyncio
import os
import re
from datetime import datetime, timezone
from typing import Optional

import discord
from dateutil.relativedelta import relativedelta
from discord import app_commands
from discord.ext import commands

from database import DB_PATH, get_results, get_scan_state, init_db, update_scan_state, upsert_result, upsert_results_bulk
from parser import parse_message
from stats import calculate_stats, format_stats_embed

# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PERIOD_RE = re.compile(r"(\d+)\s*(day|week|month|year)s?", re.IGNORECASE)


def parse_period(text: str) -> Optional[datetime]:
    """Convert e.g. '3 months' → a UTC datetime cutoff."""
    m = PERIOD_RE.search(text.strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    delta_map = {
        "day":   relativedelta(days=n),
        "week":  relativedelta(weeks=n),
        "month": relativedelta(months=n),
        "year":  relativedelta(years=n),
    }
    return datetime.now(timezone.utc) - delta_map[unit]


async def scan_channel(channel: discord.TextChannel, after_dt: Optional[datetime] = None) -> int:
    """
    Crawl channel history, parse Wordle results, and persist to SQLite.
    Returns the number of new rows inserted.
    """
    last_id = await get_scan_state(DB_PATH, str(channel.id))

    # Prefer the stored message bookmark over the time-based cutoff
    if last_id:
        after_target = discord.Object(id=int(last_id))
    elif after_dt:
        after_target = after_dt
    else:
        after_target = None

    batch: list[dict] = []
    last_msg_id: Optional[str] = None
    count = 0

    async for i, msg in _aenumerate(
        channel.history(limit=None, after=after_target, oldest_first=True)
    ):
        rows = parse_message(msg)
        batch.extend(rows)
        last_msg_id = str(msg.id)

        # Flush every 200 rows and yield the event loop
        if len(batch) >= 200:
            count += await upsert_results_bulk(DB_PATH, batch)
            batch = []
        if i % 100 == 0:
            await asyncio.sleep(0)

    if batch:
        count += await upsert_results_bulk(DB_PATH, batch)

    if last_msg_id:
        await update_scan_state(DB_PATH, str(channel.id), last_msg_id)

    return count


async def _aenumerate(aiter, start: int = 0):
    i = start
    async for item in aiter:
        yield i, item
        i += 1


def _make_embed(data: dict) -> discord.Embed:
    embed = discord.Embed(
        title=data["title"],
        description=data["description"],
        color=data["color"],
    )
    embed.set_footer(text=data["footer"])
    return embed


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

@bot.tree.command(name="scan", description="Scan this channel's history for Wordle results (admin only).")
@app_commands.default_permissions(manage_guild=True)
async def slash_scan(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)
    count = await scan_channel(interaction.channel)
    await interaction.followup.send(
        f"Scan complete. **{count}** new Wordle result(s) stored from #{interaction.channel.name}."
    )


@bot.tree.command(name="stats", description="Show your Wordle stats.")
@app_commands.describe(period='Time window, e.g. "3 months", "1 year". Leave blank for all time.')
async def slash_stats(interaction: discord.Interaction, period: str = "") -> None:
    await interaction.response.defer(thinking=True)
    cutoff, period_label = _resolve_period(period)

    # Incremental scan before querying
    await scan_channel(interaction.channel, after_dt=cutoff)

    rows = await get_results(DB_PATH, str(interaction.user.id), str(interaction.channel.id), cutoff)
    stats = calculate_stats(rows)

    if stats is None:
        await interaction.followup.send(
            f"No Wordle results found for **{interaction.user.display_name}** ({period_label})."
        )
        return

    embed_data = format_stats_embed(stats, interaction.user.display_name, period_label)
    await interaction.followup.send(embed=_make_embed(embed_data))


@bot.tree.command(name="stats_for", description="Show Wordle stats for another user.")
@app_commands.describe(
    user="The Discord member to look up.",
    period='Time window, e.g. "3 months", "1 year". Leave blank for all time.',
)
async def slash_stats_for(
    interaction: discord.Interaction,
    user: discord.Member,
    period: str = "",
) -> None:
    await interaction.response.defer(thinking=True)
    cutoff, period_label = _resolve_period(period)

    await scan_channel(interaction.channel, after_dt=cutoff)

    rows = await get_results(DB_PATH, str(user.id), str(interaction.channel.id), cutoff)
    stats = calculate_stats(rows)

    if stats is None:
        await interaction.followup.send(
            f"No Wordle results found for **{user.display_name}** ({period_label})."
        )
        return

    embed_data = format_stats_embed(stats, user.display_name, period_label)
    await interaction.followup.send(embed=_make_embed(embed_data))


def _resolve_period(period: str) -> tuple[Optional[datetime], str]:
    if not period.strip():
        return None, "all time"
    cutoff = parse_period(period)
    if cutoff is None:
        return None, "all time"
    return cutoff, period.strip()


# ---------------------------------------------------------------------------
# Live ingestion — pick up new results without waiting for /scan
# ---------------------------------------------------------------------------

@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot and message.guild:
        rows = parse_message(message)
        for row in rows:
            await upsert_result(DB_PATH, row)
        if rows:
            await update_scan_state(DB_PATH, str(message.channel.id), str(message.id))
    await bot.process_commands(message)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@bot.event
async def on_ready() -> None:
    await init_db(DB_PATH)
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Slash commands synced. Ready.")


if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Set the DISCORD_TOKEN environment variable before running.")
    bot.run(token)
