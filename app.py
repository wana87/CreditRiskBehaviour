"""Streamlit entry point: python -m streamlit run app.py"""
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from engine import CONFIG_FILES, PipelineError, load_config, parse_records, profile
from ui import apply_styles, borrower_heading, borrower_kind, hero, monthly_chart, observations, window_chart

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Credit Behaviour Profiler", page_icon="📊", layout="wide")


def format_value(value):
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return f"{value:,}" if isinstance(value, int) else str(value)


def format_exposure(value):
    if value is None:
        return "N/A"
    if abs(value) >= 1_000_000_000:
        return f"Rp{value / 1_000_000_000:,.2f}bn"
    if abs(value) >= 1_000_000:
        return f"Rp{value / 1_000_000:,.2f}m"
    return f"Rp{value:,.0f}"


def run_batch(text, config):
    records = parse_records(text)
    results, errors = [], []
    for index, record in enumerate(records, 1):
        try:
            results.append({"input_index": index, "input": record, "result": profile(record, config)})
        except (PipelineError, KeyError, TypeError, ValueError) as exc:
            errors.append({"record": index, "error": str(exc)})
    return {"results": results, "errors": errors, "total": len(records)}


def main():
    apply_styles(ROOT)
    hero()
    try:
        config = load_config(ROOT / "config")
    except (OSError, ValueError) as exc:
        st.error(f"Cannot load pipeline configuration: {exc}")
        st.stop()

    with st.sidebar:
        st.html('<div class="sidebar-brand">🏦 Credit Profiler</div><div class="sidebar-caption">A clearer view of borrower behaviour.<br>Explore a report, then follow the evidence.</div>')
        st.divider()
        st.subheader("Report input", icon=":material/folder_open:")
        mode = st.radio("Data source", ["Bundled demo", "Upload JSON / JSONL", "Paste JSON"])
        text = ""
        if mode == "Bundled demo":
            text = (ROOT / "data" / "test-data.jsonl").read_text(encoding="utf-8")
            demo_count = sum(bool(line.strip()) for line in text.splitlines())
            st.info(f"Explore {demo_count} synthetic reports covering individual and corporate borrowers.", icon=":material/science:")
        elif mode == "Upload JSON / JSONL":
            uploaded = st.file_uploader("Choose report data", type=["json", "jsonl", "ndjson"])
            if uploaded is not None:
                try:
                    text = uploaded.getvalue().decode("utf-8-sig")
                except UnicodeDecodeError:
                    st.error("Use a UTF-8 encoded JSON or JSONL file.")
        else:
            text = st.text_area("Report object, array, or JSONL", height=280,
                                placeholder='{"transaction": {"id": "REPORT-001"}, ...}')
        clicked = st.button("Run profiler", icon=":material/play_arrow:", type="primary", disabled=not text.strip(),
                            width="stretch")
        st.caption("Up to 100 reports / 5 MB. Results stay in this browser session; no database is used.")
        st.download_button("Download sample data", (ROOT / "data" / "test-data.jsonl").read_bytes(),
                           "test-data.jsonl", "application/x-ndjson", icon=":material/download:", width="stretch")

    signature = sha256((mode + text + repr(config)).encode()).hexdigest()
    if st.session_state.get("signature") != signature:
        st.session_state.pop("batch", None)
        st.session_state["signature"] = signature
    if clicked or (mode == "Bundled demo" and "batch" not in st.session_state):
        try:
            with st.spinner("Mapping inputs and calculating features…"):
                st.session_state["batch"] = run_batch(text, config)
        except (PipelineError, RecursionError) as exc:
            st.error(str(exc))
    batch = st.session_state.get("batch")
    if batch is None:
        st.info("Upload or paste your report data, then select Run profiler.", icon=":material/upload_file:")
        return
    with st.sidebar:
        st.divider()
        st.subheader("Workspace snapshot", icon=":material/dashboard:")
        st.html(f'<div class="mini-summary"><div><strong>{len(batch["results"])}</strong><span>Reports processed</span></div>'
                f'<div><strong>{len(batch["errors"])}</strong><span>Report errors</span></div></div>')
        individuals = sum(borrower_kind(e["result"]["features"]) == "INDIVIDUAL" for e in batch["results"])
        corporates = sum(borrower_kind(e["result"]["features"]) == "CORPORATE" for e in batch["results"])
        st.caption(f"👤 {individuals} individual · 🏢 {corporates} corporate")
        st.caption("Historical profiling • No predictive credit score")
    if batch["errors"]:
        st.warning(f"{len(batch['errors'])} of {batch['total']} report(s) could not be processed.")
        st.dataframe(batch["errors"], hide_index=True, width="stretch")
    if not batch["results"]:
        return
    st.caption(f"✓ {len(batch['results'])} of {batch['total']} reports ready to explore")
    with st.container(key="borrower-select"):
        category = st.radio("Borrower type", ["All", "Individual", "Corporate"], horizontal=True,
                            key="borrower-type-filter")
        entries = [e for e in batch["results"] if category == "All" or
                   borrower_kind(e["result"]["features"]) == category.upper()]
        if not entries:
            st.info("No reports match this borrower type. Select All or load another dataset.")
            return
        selected = st.selectbox("Select borrower report", range(len(entries)),
            format_func=lambda i: " · ".join(str(x) for x in (
                {"INDIVIDUAL": "👤 Individual", "CORPORATE": "🏢 Corporate", "UNSPECIFIED": "Borrower"}[borrower_kind(entries[i]["result"]["features"])],
                entries[i]["result"]["features"].get("borrower.display_name") or "Unnamed borrower",
                entries[i]["result"]["features"].get("transaction.id"))))
    entry = entries[selected]
    result, record = entry["result"], entry["input"]
    features = result["features"]
    borrower_heading(features)
    with st.container(key="metric-row"):
        columns = st.columns(4)
        for col, (label, key, slug, icon, help_text) in zip(columns, [
            ("Reported facilities", "reported_facility_count", "reported", "account_balance", "All facilities included in this report."),
            ("Active facilities", "active_facility_count", "active", "task_alt", "Facilities whose latest condition is ACTIVE."),
            ("Outstanding (IDR)", "total_outstanding_idr", "outstanding", "payments", "Outstanding principal summed across all reported facilities, in Indonesian rupiah."),
            ("Max DPD · 24m", "max_dpd_24m", "dpd", "schedule", "Maximum overdue days across REPORTED slots in the 24-month window. Read alongside the reported-slot count."),
        ]):
            with col:
                with st.container(key=f"kpi-{slug}"):
                    value = features.get(key)
                    money = key == "total_outstanding_idr"
                    st.metric(label, format_exposure(value) if money else format_value(value), icon=f":material/{icon}:",
                              border=True, help=help_text + (f" Exact value: IDR {format_value(value)}." if money else ""))

    summary, windows, facilities, graph, raw, settings = st.tabs(
        ["📊 Overview", "📅 Payment history", "🏦 Facilities", "🔗 Graph", "📥 Features & export", "⚙️ Configuration"])
    with summary:
        left, right = st.columns([1.3, 1], gap="large")
        with left:
            with st.container(border=True):
                st.subheader("Payment behaviour", icon=":material/monitoring:")
                st.caption("Maximum overdue days across three observation windows")
                window_chart(features)
                st.caption("A zero maximum needs to be read with the number of reported observations.")
        with right:
            with st.container(border=True):
                st.subheader("Historical observations", icon=":material/manage_search:")
                observations(features)
        st.subheader("Report at a glance", icon=":material/fact_check:")
        st.dataframe([{"Metric": item["label"], "Value": format_value(item["value"])}
                      for item in result["summary"]], hide_index=True, width="stretch")
        st.caption("N/A means no applicable value. A zero delinquency rate requires reported payment slots.")
        with st.expander("Borrower details and demo scenario", icon=":material/person_search:"):
            borrower = record.get("borrower") or {}
            metadata = [{"Attribute": key.replace("_", " ").title(), "Value": format_value(value)}
                        for key, value in borrower.items()]
            st.dataframe(metadata, hide_index=True, width="stretch")
            if record.get("demo_scenario"):
                st.write(record["demo_scenario"])
                st.caption("Scenario descriptions identify synthetic historical patterns, not future outcome labels.")
    with windows:
        st.subheader("Payment history windows", icon=":material/date_range:")
        window_rows = [{
            "Window": f"{months} months",
            "Max DPD": features.get(f"max_dpd_{months}m"),
            "Worst collectibility": features.get(f"worst_collectibility_{months}m"),
            "Reported slots": features.get(f"reported_slot_count_{months}m"),
            "Delinquent slots": features.get(f"delinquent_slot_count_{months}m"),
            "Delinquency rate": features.get(f"delinquency_rate_{months}m"),
        } for months in (3, 12, 24)]
        st.dataframe(window_rows, hide_index=True, width="stretch", column_config={
            "Delinquency rate": st.column_config.NumberColumn("Delinquency rate", format="percent"),
        })
        st.caption("The YAML defines slot counts and rates for 12 and 24 months only. Rates count facility-month slots, not distinct calendar months.")
        periods = features.get("payment.period", [])
        dpds = features.get("payment.days_past_due", [])
        statuses = features.get("payment.observation_status", [])
        ap = features["report.analysis_period"]
        end = int(ap[:4]) * 12 + int(ap[5:7]) - 1
        monthly = {}
        for period, dpd, status in zip(periods, dpds, statuses):
            if status != "REPORTED" or period is None:
                continue
            try:
                ym = int(period[:4]) * 12 + int(period[5:7]) - 1
            except (TypeError, ValueError):
                continue
            if end - 23 <= ym <= end:
                monthly[period] = max(monthly.get(period, 0), dpd or 0)
        if monthly:
            st.subheader("Monthly payment timeline", icon=":material/timeline:")
            monthly_chart(monthly)
        else:
            st.info("No reported payment observations within the 24-month window.")
        st.caption("The analysis month is included. NOT_APPLICABLE observations and future periods are excluded.")
    with facilities:
        st.subheader("Facility portfolio", icon=":material/account_balance:")
        st.caption("Latest reported positions, institution codes, and principal exposure")
        rows = []
        for facility in record.get("facilities") or []:
            pos = facility.get("latest_position") or {}
            rows.append({"Facility": facility.get("facility_id"),
                         "Product type": facility.get("facility_type_normalized") or "Unspecified",
                         "Funding": facility.get("funding_type") or "Unspecified",
                         "Lender": (facility.get("reporting_institution") or {}).get("code"),
                         "Condition": pos.get("condition_normalized"),
                         "Currency": facility.get("currency"),
                         "Outstanding IDR": pos.get("outstanding_principal"),
                         "Credit limit IDR": pos.get("credit_limit"),
                         "Contingent exposure IDR": pos.get("contingent_exposure_idr"),
                         "Written-off amount IDR": pos.get("written_off_amount_idr"),
                         "Collateral": (facility.get("collateral") or {}).get("type"),
                         "DPD": pos.get("days_past_due"), "Collectibility": pos.get("collectibility"),
                         "Restructures": pos.get("restructuring_count"),
                         "Start date": facility.get("credit_start_date"),
                         "Maturity": facility.get("maturity_date")})
        if rows:
            st.dataframe(rows, hide_index=True, width="stretch", column_config={
                "Outstanding IDR": st.column_config.NumberColumn("Outstanding IDR", format="localized"),
                "Credit limit IDR": st.column_config.NumberColumn("Credit limit IDR", format="localized"),
                "Contingent exposure IDR": st.column_config.NumberColumn("Contingent exposure IDR", format="localized"),
                "Written-off amount IDR": st.column_config.NumberColumn("Written-off amount IDR", format="localized"),
            })
            st.caption("Scroll horizontally for product, funding, collateral, limit, and maturity details. Contingent exposure and written-off amounts are separate from outstanding principal.")
            exposure = pd.DataFrame(rows)[["Facility", "Outstanding IDR"]]
            if exposure["Outstanding IDR"].notna().any():
                st.subheader("Exposure by facility", icon=":material/payments:")
                st.bar_chart(exposure, x="Facility", y="Outstanding IDR", horizontal=True,
                             color="#3157B7", x_label="Outstanding principal (IDR)", height=280)
        else:
            st.info("No facilities in this report.")
    with graph:
        st.subheader("Borrower and report graph", icon=":material/hub:")
        nodes = result["graph"]["vertices"]
        dot = ['digraph { rankdir=LR; bgcolor="transparent"; pad="0.5"; nodesep="0.7"; '
               'node [shape=box, style="rounded,filled", fillcolor="#EDF2FC", color="#9CB2DF", '
               'fontcolor="#20334E", fontname="Helvetica", margin="0.25,0.18"]; '
               'edge [color="#577ABD", fontcolor="#526887", fontname="Helvetica"];']
        node_ids = {}
        for i, node in enumerate(nodes):
            node_ids[json.dumps(node["ids"])] = f"n{i}"
            label = node["label"] + "\n" + " / ".join(str(x) for x in node["ids"])
            dot.append(f"n{i} [label={json.dumps(label)}];")
        for edge in result["graph"]["edges"]:
            source = node_ids.get(json.dumps(edge["from_ids"]))
            target = node_ids.get(json.dumps(edge["to_ids"]))
            if source and target:
                dot.append(f"{source} -> {target} [label={json.dumps(edge['label'])}];")
        st.graphviz_chart("\n".join(dot + ["}"]))
        st.json(result["graph"], expanded=False)
        st.caption("Graph elements are built from graph.yml for this report and exported as JSON.")
    with raw:
        st.subheader("Calculated features", icon=":material/functions:")
        feature_names = [spec["output"] for spec in config["feature-encoders.yml"]]
        st.dataframe([{"Feature": name, "Value": format_value(features.get(name))}
                      for name in feature_names], hide_index=True, width="stretch")
        st.subheader("Export workspace", icon=":material/download:")
        st.caption("Selected result exports the displayed borrower. All-results JSON and feature CSV include the entire processed batch, regardless of the borrower-type filter.")
        st.download_button("Download selected result · JSON", json.dumps(result, indent=2, allow_nan=False),
                           "profile-result.json", "application/json", icon=":material/person:")
        export = {"results": [{"input_index": e["input_index"], **e["result"]} for e in batch["results"]],
                  "errors": batch["errors"]}
        st.download_button("Download all results · JSON", json.dumps(export, indent=2, allow_nan=False),
                           "profile-results.json", "application/json", icon=":material/folder_zip:")
        csv = pd.DataFrame([e["result"]["features"] for e in batch["results"]])
        csv = csv[[name for name in csv.columns if not name.startswith(("facility.", "payment."))]]
        st.download_button("Download feature table · CSV", csv.to_csv(index=False),
                           "profile-features.csv", "text/csv", icon=":material/table_view:")
        st.json(result, expanded=False)
    with settings:
        st.subheader("Pipeline configuration", icon=":material/tune:")
        st.write("These are the supplied configurations. Edit files in config/ and restart or redeploy to change the pipeline.")
        for filename in CONFIG_FILES:
            with st.expander(filename):
                st.code((ROOT / "config" / filename).read_text(encoding="utf-8"), language="yaml")
    st.html('<div class="app-footer">Credit Behaviour Profiler · Historical analysis from the supplied YAML pipeline. '
            'Displayed observations describe payment history, not a prediction of future outcomes.</div>')


if __name__ == "__main__":
    main()
