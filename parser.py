import re
import discord
from datetime import date, timedelta

# Wordle puzzle #1 was published on 2021-06-19
_WORDLE_EPOCH = date(2021, 6, 19)

# Matches a score line: "4/6: ..." or "👑 4/6: ..."
_SCORE_LINE_RE = re.compile(r"([1-6X])/6\s*:(.+?)(?=\n|$)", re.IGNORECASE)
# Matches either a proper Discord mention <@123> or a plain @username text mention
_MENTION_RE = re.compile(r"<@!?(\d+)>|@(\w+)")


def _wordle_number(msg_date: date) -> int:
    # The summary bot reports "yesterday's results"
    return (msg_date - timedelta(days=1) - _WORDLE_EPOCH).days + 1


def _parse_score(raw: str) -> int:
    return 7 if raw.upper() == "X" else int(raw)


def _find_member(guild: discord.Guild, name: str) -> discord.Member | None:
    """Find a cached guild member by display name, global name, or username."""
    name_lower = name.lower()
    for member in guild.members:
        if (
            member.display_name.lower() == name_lower
            or member.name.lower() == name_lower
            or (member.global_name and member.global_name.lower() == name_lower)
        ):
            return member
    return None


def _resolve_mentions(text: str, guild: discord.Guild | None) -> list[str]:
    """Return user IDs from a score line, resolving plain @names to UUIDs."""
    user_ids = []
    for m in _MENTION_RE.finditer(text):
        if m.group(1):
            user_ids.append(m.group(1))
        elif m.group(2) and guild:
            member = _find_member(guild, m.group(2))
            if member:
                user_ids.append(str(member.id))
            else:
                print(f"[parser] could not resolve @{m.group(2)} to a guild member", flush=True)
    return user_ids


def parse_message(message: discord.Message) -> list[dict]:
    content = message.content
    wordle_num = _wordle_number(message.created_at.date())

    results = []
    for line_match in _SCORE_LINE_RE.finditer(content):
        score = _parse_score(line_match.group(1))
        user_ids = _resolve_mentions(line_match.group(2).strip(), message.guild)
        print(f"[parser] msg={message.id} wordle=#{wordle_num} score={score}/6 users={user_ids}", flush=True)
        for user_id in user_ids:
            results.append(
                {
                    "message_id": str(message.id),
                    "channel_id": str(message.channel.id),
                    "guild_id": str(message.guild.id) if message.guild else "0",
                    "user_id": user_id,
                    "wordle_number": wordle_num,
                    "score": score,
                    "timestamp": message.created_at.isoformat(),
                }
            )
    return results
