"""Streamlit entry point: python -m streamlit run app.py"""
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from engine import CONFIG_FILES, PipelineError, load_config, parse_records, profile

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Credit Behaviour Profiler", page_icon="📊", layout="wide")


def format_value(value):
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return f"{value:,}" if isinstance(value, int) else str(value)


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
    st.title("Credit Behaviour Profiler")
    st.caption("YAML-driven profiling · Facility snapshots · Payment history · Borrower relationships")
    try:
        config = load_config(ROOT / "config")
    except (OSError, ValueError) as exc:
        st.error(f"Cannot load pipeline configuration: {exc}")
        st.stop()

    with st.sidebar:
        st.header("Report input")
        mode = st.radio("Data source", ["Bundled demo", "Upload JSON / JSONL", "Paste JSON"])
        text = ""
        if mode == "Bundled demo":
            text = (ROOT / "data" / "test-data.jsonl").read_text(encoding="utf-8")
            st.info("Includes the five supplied synthetic borrower reports.")
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
        clicked = st.button("Run profiler", type="primary", disabled=not text.strip(),
                            width="stretch")
        st.caption("Up to 100 reports / 5 MB. Results stay in this browser session; no database is used.")
        st.download_button("Download sample data", (ROOT / "data" / "test-data.jsonl").read_bytes(),
                           "test-data.jsonl", "application/x-ndjson")

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
        st.info("Upload or paste your report data, then select Run profiler.")
        return
    if batch["errors"]:
        st.warning(f"{len(batch['errors'])} of {batch['total']} report(s) could not be processed.")
        st.dataframe(batch["errors"], hide_index=True, width="stretch")
    if not batch["results"]:
        return
    st.caption(f"Processed {len(batch['results'])} of {batch['total']} reports successfully.")
    selected = st.selectbox("Select borrower report", range(len(batch["results"])),
        format_func=lambda i: " · ".join(str(x) for x in (
            batch["results"][i]["result"]["features"].get("borrower.display_name") or "Unnamed borrower",
            batch["results"][i]["result"]["features"].get("transaction.id"))))
    entry = batch["results"][selected]
    result, record = entry["result"], entry["input"]
    features = result["features"]
    st.caption(f"Analysis period: {features['report.analysis_period']} · Report date: {features['transaction.date']}")
    columns = st.columns(4)
    for col, (label, key) in zip(columns, [
        ("Reported facilities", "reported_facility_count"),
        ("Active facilities", "active_facility_count"),
        ("Outstanding (IDR)", "total_outstanding_idr"),
        ("Max DPD · 24m", "max_dpd_24m"),
    ]):
        col.metric(label, format_value(features.get(key)))

    summary, windows, facilities, graph, raw, settings = st.tabs(
        ["Summary", "Payment history", "Facilities", "Graph", "Features & export", "YAML configuration"])
    with summary:
        st.subheader("Configured summary")
        st.dataframe([{"Metric": item["label"], "Value": format_value(item["value"])}
                      for item in result["summary"]], hide_index=True, width="stretch")
        st.caption("N/A means no applicable value. A zero delinquency rate requires reported payment slots.")
    with windows:
        st.subheader("Payment history windows")
        st.dataframe([{
            "Window": f"{months} months",
            "Max DPD": features.get(f"max_dpd_{months}m"),
            "Worst collectibility": features.get(f"worst_collectibility_{months}m"),
            "Reported slots": features.get(f"reported_slot_count_{months}m"),
            "Delinquent slots": features.get(f"delinquent_slot_count_{months}m"),
            "Delinquency rate": features.get(f"delinquency_rate_{months}m"),
        } for months in (3, 12, 24)], hide_index=True, width="stretch")
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
            chart = pd.DataFrame({"Period": sorted(monthly),
                                  "Maximum DPD": [monthly[p] for p in sorted(monthly)]})
            st.bar_chart(chart.set_index("Period"))
        else:
            st.info("No reported payment observations within the 24-month window.")
        st.caption("The analysis month is included. NOT_APPLICABLE observations and future periods are excluded.")
    with facilities:
        rows = []
        for facility in record.get("facilities") or []:
            pos = facility.get("latest_position") or {}
            rows.append({"Facility": facility.get("facility_id"),
                         "Lender": (facility.get("reporting_institution") or {}).get("code"),
                         "Condition": pos.get("condition_normalized"),
                         "Outstanding IDR": pos.get("outstanding_principal"),
                         "DPD": pos.get("days_past_due"), "Collectibility": pos.get("collectibility"),
                         "Restructures": pos.get("restructuring_count"),
                         "Start date": facility.get("credit_start_date")})
        if rows:
            st.dataframe(rows, hide_index=True, width="stretch")
        else:
            st.info("No facilities in this report.")
    with graph:
        st.subheader("Borrower and report graph")
        nodes = result["graph"]["vertices"]
        dot = ["digraph { rankdir=LR; node [shape=box, style=rounded];"]
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
        st.subheader("Calculated features")
        feature_names = [spec["output"] for spec in config["feature-encoders.yml"]]
        st.dataframe([{"Feature": name, "Value": format_value(features.get(name))}
                      for name in feature_names], hide_index=True, width="stretch")
        st.download_button("Download selected result · JSON", json.dumps(result, indent=2, allow_nan=False),
                           "profile-result.json", "application/json")
        export = {"results": [{"input_index": e["input_index"], **e["result"]} for e in batch["results"]],
                  "errors": batch["errors"]}
        st.download_button("Download all results · JSON", json.dumps(export, indent=2, allow_nan=False),
                           "profile-results.json", "application/json")
        csv = pd.DataFrame([e["result"]["features"] for e in batch["results"]])
        csv = csv[[name for name in csv.columns if not name.startswith(("facility.", "payment."))]]
        st.download_button("Download feature table · CSV", csv.to_csv(index=False),
                           "profile-features.csv", "text/csv")
        st.json(result, expanded=False)
    with settings:
        st.write("These are the supplied configurations. Edit files in config/ and restart or redeploy to change the pipeline.")
        for filename in CONFIG_FILES:
            with st.expander(filename):
                st.code((ROOT / "config" / filename).read_text(encoding="utf-8"), language="yaml")


if __name__ == "__main__":
    main()
