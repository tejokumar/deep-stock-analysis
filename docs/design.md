# Deep Stock Analysis Bot Design

## Purpose

This bot is designed to find public stocks that may be setting up for unusually large moves before the move becomes obvious to the market. The core idea is simple: big stock moves often start with business changes that show up in fundamentals, transcripts, analyst estimates, news, and sentiment before they are fully reflected in price.

The bot does not focus on one theme such as AI, semiconductors, defense, or energy. Instead, it scans broadly for multiple kinds of structural change:

- A company spending heavily before a new revenue cycle.
- Margins improving before revenue acceleration is obvious.
- Assets being valued too cheaply by the market.
- News catalysts that may change investor perception.
- Earnings-call language about backlog, capacity, pricing power, or demand inflection.
- Analyst estimates and price targets that help sanity-check the upside case.

The output is a ranked list of candidates, from most bullish to least compelling, with an individual markdown report for each stock.

This is a research assistant, not a trading system and not financial advice. Its job is to reduce the universe from thousands of stocks to a small list worth studying.

## High-Level Architecture

The bot uses a funnel. Cheap, deterministic filters run first across the entire market. More expensive data and AI analysis are used only after a stock has earned its way into later stages.

```text
US stock universe
        |
        v
Stage 1: Liquidity and price filter
        |
        v
Stage 2: Fundamental anomaly scoring
        |
        v
Stage 3: Transcript, news, and sentiment analysis
        |
        v
Stage 4: Ranked reports with targets, estimates, and action labels
```

This keeps API usage controlled. The bot avoids sending thousands of stocks to AI models. It first narrows the list with structured market and financial data, then uses AI only where language and judgment are useful.

## Data Providers

### Polygon

Polygon is used for market data:

- Active US stock universe.
- Price and volume history.
- Recent performance over 6 months, YTD, 3 months, 1 month, 1 week, and today.
- Company details such as name and industry classification.
- News headlines and descriptions.

### ROIC.ai

ROIC.ai is used for richer quarterly fundamentals and transcripts where available:

- Quarterly revenue growth.
- CapEx trends.
- Margin changes.
- Cash-flow behavior.
- Balance-sheet and valuation context.
- Earnings transcripts.

### FMP

FMP is used as a fallback and for analyst data:

- Analyst revenue estimates.
- Analyst EPS estimates.
- Analyst price target ranges.
- Some profile and reference data.

### xAI

xAI is used for sentiment analysis on a limited candidate set:

- News sentiment.
- Catalyst believability.
- Hype level.
- Retail attention.
- Bullish and bearish points.

The bot caps sentiment analysis to avoid excessive AI API usage.

## Stage 1: Liquid Universe Filter

Stage 1 starts with active US equities from Polygon and removes stocks that are unlikely to be tradable or useful for this strategy.

Filters:

- Active US stocks.
- Common stocks and ADRs.
- Close price at least `$2.00`.
- 20-day average volume at least `250,000` shares.

Output:

- A cached SQLite database containing the liquid stock universe and price-performance stats.

Why it matters:

The market has many tiny, illiquid, or structurally unsuitable securities. Stage 1 prevents the rest of the bot from wasting time and API calls on them.

## Stage 2: Fundamental Anomaly Scoring

Stage 2 looks for business changes that may precede a large stock move.

The scoring system is intentionally broad. A stock can score well for different reasons:

- CapEx acceleration.
- Gross-margin improvement.
- Revenue acceleration.
- Free-cash-flow improvement.
- Low valuation versus asset base.
- Balance-sheet optionality.
- Low or compressed recent price volatility.

Examples of archetypes:

- MU-style cycle: investment or supply-cycle shift before earnings power is obvious.
- AMD-style margin shift: mix or share gains appearing before revenue fully catches up.
- SNDK-style asset revaluation: market price not reflecting replacement value or cycle recovery.
- NVDA/ARM-style structural demand: durable growth tied to compute, IP, or platform shifts.

Output:

- A shortlist of anomaly candidates with scores and reasons.
- Cached Stage 2 state so later stages can resume without scanning the full market again.

## Stage 3: Transcripts, News, and Sentiment

Stage 3 adds context that pure numbers can miss.

Transcript analysis looks for:

- Backlog expansion.
- Capacity being pre-sold.
- Pricing power.
- Demand inflection.
- Operating leverage.
- Product ramp or deployment language.

News analysis looks for:

- Contract wins.
- Analyst upgrades.
- Earnings surprises.
- Product launches.
- Regulatory milestones.
- M&A or strategic partnerships.
- Financing or dilution risks.

Sentiment analysis scores:

- Whether recent news is truly bullish.
- Whether the catalyst is believable.
- Whether the stock is over-hyped.
- Whether social or retail interest may amplify the move.

Output:

- A candidate sentiment profile.
- News-promoted candidates when a catalyst is strong enough.
- Better filtering so the bot does not simply dump everything into "manual review."

## Stage 4: Reports and Ranking

Stage 4 creates the actual research output.

Each stock gets an individual markdown report with:

- Ticker and archetype.
- Thesis score.
- Bot action.
- Current price.
- Preferred entry zone.
- Analyst target range.
- Recent analyst target.
- Analyst revenue and EPS estimates.
- Scenario targets.
- News and sentiment context.
- Bullish and bearish factors.
- Invalidation rules.

The report folder also includes `index.md`, a ranked summary page.

The index includes:

- Rank.
- Symbol.
- Company name.
- Sub sector.
- Score.
- Action.
- Thesis score.
- Current price.
- Entry zone.
- Analyst target range.
- Recent target.
- 2026 revenue and EPS estimates.
- Stock performance over 6 months, YTD, 3 months, 1 month, 1 week, and today.
- Believability score.
- Hype score.
- Link to the full report.

The index is meant to answer: "What are the best 20 names to pay attention to right now?"

## Ranking Philosophy

The final score combines several signals:

- Fundamental anomaly strength.
- Transcript or news confirmation.
- Catalyst believability.
- Analyst upside.
- Scenario upside.
- Recent price action.
- Hype penalty when a stock may already be too crowded.

The score is not a guarantee. It is a triage score: higher-ranked names deserve attention first.

## Scheduling

The bot runs in GitHub Actions.

### Weekly Stage 1 Universe

Runs Saturday at 4:00 PM Pacific time.

In GitHub cron this is stored as:

```text
Sunday 00:00 UTC
```

This job:

- Runs tests.
- Scans the full Polygon universe.
- Saves `pipeline_state.db`.
- Uploads the database as a GitHub Actions artifact named `stage1-state`.

### Weekly Stage 2-4 Analysis

Runs Saturday at 8:00 PM Pacific time.

In GitHub cron this is stored as:

```text
Sunday 04:00 UTC
```

This job:

- Runs tests.
- Downloads the latest successful Stage 1 artifact.
- Runs Stage 2, Stage 3, and Stage 4.
- Uploads generated reports as an artifact named `scheduled-reports`.
- Uploads the updated pipeline database.

## Where Reports Are Found

Reports generated in GitHub Actions are not committed to the repository. They are stored as workflow artifacts.

To view them:

1. Go to the GitHub repository.
2. Open the Actions tab.
3. Click a completed `Weekly Stage 2-4 Analysis` run.
4. Scroll to Artifacts.
5. Download `scheduled-reports`.
6. Open `reports/scheduled/index.md`.

Stage 1 alone does not generate reports. It only prepares the cached stock universe.

## Secrets and Configuration

The GitHub Actions jobs use the `production` environment.

Required environment secrets:

- `POLYGON_API_KEY`
- `ROIC_API_KEY`
- `FMP_API_KEY`
- `XAI_API_KEY`

Optional environment variable:

- `XAI_SENTIMENT_MODEL`, defaults to `grok-4.3`.

Local runs use `.env`, but GitHub Actions does not use the local `.env` file. In GitHub, secrets must be configured in the repository's `production` environment.

## Current Limitations

The bot is useful, but it is not magic. Known limitations:

- Data provider coverage can be uneven for smaller companies or ADRs.
- Analyst estimates may be sparse or stale for less-covered stocks.
- News sentiment can identify catalyst strength, but cannot predict market reaction perfectly.
- Some sub-sector labels depend on available provider industry metadata.
- Price targets are research references, not trade instructions.
- The bot does not yet manage a portfolio, position sizing, stop losses, or execution.

## Future Improvements

Useful next additions:

- Email or Slack delivery of the top 20 summary.
- A persistent dashboard instead of artifact downloads.
- More precise sub-sector taxonomy for AI infrastructure, memory, semis, optical networking, defense drones, nuclear, and power grid.
- Better handling for intraday news catalysts.
- Historical backtesting of the ranking score.
- Watchlist tracking over time.
- Automatic comparison of new reports against prior reports to detect thesis upgrades or deterioration.
- Portfolio-aware risk controls if the bot is later connected to trading workflows.

## One-Sentence Summary

The bot is a market-wide research funnel that uses price data, quarterly fundamentals, transcripts, news, analyst estimates, and AI sentiment to rank stocks that may be forming the conditions for unusually large future moves.
