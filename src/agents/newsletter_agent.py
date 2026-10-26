"""The orchestrator: wires every stage of the funnel together and records what happened."""
import logging
import time
from datetime import datetime, timezone
from typing import Protocol

from src.agents.classifier import ArticleClassifier, fallback_select
from src.agents.summarizer import ArticleSummarizer
from src.config import Settings
from src.filters import ArticleFilter, ArticleRanker, DeduplicationService
from src.models import Article, RawArticle, RunStats
from src.services import (
    ArticleNormalizer, CostTracker, EmailError, EmailService, LLMError, LLMProvider,
    NewsletterBuilder, StorageService, render_run_summary,
)

log = logging.getLogger(__name__)


class Collector(Protocol):
    failed_feeds: list[str]

    def collect(self) -> list[RawArticle]: ...


class NewsletterAgent:
    def __init__(
        self,
        settings: Settings,
        collector: Collector,
        storage: StorageService,
        llm: LLMProvider | None = None,
        cost_tracker: CostTracker | None = None,
        email: EmailService | None = None,
        now: datetime | None = None,
    ) -> None:
        self.settings = settings
        self.collector = collector
        self.storage = storage
        self.llm = llm
        self.tracker = cost_tracker or CostTracker()
        self.email = email
        self.now = now

    def run(self, dry_run: bool = False) -> RunStats:
        started = time.monotonic()
        now = self.now or datetime.now(timezone.utc)
        stats = RunStats(started_at=now, dry_run=dry_run)
        try:
            self._run(stats, now, dry_run)
        except EmailError as exc:
            stats.status = "email_failed"
            stats.notes.append(f"Email failed: {exc}")
            log.error("Email failed: %s", exc)
        except Exception as exc:  # last-resort: record the failure, then let the caller exit non-zero
            stats.status = "failed"
            stats.notes.append(f"Unexpected error: {type(exc).__name__}: {exc}")
            log.exception("Pipeline failed")
        finally:
            stats.input_tokens = self.tracker.input_tokens
            stats.output_tokens = self.tracker.output_tokens
            stats.estimated_cost_usd = round(self.tracker.total_cost, 6)
            stats.duration_seconds = round(time.monotonic() - started, 2)
            self.storage.save_run(stats)
            self._write_summary(stats)
        return stats

    # ------------------------------------------------------------------

    def _run(self, stats: RunStats, now: datetime, dry_run: bool) -> None:
        s = self.settings

        # 1. collect -> normalize -> filter -> dedupe
        raw = self.collector.collect()
        stats.articles_discovered = len(raw)
        stats.failed_feeds = len(self.collector.failed_feeds)

        articles = ArticleNormalizer(s.max_article_chars).normalize_all(raw)
        flt = ArticleFilter(lookback_days=s.lookback_days)
        relevant = flt.filter_by_keywords(flt.filter_by_date(articles, now=now))
        unique = DeduplicationService().deduplicate(relevant, self.storage.get_sent_ids())
        self.storage.save_new(unique)
        stats.articles_after_filtering = len(unique)

        # 2. score in Python, keep only the top candidates for Claude
        candidates = ArticleRanker(s.lookback_days).select_top(unique, s.max_articles_to_claude, now=now)
        if not candidates:
            stats.status = "no_content"
            stats.notes.append("No new relevant articles this week; nothing sent.")
            log.warning("No candidates; skipping newsletter")
            return

        # 3. Claude: classify + select, then summarize (each step degrades gracefully)
        selected = self._classify(candidates, stats)
        stats.articles_selected = len(selected)
        selected = self._summarize(selected, stats)

        # 4. render, save to disk, send
        newsletter = NewsletterBuilder().build(selected, now.date())
        s.output_dir.mkdir(parents=True, exist_ok=True)
        (s.output_dir / "newsletter.html").write_text(newsletter.html, encoding="utf-8")
        (s.output_dir / "newsletter.txt").write_text(newsletter.text, encoding="utf-8")

        if dry_run:
            stats.status = "success"
            stats.notes.append(f"Dry run: newsletter written to {s.output_dir / 'newsletter.html'}, not emailed.")
        else:
            if self.email is None:
                raise EmailError("No email service configured")
            self.email.send(newsletter.subject, newsletter.html, newsletter.text)
            stats.status = "success"

        # 5. persist results; only a successful send marks articles as delivered
        for a in selected:
            self.storage.update_enrichment(a)
        self.storage.mark_processed([a.id for a in candidates])
        if not dry_run:
            self.storage.mark_sent([a.id for a in selected])

    def _llm_allowed(self, stats: RunStats) -> bool:
        if self.llm is None:
            return False
        run_cost = self.tracker.total_cost
        lifetime = self.storage.total_cost() + run_cost
        if run_cost >= self.settings.max_run_cost_usd:
            stats.notes.append(f"Per-run cost limit ${self.settings.max_run_cost_usd} reached; skipped Claude.")
        elif lifetime >= self.settings.lifetime_budget_usd:
            stats.notes.append(f"Lifetime budget ${self.settings.lifetime_budget_usd} reached; skipped Claude.")
        else:
            return True
        log.warning(stats.notes[-1])
        return False

    def _classify(self, candidates: list[Article], stats: RunStats) -> list[Article]:
        limit = self.settings.max_selected_articles
        if self._llm_allowed(stats):
            stats.articles_sent_to_claude = len(candidates)
            try:
                classifier = ArticleClassifier(
                    self.llm, max_selected=limit,
                    description_chars=min(400, self.settings.max_article_chars),
                )
                selected = classifier.classify_and_select(candidates)
                stats.llm_used = True
                if selected:
                    return selected
                stats.notes.append("Claude recommended nothing; used Python ranking instead.")
            except LLMError as exc:
                stats.notes.append(f"Claude classification failed ({exc}); used Python ranking instead.")
                log.warning("Classification failed: %s", exc)
        elif self.llm is None:
            stats.notes.append("Claude not configured; used Python ranking only.")
        return fallback_select(candidates, limit)

    def _summarize(self, selected: list[Article], stats: RunStats) -> list[Article]:
        llm = self.llm if (stats.llm_used and self._llm_allowed(stats)) else None
        return ArticleSummarizer(llm, self.settings.max_article_chars).summarize(selected)

    def _write_summary(self, stats: RunStats) -> None:
        try:
            self.settings.output_dir.mkdir(parents=True, exist_ok=True)
            report = render_run_summary(
                stats, self.storage.total_cost(), self.settings.lifetime_budget_usd
            )
            (self.settings.output_dir / "run_summary.md").write_text(report, encoding="utf-8")
            log.info(
                "Run %s: discovered=%d filtered=%d to_claude=%d selected=%d tokens=%d/%d cost=$%.5f",
                stats.status, stats.articles_discovered, stats.articles_after_filtering,
                stats.articles_sent_to_claude, stats.articles_selected,
                stats.input_tokens, stats.output_tokens, stats.estimated_cost_usd,
            )
        except OSError as exc:
            log.warning("Could not write run summary: %s", exc)
