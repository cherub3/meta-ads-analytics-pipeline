# Interview Preparation
## Meta Ads Performance Analytics Pipeline

---

## Resume Bullets

Use these on your CV under a "Projects" section.
Pick 3-4 that match the role you are applying for.

**For Data Engineer roles:**
- Built an end-to-end marketing data pipeline in Python and DuckDB, implementing a
  medallion architecture (Bronze / Silver / Gold) that processes Facebook ad campaign
  data through validation, transformation, KPI calculation, and anomaly detection stages
- Implemented checkpoint-based incremental loading that filters source records by
  last-loaded watermark, preventing duplicate ingestion across pipeline runs
- Designed and executed a validation layer that detected and logged 382 malformed source
  records (33% of input) before warehouse load, with per-row rejection reasons stored in
  an audit table

**For Analytics Engineer roles:**
- Modelled Facebook Ads data into a dimensional schema (dim_campaign, dim_audience,
  fact_campaign_performance) in DuckDB using SQL, reducing 761 ad-level rows to 133
  rows at campaign x date x audience grain
- Engineered a Campaign Health Score (0-100) using min-max normalisation across CTR,
  CPA, Conversion Rate, and CPM, with transparent component scoring to support
  business explainability
- Authored 13 named business SQL analyses covering campaign efficiency, audience
  segmentation, budget concentration risk, and day-over-day CTR change

**For Marketing Data Engineer roles:**
- Built a campaign performance analytics pipeline for Facebook Ads data, calculating
  CTR, CPC, CPA, Conversion Rate, and CPM across 3 campaigns and 8 audience segments
  over 14 days
- Implemented rule-based anomaly detection (no ML) that flagged 6 real performance
  events including zero-conversion periods and a 2.6x CPA spike on Campaign 936
- Developed automated budget efficiency analysis that identified Campaign 1178 as
  consuming 84.5% of total spend while generating only 64.6% of conversions, with
  recommendations generated programmatically per campaign

**For Performance Marketing Data Engineer roles:**
- Automated marketing performance reporting for a 3-campaign Facebook Ads portfolio,
  replacing manual CSV exports with a pipeline that runs end-to-end in under 2 seconds
- Produced audience performance analysis across age and gender segments, identifying
  the 30-34 age group as the highest-converting audience and surfacing CPA by segment
  for targeting optimisation
- Delivered a 5-page Streamlit dashboard answering executive, campaign, audience,
  budget, and monitoring questions directly from a local DuckDB warehouse


---

## GitHub Repository Description

**One-line description (for repo subtitle):**
End-to-end Facebook Ads analytics pipeline -- validation, DuckDB warehouse, KPI scoring, anomaly detection, and Streamlit dashboard.

**About section (300 characters):**
Marketing data pipeline in Python + DuckDB. Ingests Facebook Ads data through a Bronze/Silver/Gold architecture. Calculates CTR, CPA, Conversion Rate, CPM. Health scores campaigns 0-100. Detects anomalies. 5-page Streamlit dashboard.

**Topics / Tags to add to the repo:**
data-engineering, analytics-engineering, marketing-analytics, duckdb, streamlit, python,
etl, facebook-ads, campaign-analytics, kpi, anomaly-detection, data-quality, portfolio

**README headline finding to pin:**
> 33% of source records were automatically detected as malformed and excluded before
> loading. Campaign 1178 consumed 84.5% of budget while generating only 64.6% of
> conversions. Campaign 916 achieved a CPA 7x lower at $6.24.


---

## Architecture Diagram (Text Version for README or Slides)

```
[Facebook Ads CSV]
        |
        |  1,143 rows (raw)
        v
+------------------+
|  01_validate.py  |  <-- Validation Layer
|  382 rejected    |      Rule: invalid_campaign_id
|  761 accepted    |      Output: validation_log, validation_summary
+------------------+
        |
        v
+------------------+
|  02_ingest.py    |  <-- Bronze Layer (Incremental)
|  Checkpoint-     |      Append-only table: raw_campaign_performance
|  based load      |      Watermark: checkpoints/last_loaded_date.txt
+------------------+
        |
        v
+------------------+
|  03_transform.py |  <-- Silver Layer (Dimensional Model)
|  dim_campaign    |      3 rows
|  dim_audience    |      8 rows
|  fact_campaign_  |      133 rows (aggregated grain)
|  performance     |
+------------------+
        |
        v
+------------------+
|  04_mart.py      |  <-- Gold Layer (Analytics Mart)
|  mart_kpis       |      CTR, CPC, CPA, Conv Rate, CPM
|  mart_monitoring |      Daily trends + rolling averages
|  campaign_summary|      Health score + recommendation
+------------------+
        |
        v
+------------------+
|  05_anomaly.py   |  <-- Anomaly Detection
|  anomaly_log     |      6 anomalies: CTR drops, CPA spikes,
|                  |      zero-conversion events
+------------------+
        |
        v
+------------------+
|  dashboard/      |  <-- Streamlit Dashboard (5 pages)
|  app.py          |      Executive / Campaign / Audience /
|                  |      Budget / Monitoring
+------------------+
```


---

## Top Interview Questions and Answers

---

### Q1: Why did you choose DuckDB instead of PostgreSQL or SQLite?

**Answer:**

DuckDB is an embedded analytical database -- it runs in-process with Python, requires no
server setup, and is optimised for column-scan analytical queries rather than row-level
transactional writes. For a local analytics pipeline working with a dataset that fits in
memory, DuckDB is the right tool.

SQLite is also embedded but is optimised for OLTP (row-by-row operations). It would work
but is slower for the aggregation-heavy queries this pipeline runs -- window functions,
group-by aggregations, multi-table joins.

PostgreSQL would require running a server, managing credentials, and setting up a database.
That is unnecessary complexity for a local portfolio project and would make it harder for
a recruiter to run the project themselves.

In production, if the dataset grew to billions of rows, I would move the warehouse to
BigQuery or Snowflake. The SQL and Python logic would barely change -- just the connection
string. That is one of DuckDB's strengths: it is a stepping stone to production analytical
databases, not a toy.

---

### Q2: Why these KPIs specifically? Why not ROAS or ROI?

**Answer:**

The dataset does not contain revenue. ROAS (Return on Ad Spend = Revenue / Spend) and ROI
(Return on Investment = (Revenue - Spend) / Spend) both require a revenue figure. Including
them would require me to simulate or assume revenue, which would make my findings
unreliable and potentially misleading.

I chose the five KPIs the data actually supports:
- CTR measures ad relevance
- CPC measures click efficiency
- CPA measures acquisition efficiency -- the most important metric for conversion campaigns
- Conversion Rate measures audience quality
- CPM measures reach efficiency

A recruiter or interviewer can verify every number I report because every formula uses only
columns that exist in the source data. That is more impressive than a dashboard full of
made-up ROAS figures.

---

### Q3: How exactly is the Campaign Health Score calculated? Walk me through it.

**Answer:**

The score has four components, each worth 0 to 25 points, totalling 100.

I used min-max normalisation. For a metric where higher is better -- CTR and Conversion Rate:

  Score = (campaign_value - min_value) / (max_value - min_value) x 25

For metrics where lower is better -- CPA and CPM -- I inverted the formula:

  Score = (max_value - campaign_value) / (max_value - min_value) x 25

This means the campaign with the best CTR always gets 25 CTR points. The campaign with the
worst CTR gets 0. The middle campaign lands proportionally between them.

The total health score is the sum: CTR score + Conversion Rate score + CPA score + CPM score.

With 3 campaigns, Campaign 916 scores 82 (Good), Campaign 936 scores 51 (Average), and
Campaign 1178 scores 25 (Poor).

I chose normalisation over fixed thresholds because I have no external benchmark data. I
do not know what a "good" CTR is for this industry in 2017. Relative scoring is honest --
it tells you which campaign is performing best within this portfolio, without pretending to
have benchmark knowledge I do not have.

---

### Q4: Which campaign performed best and which should be paused?

**Answer:**

Campaign 916 performed best. It has the lowest CPA ($6.24), the highest conversion rate
(21.2%), and a health score of 82/100 (Good). Despite being the smallest campaign by spend
-- $149.71 over 14 days -- it generates the most conversions per dollar. My recommendation
is to scale its budget.

Campaign 1178 is the strongest candidate for review or pause. It accounts for 84.5% of
total spend ($16,577) but generates only 64.6% of total conversions (378 of 585). Its CPA
of $43.85 is seven times higher than Campaign 916. The pipeline flags it as a Poor Performer
with a health score of 25/100. Before pausing, I would investigate whether the campaign
serves a different objective -- awareness rather than conversion -- but based on the metrics
available, the spend is not justified by the results.

---

### Q5: How does incremental loading work in this pipeline?

**Answer:**

The pipeline stores the last successfully loaded date in a flat file:
`checkpoints/last_loaded_date.txt`.

On each run, the ingestion script reads that date, filters the source data to only rows
where `reporting_start` is greater than the checkpoint date, loads those rows into the
bronze table, then updates the checkpoint to the maximum date in the new batch.

On the first run with the checkpoint set to `1900-01-01`, all 761 valid rows are loaded.
On a second run, the checkpoint is `2017-08-30` (the last date in the dataset), so zero
rows pass the filter and the pipeline exits cleanly with a message that it is up to date.

In production, this checkpoint would live in a metadata table in the warehouse rather than
a flat file. The pattern is the same as a high-water mark in streaming systems. The key
benefit is that you never reload data you have already processed, which makes the pipeline
efficient and idempotent.

---

### Q6: How does this project connect to your Attribution Warehouse project?

**Answer:**

They answer different questions about the same ecosystem.

The Attribution Warehouse focuses on the question: where did a conversion come from? It
models the customer journey across touchpoints -- first click, last click, linear, time-decay
-- and attributes credit to channels.

This project focuses on the question: how efficiently is each campaign running? It does not
care about attribution -- it takes conversions as a given and measures the cost, rate, and
consistency of generating them.

In a real marketing data stack these would be two separate marts in the same warehouse.
The Attribution mart tells you which channels to invest in. The Campaign Performance mart
tells you whether those channels are running efficiently once you have invested in them.
They are complementary, not overlapping.

---

### Q7: How does this project connect to your Data Quality Framework?

**Answer:**

The Data Quality Framework established a pattern: every validation check produces an
explicit result -- pass or fail -- and every failure is logged with a reason. Nothing is
silently dropped.

This project applies that same pattern in a pipeline context. When the validation layer
finds a malformed row, it does not discard it quietly. It writes it to `validation_log`
with a specific rejection reason (`invalid_campaign_id`, `null_conversion`, etc.) and
summarises the run in `validation_summary`. The monitoring page of the dashboard surfaces
this directly so a user can see exactly how many records were rejected and why.

The conceptual connection is explicit in the README: the validation approach was inspired
by Project 2. The difference is that Project 2 builds a general-purpose DQ framework,
while this project applies DQ thinking to a specific pipeline with specific business data.
That is a realistic division of responsibility -- a DQ framework defines the patterns, and
individual pipelines implement them.

---

### Q8: The dataset only has 761 rows and 3 campaigns. Is that too small?

**Answer:**

The size of the dataset is less important than what you do with it.

A pipeline that validates, stages, transforms, aggregates, scores, and monitors 761 rows
demonstrates the same engineering patterns as one processing 761 million rows. The
architecture -- Bronze / Silver / Gold layers, incremental loading, dimensional modelling,
anomaly detection -- scales to any volume. The SQL and Python code changes minimally; the
infrastructure changes.

What matters is that the pipeline produces correct, trustworthy outputs and that I can
explain every design decision. The small dataset actually helps in an interview because I
can show the actual numbers and explain exactly why Campaign 916 scores 82 and Campaign
1178 scores 25.

If this were a production system, I would add partitioning, scheduling (Prefect or
Dagster, not Airflow -- that would be overengineering for this scale), and move DuckDB to
BigQuery or Snowflake. I would also seek a longer time window and more campaigns to make
the anomaly detection more meaningful.

---

### Q9: What would you improve if this were a production system?

**Answer:**

Five things, in priority order:

1. **Scheduler.** Right now the pipeline is triggered manually. In production I would add
   a lightweight scheduler -- Prefect or Dagster -- to run it daily at a set time. Not
   Airflow; that is overengineered for a single-pipeline local system.

2. **Metadata table for checkpoints.** The flat-file checkpoint works but is fragile. In
   production the watermark would live in a `pipeline_runs` metadata table in the
   warehouse, with columns for run timestamp, rows loaded, and status.

3. **Alert delivery.** The anomaly log exists but a marketing manager should not have to
   open the dashboard to see it. In production I would add email or Slack alerts triggered
   when a HIGH severity anomaly is detected.

4. **Revenue data.** The dataset has no revenue column. In production, the Facebook Ads
   data would be joined to an orders or CRM table to bring in actual revenue per
   conversion. That would unlock ROAS and ROI, which are the metrics marketing managers
   care about most.

5. **dbt for transformations.** The SQL in `03_transform.py` and `04_mart.py` would move
   to dbt models. dbt adds version control for SQL, automatic documentation, lineage
   graphs, and built-in testing. For a portfolio project it adds unnecessary setup; for a
   production team it is essential.

---

## Quick-Reference Card (for the day before the interview)

| Question topic          | One-line answer                                            |
|-------------------------|------------------------------------------------------------|
| Why DuckDB?             | Embedded, no server, columnar, perfect for local analytics |
| Why these KPIs?         | Only KPIs the data supports -- no simulated revenue        |
| How is health score built? | Min-max normalisation across CTR, Conv Rate, CPA, CPM  |
| Best campaign?          | Campaign 916 -- CPA $6.24, conversion rate 21.2%           |
| Worst campaign?         | Campaign 1178 -- 84.5% spend, 64.6% conversions, CPA $43  |
| How does incremental loading work? | Checkpoint file stores last date; filter on load|
| How many anomalies found? | 6 -- CTR drops, CPA spike, zero-conversion events        |
| How many records rejected? | 382 (33.4%) -- column-shifted rows with bad campaign ID|
| Connection to Project 1? | Attribution answers "where from?", this answers "how well?" |
| Connection to Project 2? | Same reject-and-log DQ pattern applied to pipeline context |
| What would you add in prod? | Scheduler, metadata watermarks, revenue join, dbt, alerts |
