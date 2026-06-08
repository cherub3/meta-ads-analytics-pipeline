# Meta Ads Performance Analytics Pipeline

A end-to-end marketing data engineering project that ingests Facebook ad campaign data,
validates and transforms it through a layered warehouse, calculates campaign KPIs and health
scores, detects performance anomalies, and surfaces actionable business recommendations
through a Streamlit dashboard.

Built as a portfolio project demonstrating skills relevant to:
Data Engineer | Analytics Engineer | Marketing Data Engineer | Performance Marketing Data Engineer

---

## Business Problem

Marketing teams run ad campaigns daily across multiple audiences. Without an automated
pipeline, performance analysis means manually exporting CSVs and building Excel reports.
That process is slow, error-prone, and produces no early warnings when something goes wrong.

This pipeline answers:

- Which campaigns generate the most conversions at the lowest cost?
- Which campaigns are wasting budget?
- Which audience segments convert best?
- When did campaign performance drop — and by how much?
- Which campaigns should be scaled, optimised, or paused?

---

## Dataset

**Source:** Facebook Ad Campaign Performance Dataset (Kaggle)
**Period:** August 17–30, 2017 (14 days)
**Granularity:** Ad x Audience Segment x Day
**Campaigns:** 3 campaigns (IDs: 916, 936, 1178)

| Column               | Description                                         |
|----------------------|-----------------------------------------------------|
| `ad_id`              | Unique identifier for each ad row                   |
| `reporting_start`    | Date of the reporting period (daily data)           |
| `campaign_id`        | Internal campaign identifier                        |
| `fb_campaign_id`     | Facebook's campaign/ad set identifier               |
| `age`                | Age bracket of targeted audience (e.g. 30-34)       |
| `gender`             | Gender of targeted audience (M / F)                 |
| `interest1/2/3`      | Facebook interest category IDs (opaque numeric)     |
| `impressions`        | Times the ad was shown                              |
| `clicks`             | Times users clicked the ad                          |
| `spent`              | Spend in USD for this row                           |
| `total_conversion`   | Total conversion events (view-through + click)      |
| `approved_conversion`| Verified conversions -- the primary quality signal  |

**What the dataset does NOT contain:** revenue, ROAS, placement data, device data,
budget limits, or ad creative information. All analysis uses only metrics the data
actually supports.

---

## Key Finding: 33% of Source Records Were Corrupted

During data profiling, **382 of 1,143 rows (33.4%)** were found to be malformed.

In those rows, columns were shifted left by one position:
- `campaign_id` contained an age bracket (e.g. `45-49`) instead of a campaign ID
- `fb_campaign_id` contained gender values (`M` / `F`)
- `total_conversion` and `approved_conversion` were missing entirely

This corruption is consistent with a source export where one column was silently dropped,
cascading a shift across all subsequent columns.

**Action taken by the pipeline:**
Every rejected row is logged to `validation_log` with its rejection reason. A
`validation_summary` table captures total rows, valid rows, rejected rows, and rejection
breakdown per run. Nothing is silently dropped.

> "The validation approach in this project was directly inspired by the
> Automated Data Quality Monitoring Framework (Project 2), which established
> the pattern of logging every rejection with an explicit reason rather than
> discarding records silently."

**Usable dataset after validation:** 761 rows across 3 campaigns, 14 days.

---

## Architecture

```
dataset/data.csv  (1,143 rows -- raw source)
        |
        v
[ 01_validate.py ]  -- Validation Layer
    Valid rows:    761  --> continue
    Rejected rows: 382  --> validation_log + validation_summary
        |
        v
[ 02_ingest.py ]  -- Bronze Layer (Incremental Loading)
    raw_campaign_performance (761 rows, append-only)
    Checkpoint: checkpoints/last_loaded_date.txt
        |
        v
[ 03_transform.py ]  -- Silver Layer
    dim_campaign              (3 rows)
    dim_audience              (8 rows)
    fact_campaign_performance (133 rows -- aggregated grain)
        |
        v
[ 04_mart.py ]  -- Gold Layer
    mart_campaign_kpis        (3 rows -- KPIs + health scores)
    mart_campaign_monitoring  (34 rows -- daily trends)
    campaign_summary          (3 rows -- recommendations)
        |
        v
[ 05_anomaly.py ]  -- Anomaly Detection
    anomaly_log               (6 anomalies flagged)
        |
        v
[ dashboard/app.py ]  -- Streamlit Dashboard (5 pages)
```

---

## Data Model

### Bronze Layer

**`raw_campaign_performance`** -- exact copy of valid source rows. Append-only.
Serves as the audit trail. Never modified after load.

### Silver Layer (Dimensions + Fact)

**`dim_campaign`**

| Column              | Description                              |
|---------------------|------------------------------------------|
| campaign_id         | Primary key                              |
| distinct_fb_campaigns | Distinct Facebook campaign IDs seen    |
| total_ad_rows       | Number of bronze rows for this campaign  |
| first_seen_date     | Earliest date in dataset                 |
| last_seen_date      | Latest date in dataset                   |

**`dim_audience`**

| Column     | Description                                       |
|------------|---------------------------------------------------|
| audience_id| Natural key: age_group + '_' + gender (e.g. 30-34_M) |
| age_group  | 30-34, 35-39, 40-44, 45-49                        |
| gender     | M or F                                            |

**`fact_campaign_performance`** -- grain: campaign x date x audience

| Column              | Description                                   |
|---------------------|-----------------------------------------------|
| campaign_id         | FK to dim_campaign                            |
| date                | Reporting date                                |
| audience_id         | FK to dim_audience                            |
| impressions         | Sum of impressions for this grain             |
| clicks              | Sum of clicks                                 |
| spend               | Sum of spend ($)                              |
| total_conversion    | Sum of total conversions                      |
| approved_conversion | Sum of approved conversions                   |
| ad_count            | Number of source rows aggregated into this row|

### Gold Layer (Marts)

**`mart_campaign_kpis`** -- one row per campaign, all KPIs pre-calculated

**`mart_campaign_monitoring`** -- one row per campaign per day, with 3-day rolling averages

**`campaign_summary`** -- lean summary with health score, recommendation, strength, and risk

**`validation_log`** / **`validation_summary`** -- data quality audit tables

**`anomaly_log`** -- flagged performance anomalies with descriptions

---

## KPI Definitions

All KPIs are calculated from actual dataset columns. No revenue, ROAS, or ROI metrics
are used because the dataset does not contain revenue data.

| KPI                | Formula                                        | Business Meaning                                   |
|--------------------|------------------------------------------------|----------------------------------------------------|
| **CTR**            | Clicks / Impressions x 100                     | Ad relevance -- are people clicking?               |
| **CPC**            | Spend / Clicks                                 | Average cost per click                             |
| **CPA**            | Spend / Approved Conversions                   | Cost to acquire one verified conversion            |
| **Conversion Rate**| Approved Conversions / Clicks x 100           | Quality of traffic -- do clickers convert?         |
| **CPM**            | (Spend / Impressions) x 1000                   | Cost per 1,000 impressions -- reach efficiency     |

---

## Campaign Health Score Methodology

Every campaign receives a score from 0 to 100, composed of four components worth 0-25 points each.

**Scoring method: min-max normalisation across campaigns**

```
CTR Score        = (CTR - min_CTR) / (max_CTR - min_CTR) x 25
Conv Rate Score  = (CR  - min_CR)  / (max_CR  - min_CR)  x 25
CPA Score        = (max_CPA - CPA) / (max_CPA - min_CPA) x 25   <-- inverted (lower = better)
CPM Score        = (max_CPM - CPM) / (max_CPM - min_CPM) x 25   <-- inverted (lower = better)

Health Score = CTR Score + Conv Rate Score + CPA Score + CPM Score
```

**Why relative scoring?** The dataset contains no external benchmark data. Relative
scoring is honest -- it shows how campaigns compare to each other, not against an arbitrary
industry threshold. A recruiter or interviewer can verify every number by hand.

| Score   | Label     | Meaning                              |
|---------|-----------|--------------------------------------|
| 90-100  | Excellent | Top performer across all KPIs        |
| 70-89   | Good      | Strong overall with minor weaknesses |
| 50-69   | Average   | Mixed performance, needs optimisation|
| Below 50| Poor      | Significant underperformance         |

---

## Campaign Segmentation and Recommendations

| Tier               | Criteria                                       | Recommendation                                      |
|--------------------|------------------------------------------------|-----------------------------------------------------|
| High Performer     | Health score >= 70 AND CPA <= median CPA       | Scale Budget -- strong efficiency                   |
| Poor Performer     | High spend + low conversion rate               | Review / Pause -- not returning value               |
| Poor Performer     | CPA > 1.5x median CPA                          | Reduce Budget -- acquisition cost too high          |
| Standard Performer | All other cases                                | Optimise -- test new audiences or creatives         |

---

## Real Business Findings

These are actual findings from the data, not hypothetical examples.

### Finding 1 -- Campaign 916 is the Most Efficient Campaign

Campaign 916 has the lowest CPA ($6.24) and highest conversion rate (21.2%) despite being
the smallest campaign by spend ($149.71 over 14 days). Its health score of **82/100 (Good)**
makes it a clear candidate for budget scaling. If 10% of Campaign 1178's budget were
reallocated here, the portfolio CPA would drop materially.

### Finding 2 -- Campaign 1178 Is Spending the Most but Converting Worst

Campaign 1178 accounts for **84.5% of total spend** ($16,577 of $19,620) but produces only
**64.6% of total conversions** (378 of 585). Its CPA of $43.85 is 7x higher than Campaign 916.
Health score: **25/100 (Poor)**. Recommendation: review audience targeting and creative
before continuing at this spend level.

### Finding 3 -- Campaign 936 Shows Signs of Efficiency Decay

On August 26, Campaign 936's CPA spiked to $117.65 -- 2.6x its 3-day average of $45.66.
This was automatically flagged as a CPA_SPIKE anomaly. A marketing manager relying on weekly
reports would have missed this intra-week spike. The daily monitoring table catches it.

### Finding 4 -- Campaign 916 Went Dark on August 25-26

Campaign 916 recorded zero clicks and zero conversions on August 25, despite non-zero spend.
The pipeline flagged this as both a CTR_DROP (100% drop from baseline) and ZERO_CONVERSIONS
anomaly. This type of silent underperformance -- spend continues, results stop -- is one of the
most damaging patterns in paid media and exactly what automated monitoring exists to catch.

### Finding 5 -- 30-34 Age Group Drives the Most Conversions

Across all campaigns and genders, the 30-34 age group generates the highest total approved
conversions. The 30-34 / M audience combination shows the strongest engagement in CTR heatmap
analysis. This is actionable -- a media buyer could test increased budget allocation toward
this segment.

### Finding 6 -- Data Validation Prevented Corrupted Data From Entering Analytics

Without the validation layer, all 382 corrupted rows would have been loaded. Those rows
contain no conversion data and invalid campaign IDs. Including them in aggregations would
have suppressed all campaign-level metrics -- CTR, CPA, and conversion rate would all be
artificially deflated. The validation layer ensured that the business numbers reflect only
clean, trustworthy data.

---

## Anomaly Detection Rules

No machine learning. Rules are transparent and explainable.

| Rule               | Condition                                              | Severity |
|--------------------|--------------------------------------------------------|----------|
| CTR_DROP           | Daily CTR < 70% of 3-day rolling average               | HIGH     |
| CPA_SPIKE          | Daily CPA > 150% of 3-day rolling average              | HIGH     |
| SPEND_SPIKE        | Daily spend > 3x campaign average daily spend          | MEDIUM   |
| ZERO_CONVERSIONS   | Approved conversions = 0 where spend > $0              | HIGH     |

6 anomalies were detected across the 14-day window across Campaigns 916 and 936.

---

## Incremental Loading

The pipeline implements checkpoint-based incremental loading.

```
checkpoints/last_loaded_date.txt  <-- stores last successfully loaded date
```

On each run:
1. Read `last_loaded_date` from checkpoint file
2. Filter source rows where `reporting_start > last_loaded_date`
3. Load only new rows into `raw_campaign_performance`
4. Update checkpoint to the maximum date in the loaded batch

On the first run: all 761 valid rows are loaded.
On subsequent runs with no new data: zero rows loaded, pipeline exits cleanly.

In a production system, this checkpoint would live in a metadata table in the warehouse
rather than a flat file, but the pattern is identical.

---

## Project Structure

```
meta-ads-pipeline/
|-- dataset/
|   `-- data.csv                     Raw Facebook Ads export
|
|-- pipeline/
|   |-- 01_validate.py               Validation layer -- reject bad records
|   |-- 02_ingest.py                 Bronze layer -- incremental loading
|   |-- 03_transform.py              Silver layer -- dimensions + fact table
|   |-- 04_mart.py                   Gold layer -- KPIs, health scores, monitoring
|   `-- 05_anomaly.py                Anomaly detection -- rule-based flagging
|
|-- dashboard/
|   `-- app.py                       Streamlit dashboard (5 pages)
|
|-- analytics/
|   `-- queries.sql                  Named business analyses in SQL
|
|-- warehouse/
|   `-- meta_ads.duckdb              Local DuckDB warehouse
|
|-- checkpoints/
|   `-- last_loaded_date.txt         Incremental load watermark
|
|-- run_pipeline.py                  Single-command pipeline orchestrator
`-- README.md
```

---

## How to Run

**Requirements**

```
pip install duckdb pandas streamlit plotly
```

**Run the full pipeline (one command)**

```bash
python run_pipeline.py
```

This runs all 5 stages in order: validate -> ingest -> transform -> mart -> anomaly.

**Run individual stages**

```bash
python pipeline/01_validate.py
python pipeline/02_ingest.py
python pipeline/03_transform.py
python pipeline/04_mart.py
python pipeline/05_anomaly.py
```

**Launch the dashboard**

```bash
streamlit run dashboard/app.py
```

**Reset and re-run from scratch**

```bash
echo 2017-08-16 > checkpoints/last_loaded_date.txt
python run_pipeline.py
```

---

## Tech Stack

| Tool       | Purpose                                               |
|------------|-------------------------------------------------------|
| Python     | Pipeline orchestration, data validation, KPI logic    |
| Pandas     | Data loading, transformation, health score calculation|
| DuckDB     | Local analytical warehouse (all SQL runs here)        |
| SQL        | Aggregations, window functions, KPI queries           |
| Streamlit  | Interactive 5-page business dashboard                 |
| Plotly     | Charts -- bar, scatter, pie, line, heatmap, treemap   |

No cloud infrastructure. No Docker. No Spark. Everything runs locally in under 2 seconds.

---

## Connection to Other Portfolio Projects

| Project | Focus | Connection |
|---------|-------|------------|
| Project 1: Marketing Attribution Warehouse | Attribution modelling, channel analytics, dbt | Provides the attribution logic this project builds on for campaign analysis |
| Project 2: Automated Data Quality Monitoring Framework | DQ rules, monitoring, alerting | The validation layer in this project applies the same reject-and-log pattern established in Project 2 |
| Project 3: Meta Ads Performance Analytics Pipeline (this project) | Campaign performance, KPIs, health scoring, anomaly detection | Focuses on operational campaign monitoring and budget efficiency |

Together the three projects cover: **attribution** (where conversions came from) +
**data quality** (is the data trustworthy) + **campaign performance** (are campaigns working).

---

## Business Outcomes

- Automated detection of 382 corrupted source records before they entered analytics
- Identified Campaign 1178 as spending 84.5% of budget while producing only 64.6% of conversions
- Identified Campaign 916 as the most efficient campaign (CPA: $6.24 vs blended $33.54)
- Flagged 6 anomalies including a zero-conversion event and a 2.6x CPA spike
- Surfaced 30-34 age group as highest-converting audience segment
- Produced automated recommendations for each campaign: Scale / Optimise / Review

---

## Dashboard Pages

| Page | Business Question Answered |
|------|---------------------------|
| Executive Overview | How are campaigns performing overall? |
| Campaign Performance | Which campaigns should I scale or pause? |
| Audience Analysis | Which audiences convert best? |
| Budget Efficiency | Where is my budget being wasted? |
| Monitoring & Data Quality | What went wrong -- in the data and in performance? |
