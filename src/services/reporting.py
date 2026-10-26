"""Phase 14: human-readable run report (also shown in the GitHub Actions job summary)."""
from src.models import RunStats


def render_run_summary(stats: RunStats, lifetime_cost: float, lifetime_budget: float) -> str:
    rows = [
        ("Status", stats.status + (" (dry run)" if stats.dry_run else "")),
        ("Claude used", "yes" if stats.llm_used else "no (fallback ranking)"),
        ("Articles discovered", stats.articles_discovered),
        ("After filtering and dedup", stats.articles_after_filtering),
        ("Sent to Claude", stats.articles_sent_to_claude),
        ("Selected for newsletter", stats.articles_selected),
        ("Failed feeds", stats.failed_feeds),
        ("Input tokens", f"{stats.input_tokens:,}"),
        ("Output tokens", f"{stats.output_tokens:,}"),
        ("Estimated cost (this run)", f"${stats.estimated_cost_usd:.5f}"),
        ("Total recorded spend", f"${lifetime_cost:.4f} of ${lifetime_budget:.2f} budget"),
        ("Duration", f"{stats.duration_seconds:.1f}s"),
    ]
    lines = ["## DataPulse AI run summary", "", "| Metric | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    if stats.notes:
        lines += ["", "**Notes**", ""] + [f"- {n}" for n in stats.notes]
    return "\n".join(lines) + "\n"
