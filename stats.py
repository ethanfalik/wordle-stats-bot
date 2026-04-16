from typing import Optional


def calculate_stats(rows: list[dict]) -> Optional[dict]:
    if not rows:
        return None

    scores = [r["score"] for r in rows]
    wins = [s for s in scores if s <= 6]
    fails = [s for s in scores if s == 7]

    return {
        "total": len(scores),
        "wins": len(wins),
        "fails": len(fails),
        "win_rate": len(wins) / len(scores) * 100,
        "best": min(wins) if wins else None,
        "worst": max(wins) if wins else None,
        "average": sum(scores) / len(scores),
    }


def format_stats_embed(
    stats: dict,
    display_name: str,
    period_label: str,
    color: int = 0x5865F2,
) -> dict:
    best = f"{stats['best']}/6" if stats["best"] is not None else "—"
    worst = f"{stats['worst']}/6" if stats["worst"] is not None else "—"
    lines = [
        f"**Games Played** : {stats['total']}",
        f"**Wins**         : {stats['wins']}  ({stats['win_rate']:.1f}%)",
        f"**Fails (X/6)**  : {stats['fails']}",
        f"**Best Game**    : {best}",
        f"**Worst Win**    : {worst}",
        f"**Average**      : {stats['average']:.2f} guesses",
    ]
    return {
        "title": f"Wordle Stats — {display_name}",
        "description": "\n".join(lines),
        "footer": f"Period: {period_label}",
        "color": color,
    }
