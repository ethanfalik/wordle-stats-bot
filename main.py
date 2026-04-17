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
    Returns the number of rows upserted.
    """
    print(f"[scan] starting #{channel.name} | after_dt={after_dt}", flush=True)

    last_id, earliest_dt_str = await get_scan_state(DB_PATH, str(channel.id))
    earliest_dt = datetime.fromisoformat(earliest_dt_str) if earliest_dt_str else None
    print(f"[scan] state: last_id={last_id} earliest_dt={earliest_dt_str}", flush=True)

    # If the requested window goes further back than what we've already scanned,
    # start from after_dt so the gap gets filled.  Otherwise use last_id to
    # pick up only new messages.
    backfill_needed = (
        after_dt is not None
        and earliest_dt is not None
        and after_dt < earliest_dt
    )

    if last_id and not backfill_needed:
        after_target = discord.Object(id=int(last_id))
        print(f"[scan] incremental from message id={last_id}", flush=True)
    elif after_dt:
        after_target = after_dt
        print(f"[scan] {'backfill' if backfill_needed else 'fresh'} from after_dt={after_dt}", flush=True)
    else:
        after_target = None
        print("[scan] full scan from beginning", flush=True)

    # Track the earliest point we're scanning from so future calls can detect gaps.
    # A true full scan (after_target is None) marks everything as covered via a
    # sentinel date so period-based stats never trigger a spurious backfill.
    if after_target is None:
        new_earliest = datetime(2000, 1, 1, tzinfo=timezone.utc)
    elif after_dt is not None:
        new_earliest = min(after_dt, earliest_dt) if earliest_dt else after_dt
    else:
        new_earliest = earliest_dt

    batch: list[dict] = []
    last_msg_id: Optional[str] = None
    count = 0

    async for i, msg in _aenumerate(
        channel.history(limit=None, after=after_target, oldest_first=True)
    ):
        rows = parse_message(msg)
        batch.extend(rows)
        last_msg_id = str(msg.id)

        if len(batch) >= 200:
            print(f"[scan] flushing batch at msg #{i} | upserted so far: {count}", flush=True)
            count += await upsert_results_bulk(DB_PATH, batch)
            batch = []
        if i % 100 == 0:
            print(f"[scan] processed {i} messages | wordle rows found: {count + len(batch)}", flush=True)
            await asyncio.sleep(0)

    print(f"[scan] loop done | total messages scanned, flushing final batch of {len(batch)}", flush=True)
    if batch:
        count += await upsert_results_bulk(DB_PATH, batch)

    if last_msg_id:
        print(f"[scan] saving state | last_msg_id={last_msg_id}", flush=True)
        await update_scan_state(
            DB_PATH,
            str(channel.id),
            last_msg_id,
            new_earliest.isoformat() if new_earliest else None,
        )

    print(f"[scan] done | {count} rows upserted", flush=True)
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
    print(f"[/scan] called by {interaction.user} in #{interaction.channel.name}", flush=True)
    await interaction.response.send_message(
        f"Scan started for #{interaction.channel.name}. I'll post here when it's done."
    )
    asyncio.create_task(_run_scan(interaction.channel))


async def _run_scan(channel: discord.TextChannel) -> None:
    for attempt in range(3):
        try:
            count = await scan_channel(channel)
            await channel.send(f"Scan complete. **{count}** new Wordle result(s) stored from #{channel.name}.")
            return
        except Exception as e:
            print(f"[scan] Error on attempt {attempt + 1}: {e}", flush=True)
            if attempt < 2:
                await channel.send(f"Scan hit an error (attempt {attempt + 1}/3), retrying in 20 seconds...")
                await asyncio.sleep(20)
            else:
                await channel.send(f"Scan failed after 3 attempts. Last error: {e}")


@bot.tree.command(name="stats", description="Show your Wordle stats.")
@app_commands.describe(period='Time window, e.g. "3 months", "1 year". Leave blank for all time.')
async def slash_stats(interaction: discord.Interaction, period: str = "") -> None:
    print(f"[/stats] called by {interaction.user} | period='{period}'", flush=True)
    await interaction.response.defer(thinking=True)
    cutoff, period_label = _resolve_period(period)

    await scan_channel(interaction.channel, after_dt=cutoff)

    print(f"[/stats] querying DB for user={interaction.user.id}", flush=True)
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
    if message.guild:
        rows = parse_message(message)
        if rows:
            print(f"[on_message] {len(rows)} row(s) parsed from msg {message.id} by {message.author}", flush=True)
        for row in rows:
            await upsert_result(DB_PATH, row)
        if rows:
            await update_scan_state(DB_PATH, str(message.channel.id), str(message.id))
    await bot.process_commands(message)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
    if after.guild:
        rows = parse_message(after)
        if rows:
            print(f"[on_message_edit] {len(rows)} row(s) updated from msg {after.id}", flush=True)
        for row in rows:
            await upsert_result(DB_PATH, row)


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
