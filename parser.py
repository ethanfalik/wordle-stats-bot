import re
import discord
from typing import Optional

WORDLE_NUM_RE = re.compile(r"Wordle\s+(?:No\.?\s*)?([\d,]+)", re.IGNORECASE)
SCORE_USER_RE = re.compile(r"([1-6X])/6\s*:\s*<@!?(\d+)>", re.IGNORECASE)


def _parse_wordle_number(text: str) -> Optional[int]:
    m = WORDLE_NUM_RE.search(text)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def _parse_score(raw: str) -> int:
    return 7 if raw.upper() == "X" else int(raw)


def parse_message(message: discord.Message) -> list[dict]:
    content = message.content
    wordle_number = _parse_wordle_number(content)
    pairs = SCORE_USER_RE.findall(content)
    if not pairs:
        return []

    results = []
    for score_str, user_id in pairs:
        results.append(
            {
                "message_id": str(message.id),
                "channel_id": str(message.channel.id),
                "guild_id": str(message.guild.id) if message.guild else "0",
                "user_id": user_id,
                "wordle_number": wordle_number,
                "score": _parse_score(score_str),
                "timestamp": message.created_at.isoformat(),
            }
        )
    return results
