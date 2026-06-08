"""
app.py
------
Meta Ads Performance Analytics Pipeline -- Streamlit Dashboard

5 pages, each answering a specific business question:
  1. Executive Overview    -- "How are campaigns performing overall?"
  2. Campaign Performance  -- "Which campaigns should I scale or pause?"
  3. Audience Analysis     -- "Which audiences convert best?"
  4. Budget Efficiency     -- "Where is money being wasted?"
  5. Monitoring            -- "What went wrong and when?"

Run from project root:
    streamlit run dashboard/app.py
"""

import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# - Config -
st.set_page_config(
    page_title="Meta Ads Analytics Pipeline",
    page_icon="[chart]",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = Path(__file__).resolve().parent.parent / "warehouse" / "meta_ads.duckdb"

# - Colour palette (consistent across all charts) -
CAMPAIGN_COLORS = {"916": "#2196F3", "936": "#FF9800", "1178": "#9C27B0"}
HEALTH_COLORS   = {"Excellent": "#2e7d32", "Good": "#388e3c",
                   "Average": "#f57c00",   "Poor": "#c62828"}
SEVERITY_COLORS = {"HIGH": "#c62828", "MEDIUM": "#f57c00", "LOW": "#1565c0"}


# - Data loader (cached) -
@st.cache_data(ttl=300)
def load(query: str) -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df  = con.execute(query).df()
    con.close()
    return df


# - Shared data -
def get_kpis()       -> pd.DataFrame: return load("SELECT * FROM mart_campaign_kpis ORDER BY campaign_id")
def get_summary()    -> pd.DataFrame: return load("SELECT * FROM campaign_summary ORDER BY health_score DESC")
def get_monitoring() -> pd.DataFrame: return load("SELECT * FROM mart_campaign_monitoring ORDER BY campaign_id, date")
def get_anomalies()  -> pd.DataFrame: return load("SELECT * FROM anomaly_log ORDER BY severity, date")
def get_val_summary()-> pd.DataFrame: return load("SELECT * FROM validation_summary")
def get_audience()   -> pd.DataFrame:
    return load("""
        SELECT
            da.age_group,
            da.gender,
            SUM(f.impressions)                                              AS impressions,
            SUM(f.clicks)                                                   AS clicks,
            ROUND(SUM(f.spend), 2)                                          AS spend,
            SUM(f.approved_conversion)                                      AS conversions,
            ROUND(SUM(f.clicks)/NULLIF(SUM(f.impressions),0)*100, 4)       AS ctr_pct,
            ROUND(SUM(f.spend)/NULLIF(SUM(f.approved_conversion),0), 2)    AS cpa,
            ROUND(SUM(f.approved_conversion)/NULLIF(SUM(f.clicks),0)*100,4) AS conversion_rate_pct
        FROM fact_campaign_performance f
        JOIN dim_audience da ON f.audience_id = da.audience_id
        GROUP BY da.age_group, da.gender
        ORDER BY da.age_group, da.gender
    """)


# - Sidebar -
def sidebar():
    st.sidebar.title("Meta Ads Pipeline")
    st.sidebar.caption("Marketing Performance Analytics")
    st.sidebar.divider()

    page = st.sidebar.radio(
        "Navigate",
        [
            "Executive Overview",
            "Campaign Performance",
            "Audience Analysis",
            "Budget Efficiency",
            "Monitoring & Data Quality",
        ],
        label_visibility="collapsed",
    )

    st.sidebar.divider()
    st.sidebar.caption("Dataset: Facebook Ads | Aug 2017 | 3 campaigns | 14 days")
    st.sidebar.caption("Pipeline: DuckDB + Python + Streamlit")

    return page


# -
# PAGE 1 -- Executive Overview
# Business question: "How are my campaigns performing overall?"
# -
def page_executive():
    st.title("Executive Overview")
    st.caption("Business question: How are my campaigns performing overall?")

    kpis    = get_kpis()
    summary = get_summary()

    # - Headline KPI cards -
    total_spend   = kpis["total_spend"].sum()
    total_clicks  = kpis["total_clicks"].sum()
    total_conv    = kpis["total_approved_conv"].sum()
    avg_ctr       = (kpis["total_clicks"].sum() / kpis["total_impressions"].sum() * 100)
    blended_cpa   = total_spend / total_conv if total_conv > 0 else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Spend",       f"${total_spend:,.2f}")
    c2.metric("Total Clicks",      f"{int(total_clicks):,}")
    c3.metric("Approved Conv.",    f"{int(total_conv):,}")
    c4.metric("Blended CTR",       f"{avg_ctr:.3f}%")
    c5.metric("Blended CPA",       f"${blended_cpa:.2f}")

    st.divider()

    # - Campaign health cards -
    st.subheader("Campaign Health Scores")
    st.caption("Score 0-100. Based on normalized CTR, Conversion Rate, CPA, and CPM across campaigns.")

    cols = st.columns(3)
    for i, (_, row) in enumerate(summary.iterrows()):
        color = HEALTH_COLORS.get(row["health_label"], "#555")
        with cols[i]:
            st.markdown(f"""
            <div style="border:1px solid {color}; border-radius:8px; padding:16px; margin-bottom:8px;">
                <div style="font-size:13px; color:#888;">Campaign {row['campaign_id']}</div>
                <div style="font-size:28px; font-weight:700; color:{color};">{row['health_score']:.0f}/100</div>
                <div style="font-size:14px; color:{color}; font-weight:600;">{row['health_label']}</div>
                <div style="font-size:11px; color:#555; margin-top:6px;">
                    <b>Tier:</b> {row['performance_tier']}<br>
                    <b>Strength:</b> {row['top_strength']}<br>
                    <b>Risk:</b> {row['biggest_risk'].split(' -- ')[0] if ' -- ' in row['biggest_risk'] else row['biggest_risk'][:45]}
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # - Spend vs Conversions scatter -
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Spend vs. Conversions by Campaign")
        fig = px.scatter(
            kpis,
            x="total_spend", y="total_approved_conv",
            size="total_clicks", color="campaign_id",
            color_discrete_map=CAMPAIGN_COLORS,
            text="campaign_id",
            labels={"total_spend": "Total Spend ($)", "total_approved_conv": "Approved Conversions"},
            size_max=60,
        )
        fig.update_traces(textposition="top center")
        fig.update_layout(showlegend=False, height=320)
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("KPI Comparison by Campaign")
        metrics = kpis[["campaign_id", "ctr_pct", "cpa", "conversion_rate_pct", "cpm"]].copy()
        metrics = metrics.rename(columns={
            "ctr_pct": "CTR (%)", "cpa": "CPA ($)",
            "conversion_rate_pct": "Conv Rate (%)", "cpm": "CPM ($)"
        })
        st.dataframe(
            metrics.set_index("campaign_id").style.format("{:.4f}").background_gradient(cmap="RdYlGn", axis=0),
            use_container_width=True, height=200
        )

    # - Recommendation summary -
    st.subheader("Automated Recommendations")
    for _, row in summary.iterrows():
        color = HEALTH_COLORS.get(row["health_label"], "#555")
        icon = {"Excellent": "[OK]", "Good": "[OK]", "Average": "[WARN]", "Poor": "[POOR]"}.get(row["health_label"], "[--]")
        st.markdown(
            f"{icon} **Campaign {row['campaign_id']}** ({row['health_label']}) -- {row['recommendation']}"
        )


# -
# PAGE 2 -- Campaign Performance
# Business question: "Which campaigns should I scale or pause?"
# -
def page_campaign_performance():
    st.title("Campaign Performance")
    st.caption("Business question: Which campaigns should I scale or pause?")

    kpis       = get_kpis()
    monitoring = get_monitoring()

    # - Health score bar chart -
    col_l, col_r = st.columns([1, 1])

    with col_l:
        st.subheader("Health Score Ranking")
        fig = px.bar(
            kpis.sort_values("health_score"),
            x="health_score", y="campaign_id",
            orientation="h",
            color="campaign_id",
            color_discrete_map=CAMPAIGN_COLORS,
            text="health_score",
            labels={"health_score": "Health Score (0-100)", "campaign_id": "Campaign"},
        )
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig.add_vline(x=70, line_dash="dash", line_color="green",  annotation_text="Good threshold")
        fig.add_vline(x=50, line_dash="dash", line_color="orange", annotation_text="Average threshold")
        fig.update_layout(showlegend=False, height=280, xaxis_range=[0, 110])
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("CPA Ranking (lower = better)")
        fig = px.bar(
            kpis.sort_values("cpa", ascending=False),
            x="cpa", y="campaign_id",
            orientation="h",
            color="campaign_id",
            color_discrete_map=CAMPAIGN_COLORS,
            text="cpa",
            labels={"cpa": "Cost per Acquisition ($)", "campaign_id": "Campaign"},
        )
        fig.update_traces(texttemplate="$%{text:.2f}", textposition="outside")
        fig.update_layout(showlegend=False, height=280)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # - Score component breakdown -
    st.subheader("Health Score Component Breakdown")
    st.caption("Each component contributes 0-25 points. Transparent scoring -- no black box.")

    score_cols = ["score_ctr", "score_conversion_rate", "score_cpa", "score_cpm"]
    score_labels = ["CTR Score", "Conv Rate Score", "CPA Score", "CPM Score"]

    fig = go.Figure()
    for col, label in zip(score_cols, score_labels):
        fig.add_trace(go.Bar(
            name=label,
            x=kpis["campaign_id"],
            y=kpis[col].round(1),
            text=kpis[col].round(1),
            textposition="inside",
        ))
    fig.update_layout(
        barmode="stack",
        height=320,
        yaxis_title="Health Score (0-100)",
        xaxis_title="Campaign",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # - Daily CTR trend -
    st.subheader("Daily CTR Trend by Campaign")
    fig = px.line(
        monitoring,
        x="date", y="ctr_pct",
        color="campaign_id",
        color_discrete_map=CAMPAIGN_COLORS,
        markers=True,
        labels={"ctr_pct": "CTR (%)", "date": "Date", "campaign_id": "Campaign"},
    )
    fig.update_layout(height=320)
    st.plotly_chart(fig, use_container_width=True)

    # - Daily CPA trend -
    st.subheader("Daily CPA Trend by Campaign")
    fig = px.line(
        monitoring,
        x="date", y="cpa",
        color="campaign_id",
        color_discrete_map=CAMPAIGN_COLORS,
        markers=True,
        labels={"cpa": "CPA ($)", "date": "Date", "campaign_id": "Campaign"},
    )
    fig.update_layout(height=320)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # - Full KPI table -
    st.subheader("Full Campaign KPI Table")
    display = kpis[[
        "campaign_id", "total_spend", "total_clicks", "total_approved_conv",
        "ctr_pct", "cpc", "cpa", "conversion_rate_pct", "cpm",
        "health_score", "health_label", "performance_tier"
    ]].rename(columns={
        "campaign_id": "Campaign", "total_spend": "Spend ($)",
        "total_clicks": "Clicks", "total_approved_conv": "Conversions",
        "ctr_pct": "CTR (%)", "cpc": "CPC ($)", "cpa": "CPA ($)",
        "conversion_rate_pct": "Conv Rate (%)", "cpm": "CPM ($)",
        "health_score": "Score", "health_label": "Label", "performance_tier": "Tier"
    })
    st.dataframe(display.set_index("Campaign"), use_container_width=True)


# -
# PAGE 3 -- Audience Analysis
# Business question: "Which audiences convert best?"
# -
def page_audience():
    st.title("Audience Analysis")
    st.caption("Business question: Which audiences convert best? (Age + Gender segmentation)")

    aud = get_audience()
    aud["audience"] = aud["age_group"] + " / " + aud["gender"]

    # - Summary metrics -
    best_cpa = aud.loc[aud["cpa"].idxmin()]
    best_ctr = aud.loc[aud["ctr_pct"].idxmax()]
    best_cr  = aud.loc[aud["conversion_rate_pct"].idxmax()]
    most_conv = aud.loc[aud["conversions"].idxmax()]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lowest CPA Audience",      f"{best_cpa['age_group']} / {best_cpa['gender']}", f"${best_cpa['cpa']:.2f}")
    c2.metric("Highest CTR Audience",     f"{best_ctr['age_group']} / {best_ctr['gender']}", f"{best_ctr['ctr_pct']:.4f}%")
    c3.metric("Best Conv Rate Audience",  f"{best_cr['age_group']} / {best_cr['gender']}",   f"{best_cr['conversion_rate_pct']:.2f}%")
    c4.metric("Most Conversions",         f"{most_conv['age_group']} / {most_conv['gender']}", f"{int(most_conv['conversions'])}")

    st.divider()

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Conversions by Age Group")
        age_agg = aud.groupby("age_group").agg(
            conversions=("conversions", "sum"),
            spend=("spend", "sum"),
            cpa=("cpa", "mean"),
        ).reset_index()
        fig = px.bar(
            age_agg.sort_values("conversions", ascending=False),
            x="age_group", y="conversions",
            color="age_group",
            text="conversions",
            labels={"age_group": "Age Group", "conversions": "Approved Conversions"},
        )
        fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
        fig.update_layout(showlegend=False, height=320)
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("CPA by Age Group")
        fig = px.bar(
            age_agg.sort_values("cpa"),
            x="age_group", y="cpa",
            color="age_group",
            text="cpa",
            labels={"age_group": "Age Group", "cpa": "Avg. CPA ($)"},
        )
        fig.update_traces(texttemplate="$%{text:.2f}", textposition="outside")
        fig.update_layout(showlegend=False, height=320)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Gender Performance Comparison")
        gender_agg = aud.groupby("gender").agg(
            spend=("spend", "sum"),
            conversions=("conversions", "sum"),
            ctr=("ctr_pct", "mean"),
            cpa=("cpa", "mean"),
        ).reset_index()

        fig = px.bar(
            gender_agg,
            x="gender", y=["ctr", "cpa"],
            barmode="group",
            labels={"gender": "Gender", "value": "Metric Value", "variable": "KPI"},
        )
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("Spend vs. Conversions by Audience")
        fig = px.scatter(
            aud,
            x="spend", y="conversions",
            color="age_group",
            symbol="gender",
            text="audience",
            size="conversions",
            size_max=40,
            labels={"spend": "Spend ($)", "conversions": "Approved Conversions"},
        )
        fig.update_traces(textposition="top center")
        fig.update_layout(height=320)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # - CTR heatmap: age x gender -
    st.subheader("CTR Heatmap -- Age x Gender")
    st.caption("Darker = higher CTR. Identifies which audience combinations engage most with ads.")

    pivot = aud.pivot(index="age_group", columns="gender", values="ctr_pct").fillna(0)
    fig = px.imshow(
        pivot,
        text_auto=".4f",
        color_continuous_scale="Blues",
        labels={"x": "Gender", "y": "Age Group", "color": "CTR (%)"},
        aspect="auto",
    )
    fig.update_layout(height=280)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Full Audience KPI Table")
    display = aud[[
        "audience", "spend", "clicks", "conversions",
        "ctr_pct", "cpa", "conversion_rate_pct"
    ]].rename(columns={
        "audience": "Audience", "spend": "Spend ($)", "clicks": "Clicks",
        "conversions": "Conversions", "ctr_pct": "CTR (%)",
        "cpa": "CPA ($)", "conversion_rate_pct": "Conv Rate (%)"
    }).sort_values("CPA ($)")
    st.dataframe(display.set_index("Audience"), use_container_width=True)


# -
# PAGE 4 -- Budget Efficiency
# Business question: "Where is my budget being wasted?"
# -
def page_budget():
    st.title("Budget Efficiency")
    st.caption("Business question: Where is my budget being wasted -- and where should I invest more?")

    kpis    = get_kpis()
    summary = get_summary()

    # - Spend distribution -
    total_spend = kpis["total_spend"].sum()

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Spend Distribution by Campaign")
        fig = px.pie(
            kpis,
            names="campaign_id", values="total_spend",
            color="campaign_id",
            color_discrete_map=CAMPAIGN_COLORS,
            hole=0.45,
        )
        fig.update_traces(textinfo="label+percent")
        fig.update_layout(height=340, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("Conversion Distribution by Campaign")
        fig = px.pie(
            kpis,
            names="campaign_id", values="total_approved_conv",
            color="campaign_id",
            color_discrete_map=CAMPAIGN_COLORS,
            hole=0.45,
        )
        fig.update_traces(textinfo="label+percent")
        fig.update_layout(height=340, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # - Efficiency quadrant -
    st.divider()
    st.subheader("Budget Efficiency Quadrant")
    st.caption(
        "X-axis: Spend share (% of total budget). "
        "Y-axis: Conversion share (% of total conversions). "
        "Dots above the diagonal = efficient. Below = inefficient."
    )

    kpis = kpis.copy()
    total_conv = kpis["total_approved_conv"].sum()
    kpis["spend_share"]  = kpis["total_spend"] / total_spend * 100
    kpis["conv_share"]   = kpis["total_approved_conv"] / total_conv * 100
    kpis["efficiency"]   = kpis["conv_share"] - kpis["spend_share"]   # positive = efficient

    fig = px.scatter(
        kpis,
        x="spend_share", y="conv_share",
        color="campaign_id",
        color_discrete_map=CAMPAIGN_COLORS,
        size="total_spend",
        text="campaign_id",
        size_max=60,
        labels={
            "spend_share": "Spend Share (%)",
            "conv_share": "Conversion Share (%)",
        },
    )
    # Add diagonal (equal efficiency line)
    fig.add_shape(type="line", x0=0, y0=0, x1=100, y1=100,
                  line=dict(color="gray", dash="dash"))
    fig.add_annotation(x=70, y=75, text="Equal Efficiency Line",
                       showarrow=False, font=dict(color="gray", size=10))
    fig.update_traces(textposition="top center")
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # - Efficiency table -
    st.subheader("Budget Efficiency Summary")
    eff_table = kpis[[
        "campaign_id", "total_spend", "total_approved_conv",
        "spend_share", "conv_share", "efficiency", "cpa"
    ]].copy()
    eff_table["efficiency_flag"] = eff_table["efficiency"].apply(
        lambda x: "Over-performing" if x > 5 else ("Under-performing" if x < -5 else "Balanced")
    )
    eff_table = eff_table.rename(columns={
        "campaign_id": "Campaign", "total_spend": "Spend ($)",
        "total_approved_conv": "Conversions",
        "spend_share": "Spend Share (%)", "conv_share": "Conv Share (%)",
        "efficiency": "Efficiency Gap", "cpa": "CPA ($)",
        "efficiency_flag": "Budget Verdict"
    })
    st.dataframe(eff_table.set_index("Campaign").style.format({
        "Spend ($)": "${:.2f}", "Spend Share (%)": "{:.1f}%",
        "Conv Share (%)": "{:.1f}%", "Efficiency Gap": "{:+.1f}",
        "CPA ($)": "${:.2f}"
    }), use_container_width=True)

    st.divider()

    # - Recommendations -
    st.subheader("Automated Budget Recommendations")
    for _, row in summary.iterrows():
        color = HEALTH_COLORS.get(row["health_label"], "#555")
        icon  = {"Excellent": "[OK]", "Good": "[OK]", "Average": "[WARN]", "Poor": "[POOR]"}.get(row["health_label"], "[--]")
        with st.container():
            st.markdown(
                f"{icon} **Campaign {row['campaign_id']}** -- {row['recommendation']}"
            )
            st.caption(f"Biggest risk: {row['biggest_risk']}")
            st.divider()


# -
# PAGE 5 -- Monitoring & Data Quality
# Business question: "What went wrong -- in the data and in campaign performance?"
# -
def page_monitoring():
    st.title("Monitoring & Data Quality")
    st.caption("Business question: What went wrong -- in the data pipeline and in campaign performance?")

    val    = get_val_summary()
    anom   = get_anomalies()
    mon    = get_monitoring()

    # - Data quality summary -
    st.subheader("Pipeline Data Quality Report")
    st.caption(
        "During profiling, 33% of source records were found to be malformed. "
        "They were automatically detected and excluded before loading. "
        "This approach was inspired by the Automated Data Quality Monitoring Framework (Project 2)."
    )

    if not val.empty:
        row = val.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Source Rows",   f"{int(row['total_rows']):,}")
        c2.metric("Valid Rows Loaded",   f"{int(row['valid_rows']):,}")
        c3.metric("Rejected Rows",       f"{int(row['rejected_rows']):,}",
                  delta=f"-{row['pct_rejected']:.1f}%", delta_color="inverse")
        c4.metric("Invalid Campaign IDs", f"{int(row['reason_invalid_campaign']):,}")

    # Rejection pie chart
    if not val.empty:
        row = val.iloc[0]
        reasons = {
            "Invalid Campaign ID": int(row["reason_invalid_campaign"]),
            "Null Conversion":     int(row["reason_null_conversion"]),
            "Negative Spend":      int(row["reason_negative_spend"]),
            "Duplicate Record":    int(row["reason_duplicate"]),
        }
        reasons = {k: v for k, v in reasons.items() if v > 0}
        if reasons:
            col_l, col_r = st.columns([1, 2])
            with col_l:
                fig = px.pie(
                    names=list(reasons.keys()),
                    values=list(reasons.values()),
                    title="Rejection Reasons",
                    hole=0.4,
                    color_discrete_sequence=["#c62828", "#f57c00", "#1565c0", "#555"],
                )
                fig.update_layout(height=280, showlegend=True)
                st.plotly_chart(fig, use_container_width=True)
            with col_r:
                st.markdown("#### What were the corrupted rows?")
                st.markdown("""
                **382 rows had their columns shifted left by one position.**

                In those rows:
                - `campaign_id` contained an age bracket value (e.g., `45-49`)
                - `fb_campaign_id` contained `M` or `F` (gender values)
                - `total_conversion` and `approved_conversion` were missing

                This is consistent with a CSV export where one column was dropped
                at the source, shifting all subsequent columns left.

                **Action taken:** All 382 rows logged to `validation_log` with
                reason `invalid_campaign_id` and excluded from the warehouse.
                """)

    st.divider()

    # - Anomaly detection -
    st.subheader("Anomaly Detection Log")
    st.caption("Rule-based detection -- no machine learning. Thresholds are transparent and explainable.")

    if anom.empty:
        st.info("No anomalies detected.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Anomalies",    len(anom))
        c2.metric("High Severity",      len(anom[anom["severity"] == "HIGH"]))
        c3.metric("Medium Severity",    len(anom[anom["severity"] == "MEDIUM"]))

        # Anomaly bar chart
        anom_counts = anom.groupby(["anomaly_type", "severity"]).size().reset_index(name="count")
        fig = px.bar(
            anom_counts,
            x="anomaly_type", y="count",
            color="severity",
            color_discrete_map=SEVERITY_COLORS,
            text="count",
            labels={"anomaly_type": "Anomaly Type", "count": "Occurrences"},
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(height=300, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

        # Anomaly table
        display = anom[["campaign_id", "date", "anomaly_type", "severity", "description"]].rename(columns={
            "campaign_id": "Campaign", "date": "Date",
            "anomaly_type": "Type", "severity": "Severity", "description": "Detail"
        })
        st.dataframe(display, use_container_width=True, hide_index=True)

    st.divider()

    # - Daily spend trend (to visualise spend spike context) -
    st.subheader("Daily Spend Trend (for context)")
    fig = px.area(
        mon,
        x="date", y="spend",
        color="campaign_id",
        color_discrete_map=CAMPAIGN_COLORS,
        labels={"spend": "Daily Spend ($)", "date": "Date", "campaign_id": "Campaign"},
    )
    fig.update_layout(height=300)
    st.plotly_chart(fig, use_container_width=True)

    # - Anomaly rules reference -
    st.divider()
    st.subheader("Anomaly Detection Rules Reference")
    rules = pd.DataFrame([
        {"Rule": "CTR_DROP",        "Condition": "Daily CTR < 70% of 3-day rolling average",       "Severity": "HIGH"},
        {"Rule": "CPA_SPIKE",       "Condition": "Daily CPA > 150% of 3-day rolling average",       "Severity": "HIGH"},
        {"Rule": "SPEND_SPIKE",     "Condition": "Daily spend > 3x campaign average daily spend",   "Severity": "MEDIUM"},
        {"Rule": "ZERO_CONVERSIONS","Condition": "Approved conversions = 0 where spend > $0",        "Severity": "HIGH"},
    ])
    st.dataframe(rules, use_container_width=True, hide_index=True)


# -
# Router
# -
def main():
    page = sidebar()
    if page == "Executive Overview":
        page_executive()
    elif page == "Campaign Performance":
        page_campaign_performance()
    elif page == "Audience Analysis":
        page_audience()
    elif page == "Budget Efficiency":
        page_budget()
    elif page == "Monitoring & Data Quality":
        page_monitoring()


if __name__ == "__main__":
    main()
