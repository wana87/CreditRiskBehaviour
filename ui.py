"""Presentation helpers; feature calculations remain in engine.py."""
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


def apply_styles(root):
    st.html("<style>" + (Path(root) / "styles.css").read_text(encoding="utf-8") + "</style>")


def hero():
    st.html('''<section class="profile-hero" aria-label="Credit Behaviour Profiler">
      <div class="hero-eyebrow">Borrower intelligence workspace</div>
      <h1>📊 Credit Behaviour Profiler</h1>
      <p>Explore payment behaviour, understand facility exposure, and trace every insight back to the report.</p>
      <div class="hero-pills"><span>🏦 Facility snapshots</span><span>📅 24-month history</span><span>🔎 Traceable features</span></div>
    </section>''')


def borrower_heading(features):
    name = features.get("borrower.display_name") or "Unnamed borrower"
    initial = escape(str(name).strip()[:1].upper())
    report = escape(str(features.get("transaction.id", "")))
    period = escape(str(features.get("report.analysis_period", "")))
    date = escape(str(features.get("transaction.date", "")))
    st.html(f'''<div class="borrower-heading"><div class="borrower-avatar" aria-hidden="true">{initial}</div>
      <div><h2>{escape(str(name))}</h2><p>{report} &nbsp; · &nbsp; Analysis: {period}<br>Report date: {date}</p></div></div>''')


def observations(features):
    rate = features.get("delinquency_rate_24m")
    delinquent = features.get("delinquent_slot_count_24m", 0)
    reported = features.get("reported_slot_count_24m", 0)
    recency = features.get("months_since_last_delinquency")
    if reported == 0:
        recency_value = "No reported observations"
        recency_detail = "A payment history conclusion is not available for this window."
    elif recency is None:
        recency_value = "No delinquency observed"
        recency_detail = "Within the reported 24-month window. This does not describe periods outside that window."
    elif recency == 0:
        recency_value = "Observed in the analysis month"
        recency_detail = "At least one reported facility had overdue days in the latest month."
    else:
        recency_value = f"{recency} months since last delinquency"
        recency_detail = "Measured from the analysis period, across reported facilities."
    rows = [
        ("📅 Reported payment history", f"{reported:,} facility-month slots", "Only REPORTED observations contribute to payment-window metrics."),
        ("🕒 Delinquency rate · 24m", "N/A" if rate is None else f"{rate:.2%}", f"{delinquent:,} delinquent slots out of {reported:,} reported slots."),
        ("🔎 Most recent delinquency", recency_value, recency_detail),
    ]
    st.html("".join(f'<div class="observation"><div class="obs-label">{escape(label)}</div>'
                    f'<div class="obs-value">{escape(value)}</div><div class="obs-detail">{escape(detail)}</div></div>'
                    for label, value, detail in rows))


def window_chart(features):
    data = pd.DataFrame([{"Window": f"{months} months", "Maximum DPD": features.get(f"max_dpd_{months}m")}
                         for months in (3, 12, 24)])
    chart = alt.Chart(data).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, size=60).encode(
        x=alt.X("Window:N", sort=["3 months", "12 months", "24 months"], axis=alt.Axis(labelAngle=0), title=None),
        y=alt.Y("Maximum DPD:Q", title="Days past due", scale=alt.Scale(zero=True)),
        color=alt.Color("Window:N", sort=["3 months", "12 months", "24 months"],
                        scale=alt.Scale(range=["#8AA7ED", "#4673CC", "#173D7F"]), legend=None),
        tooltip=[alt.Tooltip("Window:N"), alt.Tooltip("Maximum DPD:Q", title="Maximum DPD", format=",.0f")],
    )
    labels = chart.mark_text(dy=-12, fontSize=14, color="#20334E").encode(text="Maximum DPD:Q")
    st.altair_chart((chart + labels).properties(height=260).configure_view(strokeWidth=0), width="stretch")


def monthly_chart(monthly):
    rows = [{"Period": period, "Maximum DPD": monthly[period],
             "Observation": "Overdue days reported" if monthly[period] > 0 else "No overdue days"}
            for period in sorted(monthly)]
    data = pd.DataFrame(rows)
    chart = alt.Chart(data).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("Period:N", sort=sorted(monthly), title="Reporting month", axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("Maximum DPD:Q", title="Days past due", scale=alt.Scale(zero=True)),
        color=alt.Color("Observation:N", scale=alt.Scale(domain=["No overdue days", "Overdue days reported"],
                                                       range=["#148D91", "#D79A38"]),
                        legend=alt.Legend(title=None, orient="top")),
        tooltip=["Period:N", alt.Tooltip("Maximum DPD:Q", format=",.0f"), "Observation:N"],
    )
    # A point at zero keeps on-time reported months visible without inventing a bar height.
    points = chart.mark_circle(size=35).encode()
    st.altair_chart((chart + points).properties(height=320).configure_view(strokeWidth=0), width="stretch")
