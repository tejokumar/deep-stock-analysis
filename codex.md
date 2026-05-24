---

# Deep Analysis Bot: Architecture & Implementation Blueprint

This guide outlines the architectural design and programmatic steps required to build an automated, deep-fundamental discovery bot. The system filters thousands of listed equities down to high-conviction structural anomalies (such as **OKLO**, **ARM**, **AMD**, or historical inflection cycles like **MU**) using a cost-efficient, multi-tier funnel.

---

## 1. System Topology & Data Lineage

To optimize API costs and throughput, data flows linearly through increasingly complex filters. Heavy structural computation and LLM processing are reserved exclusively for the final stages.

* **Stage 1: Master Ticker Universe (10,000+ Equities)**
* *Provider:* Polygon.io API
* *Filter:* Active, US, Liquid Common Stocks


* **Stage 2: Liquid Revenue Traders (~2,500 Equities)**
* *Provider:* FMP API Key Metrics
* *Filter:* CapEx Divergence, Margin Inflexion, SOTP


* **Stage 3: Quant Shortlist Equities (~150 Equities)**
* *Provider:* FMP Transcript API + xAI/Claude
* *Filter:* LLM Structural Backlog & Guidance Matrix


* **Stage 4: High-Conviction Alerts (~5-12 Equities)**
* *Provider:* Deep Generative Review
* *Output:* Valuation Models, Price Targets, 12–24 Month Timeline



---

## 2. Technical Prerequisites & Data Providers

Ensure your configuration or environment variables have the following active API credentials:

* **POLYGON_API_KEY**: High-performance market data engine for master ticker synchronization, active listing states, and historical volume calculations.
* **FMP_API_KEY**: Structured fundamental database providing financial statement histories (10-Q/10-K parameters), key-metric ratios, and clean, timestamped earnings call transcripts.
* **ANTHROPIC_API_KEY / XAI_API_KEY**: Specialized text evaluation engines used exclusively for non-deterministic context matching and valuation target orchestration.

---

## 3. Tiered Pipeline Engineering Instructions

### Stage 1: Liquid Universe Filtration Engine

* **Cadence:** Weekly (Execute every Saturday at 4:00 PM PST).
* **Objective:** Sieve out un-investable structural noise (ETFs, mutual funds, illiquid micro-caps, penny stocks, over-the-counter ADRs).
* **Filter Logic:**
1. Query the Polygon `/v3/reference/tickers` endpoint filtering for active US equities (`market=stocks`, `active=true`).
2. Extract historical aggregate bars (`/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}`) covering the previous 20 trading days.
3. Retain only tickers where:
* **Close Price** >= $2.00
* **Average Daily Volume (20-Day)** >= 250,000 shares





### Stage 2: Quantitative Fundamental Archetype Screening

* **Cadence:** Weekly (Execute every Saturday at 8:00 PM PST immediately following Stage 1).
* **Objective:** Identify operational divergence anomalies—where underlying industrial changes have occurred, but the asset price remains flat or compressed.
* **Implementation Modules:**

#### Module A: CapEx Divergence Sieve (The Micron/MU Archetype)

* Query FMP's `/api/v3/financial-growth/{ticker}?period=quarter` endpoint.
* Calculate Year-over-Year (YoY) Capital Expenditure growth:
* *Delta CapEx (YoY) = (CapEx[Current] - CapEx[Last Year]) / CapEx[Last Year]*


* **Trigger:** Retain if **Delta CapEx (YoY) >= 30%** and the stock price 6-month trailing standard deviation is compressed (**<= 5%**).

#### Module B: Margin Acceleration Sieve (The AMD Archetype)

* Query FMP's `/api/v3/ratios/{ticker}?period=quarter`.
* Evaluate Gross Profit Margin for the current period (t) and past consecutive periods (t-1, t-2).
* **Trigger:** Retain if:
* *Gross Margin[t] - Gross Margin[t-1] >= 200 bps (0.02)*
* *Revenue Growth[t] <= 5%* (Signals a market share flip preceding top-line recognition).



#### Module C: Asset Replacement Devaluation Sieve (The Sandisk/SNDK Archetype)

* Query FMP's `/api/v3/key-metrics/{ticker}?period=quarter`.
* Calculate Tangible Asset Base to Enterprise Value conversion:
* *EV / Tangible Book Value <= 1.2x*


* **Trigger:** Retain if the valuation falls below this threshold and the **Industry Segment** matches Cyclical Hardware or Commodity Hardware Manufacturing.

### Stage 3: NLP Transcript Sentiment & Backlog Extraction

* **Cadence:** Quarterly / On-Demand (Triggered immediately when target tickers pass Stage 2; no fixed PST run time).
* **Objective:** Perform programmatic context extraction via semantic structural tags without manual verification.
* **Data Sourcing:** Fetch clean transcript chunks from FMP's `/api/v3/earning_call_transcript/{ticker}` using the most recent quarter string parameters.
* **LLM Processing Instructions (Claude / xAI API Execution):**
* Initialize the LLM context window with system instructions optimized for structural business shifts. Do not pass variable pricing inputs here; extract core textual indicators.
* **Semantic Scoring Prompts:** Instruct the LLM to inspect text blocks specifically for key phrase anchors. It must output a strict JSON structure conforming to the schema below:



```json
{
  "ticker": "STRING",
  "backlog_expansion_detected": "BOOLEAN",
  "capacity_pre_sold": "BOOLEAN",
  "pricing_power_indicator": "INTEGER (0-100)",
  "textual_evidence_excerpt": "STRING",
  "pipeline_confidence_score": "INTEGER (0-100)"
}

```

* **Sieve Boundary:** Tickers with a `pipeline_confidence_score` **< 85** are immediately purged from active processing queues.

### Stage 4: Deep Generative Financial Analysis & Valuation Targets

* **Cadence:** On-Demand (Run exclusively on the passing ~5-12 high-conviction equities; no fixed PST run time).
* **Objective:** Calculate forward-looking intrinsic values and coordinate multi-variable structural target timelines.
* **Execution Blueprint:**
* Instruct your LLM agent to dynamically orchestrate an analysis across three distinct valuation pillars depending on the company's structural archetype:
1. **Alternative / Capacity Ramps (e.g., OKLO):** Value based on contract backlog gigawatt capacity multiplied by localized Power Purchase Agreement (PPA) margin structures. Timeline mapped to Nuclear Regulatory Commission (NRC) validation cycles.
2. **Intellectual Property Monopolies (e.g., ARM):** Value based on prospective Tier-Migration models. Shift legacy royalty architectures to high-end multi-core designs, calculating Average Selling Price (ASP) expansions.
3. **Cyclical Hardware Runners (e.g., AMD, MU):** Value calculated using Peak-Cycle Forward Multiples. Determine historically normalized operating margins applied to peak supply-deficit periods rather than depressed current metrics.


* **Timeline Anchor Calculations:** The bot must mathematically link price execution windows to tangible underlying operational catalysts. **It is forbidden to output a naked timeline (e.g., "12 Months")** without pairing it to an asset delivery milestone (e.g., *"TSMC node fabrication volume scaling in Q3"* or *"Phase 1 commissioning of production facility"*).



---

## 4. Production Execution & Automation Engineering

To launch and manage the pipeline securely:

1. **State Management:** Cache the outputs of Stage 1 and Stage 2 into a localized PostgreSQL or structured SQLite instance (`pipeline_state.db`). This ensures that if network timeouts hit during heavy LLM evaluations, execution context can immediately resume without reprocessing master queries.
2. **Rate Limiting & Safety Rails:**
* **Polygon/FMP APIs:** Enforce basic thread limits (`max_workers=5`) when iterating over the ticker list to respect institutional infrastructure constraints.
* **LLM APIs:** Implement exponential backoff handling to handle burst requests cleanly.


3. **Alert Dispatch Lifecycle:** Once Stage 4 generates an approved deep dive report, format the markdown payload and execute an internal webhook broadcast (Slack, Discord, or Email pipeline) displaying:
* Ticker + Structural Archetype Classification.
* Core Macro Trigger (e.g., CapEx Divergence or Backlog Accumulation).
* Base, Bull, and Bear Price Targets.
* Catalyst-Linked Investment Horizon Window.
