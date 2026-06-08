-- queries.sql
-- Named business analyses for the Meta Ads Performance Analytics Pipeline
-- Run against warehouse/meta_ads.duckdb
-- Each query answers a specific business question.
-- ============================================================


-- ============================================================
-- 1. Campaign KPI Overview
-- Business question: What are the core metrics for each campaign?
-- ============================================================
SELECT
    campaign_id,
    total_spend,
    total_clicks,
    total_approved_conv                 AS conversions,
    ROUND(ctr_pct, 4)                   AS ctr_pct,
    ROUND(cpc, 2)                       AS cpc,
    ROUND(cpa, 2)                       AS cpa,
    ROUND(conversion_rate_pct, 4)       AS conversion_rate_pct,
    ROUND(cpm, 4)                       AS cpm,
    health_score,
    health_label
FROM mart_campaign_kpis
ORDER BY health_score DESC;


-- ============================================================
-- 2. Top Campaigns by Approved Conversions
-- Business question: Which campaign generates the most verified results?
-- ============================================================
SELECT
    campaign_id,
    total_approved_conv                 AS conversions,
    total_spend,
    ROUND(cpa, 2)                       AS cpa,
    health_label
FROM mart_campaign_kpis
ORDER BY total_approved_conv DESC;


-- ============================================================
-- 3. Lowest CPA Campaigns
-- Business question: Which campaigns acquire customers most cheaply?
-- ============================================================
SELECT
    campaign_id,
    ROUND(cpa, 2)                       AS cpa,
    total_approved_conv                 AS conversions,
    total_spend,
    ROUND(conversion_rate_pct, 2)       AS conversion_rate_pct,
    health_label
FROM mart_campaign_kpis
ORDER BY cpa ASC;


-- ============================================================
-- 4. Highest CTR Campaigns
-- Business question: Which campaigns produce the most engaging ads?
-- ============================================================
SELECT
    campaign_id,
    ROUND(ctr_pct, 4)                   AS ctr_pct,
    total_impressions,
    total_clicks,
    health_label
FROM mart_campaign_kpis
ORDER BY ctr_pct DESC;


-- ============================================================
-- 5. Budget Efficiency Analysis
-- Business question: Which campaigns return the most value per dollar spent?
-- ============================================================
SELECT
    campaign_id,
    total_spend,
    ROUND(total_spend / SUM(total_spend) OVER () * 100, 1)          AS spend_share_pct,
    total_approved_conv,
    ROUND(total_approved_conv / SUM(total_approved_conv) OVER () * 100, 1) AS conv_share_pct,
    ROUND(
        (total_approved_conv / SUM(total_approved_conv) OVER ())
        - (total_spend / SUM(total_spend) OVER ()), 4
    )                                                                AS efficiency_gap,
    ROUND(cpa, 2)                                                    AS cpa,
    performance_tier,
    recommendation
FROM mart_campaign_kpis
ORDER BY efficiency_gap DESC;


-- ============================================================
-- 6. Audience Performance -- Age Group
-- Business question: Which age groups convert best?
-- ============================================================
SELECT
    da.age_group,
    SUM(f.approved_conversion)                                       AS conversions,
    ROUND(SUM(f.spend), 2)                                           AS spend,
    ROUND(SUM(f.clicks) / NULLIF(SUM(f.impressions), 0) * 100, 4)   AS ctr_pct,
    ROUND(SUM(f.spend) / NULLIF(SUM(f.approved_conversion), 0), 2)  AS cpa,
    ROUND(SUM(f.approved_conversion) / NULLIF(SUM(f.clicks), 0) * 100, 2)
                                                                     AS conversion_rate_pct
FROM fact_campaign_performance f
JOIN dim_audience da ON f.audience_id = da.audience_id
GROUP BY da.age_group
ORDER BY conversions DESC;


-- ============================================================
-- 7. Audience Performance -- Age x Gender
-- Business question: Which specific audience segment has the lowest CPA?
-- ============================================================
SELECT
    da.age_group,
    da.gender,
    SUM(f.approved_conversion)                                       AS conversions,
    ROUND(SUM(f.spend), 2)                                           AS spend,
    ROUND(SUM(f.clicks) / NULLIF(SUM(f.impressions), 0) * 100, 4)   AS ctr_pct,
    ROUND(SUM(f.spend) / NULLIF(SUM(f.approved_conversion), 0), 2)  AS cpa,
    ROUND(SUM(f.approved_conversion) / NULLIF(SUM(f.clicks), 0) * 100, 2)
                                                                     AS conversion_rate_pct
FROM fact_campaign_performance f
JOIN dim_audience da ON f.audience_id = da.audience_id
GROUP BY da.age_group, da.gender
ORDER BY cpa ASC;


-- ============================================================
-- 8. Daily Performance Trends
-- Business question: How is campaign performance changing day by day?
-- ============================================================
SELECT
    campaign_id,
    date,
    ROUND(spend, 2)                     AS spend,
    clicks,
    approved_conversion,
    ROUND(ctr_pct, 4)                   AS ctr_pct,
    ROUND(cpa, 2)                       AS cpa,
    ROUND(ctr_3day_avg, 4)              AS ctr_3day_avg,
    ROUND(cpa_3day_avg, 2)              AS cpa_3day_avg
FROM mart_campaign_monitoring
ORDER BY campaign_id, date;


-- ============================================================
-- 9. Campaign Health Score Ranking
-- Business question: Which campaigns are healthy and which need attention?
-- ============================================================
SELECT
    cs.campaign_id,
    cs.health_score,
    cs.health_label,
    cs.performance_tier,
    cs.top_strength,
    cs.biggest_risk,
    cs.recommendation,
    mk.ctr_pct,
    mk.cpa,
    mk.conversion_rate_pct
FROM campaign_summary cs
JOIN mart_campaign_kpis mk ON cs.campaign_id = mk.campaign_id
ORDER BY cs.health_score DESC;


-- ============================================================
-- 10. Anomaly Report
-- Business question: When did campaign performance behave abnormally?
-- ============================================================
SELECT
    campaign_id,
    date,
    anomaly_type,
    severity,
    ROUND(metric_value, 4)              AS metric_value,
    ROUND(baseline, 4)                  AS baseline,
    description
FROM anomaly_log
ORDER BY
    CASE severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
    campaign_id,
    date;


-- ============================================================
-- 11. Data Quality Summary
-- Business question: How clean was the source data?
-- ============================================================
SELECT
    run_timestamp,
    total_rows,
    valid_rows,
    rejected_rows,
    pct_rejected,
    reason_invalid_campaign,
    reason_null_conversion,
    reason_negative_spend,
    reason_duplicate
FROM validation_summary;


-- ============================================================
-- 12. Day-over-Day CTR Change
-- Business question: Is CTR improving or declining across the campaign window?
-- ============================================================
SELECT
    campaign_id,
    date,
    ROUND(ctr_pct, 4)                                               AS ctr_pct,
    LAG(ctr_pct) OVER (PARTITION BY campaign_id ORDER BY date)      AS prev_ctr_pct,
    ROUND(
        ctr_pct - LAG(ctr_pct) OVER (PARTITION BY campaign_id ORDER BY date),
        4
    )                                                               AS ctr_change,
    ROUND(
        (ctr_pct - LAG(ctr_pct) OVER (PARTITION BY campaign_id ORDER BY date))
        / NULLIF(LAG(ctr_pct) OVER (PARTITION BY campaign_id ORDER BY date), 0) * 100,
        2
    )                                                               AS ctr_pct_change
FROM mart_campaign_monitoring
ORDER BY campaign_id, date;


-- ============================================================
-- 13. Spend Concentration Risk
-- Business question: Is the portfolio over-reliant on one campaign?
-- ============================================================
SELECT
    campaign_id,
    total_spend,
    ROUND(total_spend / SUM(total_spend) OVER () * 100, 1)  AS spend_share_pct,
    health_label,
    CASE
        WHEN total_spend / SUM(total_spend) OVER () > 0.7
             AND health_label = 'Poor'
        THEN 'HIGH RISK -- dominant spend + poor health'
        WHEN total_spend / SUM(total_spend) OVER () > 0.5
        THEN 'MEDIUM RISK -- high spend concentration'
        ELSE 'LOW RISK'
    END                                                      AS concentration_risk
FROM mart_campaign_kpis
ORDER BY total_spend DESC;
