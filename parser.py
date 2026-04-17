import re
import discord
from datetime import date, timedelta

# Wordle puzzle #1 was published on 2021-06-19
_WORDLE_EPOCH = date(2021, 6, 19)

# Matches a score line: "4/6: ..." or "👑 4/6: ..."
_SCORE_LINE_RE = re.compile(r"([1-6X])/6\s*:(.+?)(?=\n|$)", re.IGNORECASE)
# Matches every Discord mention on a line
_MENTION_RE = re.compile(r"<@!?(\d+)>")


def _wordle_number(msg_date: date) -> int:
    # The summary bot reports "yesterday's results"
    return (msg_date - timedelta(days=1) - _WORDLE_EPOCH).days + 1


def _parse_score(raw: str) -> int:
    return 7 if raw.upper() == "X" else int(raw)


def parse_message(message: discord.Message) -> list[dict]:
    content = message.content
    wordle_num = _wordle_number(message.created_at.date())

    results = []
    for line_match in _SCORE_LINE_RE.finditer(content):
        score = _parse_score(line_match.group(1))
        users = _MENTION_RE.findall(line_match.group(2).strip())
        print(f"[parser] msg={message.id} wordle=#{wordle_num} score={score}/6 users={users}", flush=True)
        for user_id in users:
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
