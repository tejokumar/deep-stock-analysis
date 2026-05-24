# Deep Stock Analysis

Multi-stage stock anomaly discovery bot based on `codex.md`.

For a higher-level explanation of the bot architecture and workflow, see [docs/design.md](docs/design.md).

The first implementation slice covers:

- Stage 1: liquid US common-stock universe filtering.
- Stage 2: broad quantitative anomaly scoring across multiple archetypes:
  - CapEx divergence.
  - Margin acceleration.
  - Asset replacement discount.
  - Revenue acceleration.
  - Cash-flow inflection.
  - Balance-sheet optionality.
- Stage 3: transcript confirmation for structural backlog, capacity, pricing, operating leverage, and ramp language. On FMP Starter, the bot falls back to stock news because earnings call transcripts require a higher FMP plan.
- Stage 4: catalyst-linked markdown reports for transcript-confirmed candidates.
- SQLite state caching in `pipeline_state.db`.
- Sample-data mode for local development without API calls.

## Run Locally

Use the deterministic sample data:

```bash
python3 -m deep_stock_analysis.cli \
  --stage stage1-stage4 \
  --sample-data samples/broad_anomaly_sample.json \
  --state-path /private/tmp/deep-stock-sample.db \
  --reports-dir /private/tmp/deep-stock-reports \
  --limit 10
```

Run against live providers after setting API keys:

```bash
cp .env.example .env
# Fill POLYGON_API_KEY and ROIC_API_KEY in .env.
# FMP_API_KEY is now optional fallback.
python3 -m deep_stock_analysis.cli --stage stage1-stage2 --limit 1000
```

Run through transcript confirmation:

```bash
python3 -m deep_stock_analysis.cli --stage stage1-stage3 --limit 1000
```

For exploratory quarterly runs, use a wider Stage 2 gate and let transcript scoring filter the list:

```bash
python3 -m deep_stock_analysis.cli --stage stage1-stage3 --limit 1000 --shortlist-min-score 30
```

Run through report generation:

```bash
python3 -m deep_stock_analysis.cli --stage stage1-stage4 --limit 1000 --reports-dir reports
```

Run the full Polygon universe with pagination:

```bash
python3 -m deep_stock_analysis.cli \
  --stage stage1-stage4 \
  --all-tickers \
  --shortlist-min-score 30 \
  --max-sentiment-candidates 50 \
  --reports-dir reports/full-run
```

Reuse cached Stage 1/2 data to speed up follow-up runs:

```bash
python3 -m deep_stock_analysis.cli \
  --stage stage1-stage4 \
  --use-cached-stage1 \
  --use-cached-stage2 \
  --cache-max-age-hours 24 \
  --shortlist-min-score 30 \
  --reports-dir reports/cached-rerun
```

Each report directory includes an `index.md` file.

## Test

```bash
python3 -m unittest discover -s tests
```

## Bot Schedule

- Stage 1: Saturday 4:00 PM PST.
- Stage 2: Saturday 8:00 PM PST.
- Stage 3: on-demand after Stage 2 candidates pass.
- Stage 4: on-demand for the highest-conviction candidates.

## GitHub Actions Schedule

The repository includes scheduled GitHub Actions workflows matching `codex.md`:

- `Weekly Stage 1 Universe`: Saturday 4:00 PM PST, stored as Sunday 00:00 UTC in GitHub cron.
- `Weekly Stage 2-4 Analysis`: Saturday 8:00 PM PST, stored as Sunday 04:00 UTC in GitHub cron.

Add these GitHub Actions environment secrets before enabling live runs. The workflows use the `production` environment, so create that environment and add the secrets there:

- `POLYGON_API_KEY`
- `ROIC_API_KEY`
- `FMP_API_KEY`
- `XAI_API_KEY`

Optional repository variable:

- `XAI_SENTIMENT_MODEL`, defaults to `grok-4.3`.

Stage 1 uploads `pipeline_state.db` as a `stage1-state` artifact. Stage 2 downloads the latest successful Stage 1 artifact, runs the cached Stage 1 universe through Stage 2-4, uploads a timestamped `scheduled-reports-*` artifact plus the updated pipeline state, and commits the generated markdown reports under `reports/<reverse-time>_<UTC timestamp>/`. The reverse-time prefix makes newer report folders sort first in GitHub, and `reports/README.md` links runs newest-first.
