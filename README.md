# DataPulse AI

**Weekly Data Engineering Intelligence.** An automated agent that collects the week's Data Engineering news, filters it cheaply in Python, asks Claude Haiku to rank and summarize only the best candidates, and emails a clean HTML newsletter, all for a fraction of a cent per run.

## Problem Statement

Keeping up with Databricks, Spark, Azure, Kafka, Airflow, data quality and GenAI means skimming dozens of blogs and release feeds every week. Most of it is noise. Sending everything to an LLM would be slow and expensive. DataPulse AI shows a cost-aware alternative: use deterministic code to shrink hundreds of items to ~20, and use the LLM only where judgment and writing are needed.

## Features

- Collects from RSS/Atom feeds and GitHub release feeds (no scraping)
- Python-side date, keyword, dedup and weighted relevance filtering before any LLM call
- Claude Haiku classifies, scores, ranks and summarizes with validated structured JSON
- Remembers what it already sent (SQLite), so articles are never repeated
- Professional HTML + plain-text email with "Why this matters for a Data Engineer"
- Per-run token and cost tracking, a per-run spend cap and a lifetime budget guard
- Degrades gracefully: a dead feed, a Claude outage or garbage JSON never prevents the newsletter
- Runs weekly on GitHub Actions, or locally / in Docker

## Architecture

```
src/
  collectors/   RSSCollector, feed list
  filters/      ArticleFilter (date, keyword), DeduplicationService, ArticleRanker
  agents/       ArticleClassifier, ArticleSummarizer, NewsletterAgent (orchestrator)
  services/     ClaudeService (behind LLMProvider), StorageService, EmailService,
                NewsletterBuilder, CostTracker, ArticleNormalizer, reporting
  models/       Pydantic models: RawArticle, Article, RunStats, categories
  templates/    Jinja2 newsletter template
```

Components talk only through `Article` objects. The LLM is reached through the provider-neutral `LLMProvider` protocol, and only `claude_service.py` imports the Anthropic SDK, so another provider can be added without touching the rest of the app.

## Data Flow

```
RSS feeds + GitHub release feeds
   -> RSSCollector            (timeouts, retries, per-feed failure isolation)
   -> ArticleNormalizer       (clean HTML, canonical URL, stable ID, truncation)
   -> Date filter -> Keyword filter
   -> Deduplication           (in-batch + already-sent, via SQLite)
   -> ArticleRanker           (weighted Python score; top 20, max 4 per source)
   -> Claude Haiku  call 1    (classify + score + recommend; one call for all candidates)
   -> Python selection        (8-10 best)
   -> Claude Haiku  call 2    (summary + "why it matters"; selected articles only)
   -> NewsletterBuilder       (HTML + text)
   -> EmailService (SMTP)     -> mark articles as sent
```

Each run makes **at most 4 Claude calls** (two logical calls, each with one retry on unusable output).

## Tech Stack

Python 3.11+, Anthropic Claude API (Haiku), feedparser, httpx, Pydantic, SQLite, Jinja2, pytest, GitHub Actions, Docker.

## Project Structure

```
.github/workflows/weekly-newsletter.yml   scheduled pipeline
scripts/sync_state.sh                     persists the SQLite DB between CI runs
src/                                      application code (see Architecture)
tests/                                    unit + end-to-end tests (no network, no real API calls)
Dockerfile, requirements.txt, .env.example
```

## Installation

```bash
git clone https://github.com/<you>/de-newsletter-agent.git
cd de-newsletter-agent
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env             # then edit .env
```

## Configuration

All configuration is via environment variables (`.env` locally, GitHub Secrets in CI). See `.env.example`.

| Variable | Purpose | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API key (secret) | none (runs without Claude) |
| `CLAUDE_MODEL` | Model | `claude-haiku-5-5` |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Mail login (Gmail: use an App Password) | none |
| `EMAIL_FROM` / `EMAIL_TO` | Sender / comma-separated recipients | username / none |
| `MAX_ARTICLES_TO_CLAUDE` | Candidates sent to Claude | 20 |
| `MAX_SELECTED_ARTICLES` | Articles in the newsletter | 10 |
| `MAX_ARTICLE_CHARS` | Per-article text cap sent to Claude | 1500 |
| `MAX_OUTPUT_TOKENS` | Hard output cap per call | 2000 |
| `MAX_RUN_COST_USD` | Stop calling Claude in a run past this | 0.25 |
| `LIFETIME_BUDGET_USD` | Stop calling Claude once total spend reaches this | 5.0 |
| `LOOKBACK_DAYS` | Recency window | 7 |

Add or remove feeds in `src/collectors/feeds.py` and keywords in `src/filters/keywords.py`.

## Running Locally

```bash
python -m src.main --dry-run --no-llm   # free: no Claude, no email; writes output/newsletter.html
python -m src.main --dry-run            # uses Claude, writes the newsletter, does not email
python -m src.main                      # the real thing: Claude + email
python -m src.check_claude              # one tiny call to verify your API key
```

Outputs land in `output/` (`newsletter.html`, `newsletter.txt`, `run_summary.md`).

## Testing

```bash
pytest -v
```

The suite covers RSS parsing, retries and failure isolation, date and keyword filtering, deduplication, SQLite storage, relevance scoring, Claude response parsing and validation, cost calculation, newsletter rendering (including HTML escaping), SMTP delivery and full end-to-end runs. Every external system (feeds, Claude, SMTP) is faked, so tests are free and offline.

## GitHub Actions

`.github/workflows/weekly-newsletter.yml` runs every Monday at 07:00 UTC and can be started manually (with `dry_run` and `no_llm` options).

1. Add repository secrets: `ANTHROPIC_API_KEY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`.
2. Run it once from the **Actions** tab with `dry_run` enabled, then once for real.
3. Each run uploads the newsletter as an artifact and writes a cost summary to the job summary.

CI runners are ephemeral, so the SQLite database is saved to an orphan `state` branch after every run and restored at the start of the next. That is how "never repeat an article" survives between weeks. GitHub may disable scheduled workflows after 60 days without repository activity; re-enable it from the Actions tab if that happens.

## Cost Optimization

- **Funnel design:** hundreds of items become ~20 before Claude sees anything, using free Python filters and scoring.
- **Two batched calls per run** instead of one call per article.
- **Compact prompts:** title, source and a truncated description only (no URLs, no full pages).
- **Haiku model, thinking disabled, low effort:** classification and summaries don't need extended reasoning, and thinking tokens bill as output.
- **Hard caps:** `MAX_OUTPUT_TOKENS`, `MAX_ARTICLE_CHARS`, one retry maximum.
- **Spend guards:** per-run cost cap and a lifetime budget; once hit, the pipeline falls back to Python ranking instead of spending more.
- **Measured:** every run records tokens and estimated cost in SQLite and the run summary.

Pricing in `src/services/cost_tracker.py` is a hard-coded table; verify it against Anthropic's pricing page.

## Security

- No secrets in code. API and mail credentials come from environment variables or GitHub Secrets; `.env` is gitignored.
- Feed content is untrusted: the template auto-escapes everything, and only `http(s)` links are accepted.
- Claude output is validated with Pydantic before use; invalid items are dropped.
- The Docker image contains no secrets and runs as a non-root user.
- Use an app-specific mail password, never your primary one.

## Docker

```bash
docker build -t datapulse-ai .
docker run --rm --env-file .env -v "$PWD/data:/app/data" -v "$PWD/output:/app/output" datapulse-ai --dry-run
```

## Future Enhancements

- Additional LLM providers behind `LLMProvider`
- More sources (Hacker News, Reddit, arXiv, vendor release notes)
- Per-reader topic preferences and multiple newsletters
- Embedding-based near-duplicate detection
- Parallel feed fetching
- A minimum-score cutoff tuned from real Claude ratings
- Web archive of past issues

## License

MIT
