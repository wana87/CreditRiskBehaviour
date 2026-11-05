"""Readable source-report presentation. Never reads calculated profiler features."""
from hashlib import sha256
from html import escape
import json
from numbers import Real

import pandas as pd
import streamlit as st


MISSING = object()


def source_value(value=MISSING, currency=None):
    """Keep source absence, null, false, and numeric zero distinguishable."""
    if value is MISSING:
        return "Not supplied"
    if value is None:
        return "Not reported (null)"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Real):
        # Use the original numeric precision instead of rounding the source amount.
        formatted = format(value, ",")
        return f"{currency} {formatted}" if currency else formatted
    if isinstance(value, str):
        return value if value else "Empty string"
    return json.dumps(value, ensure_ascii=False)


def supplied_object(value):
    return value if isinstance(value, dict) else {}


def field_rows(obj, fields, currency=None):
    """Each field is (source key, display label, optional monetary flag)."""
    return [(label, source_value(str(obj[key]) if key.endswith("_year") and isinstance(obj.get(key), Real)
                                 else obj.get(key, MISSING), currency if rest and rest[0] else None))
            for key, label, *rest in fields]


def source_sections(record):
    borrower = supplied_object(record.get("borrower"))
    report = supplied_object(record.get("report"))
    transaction = supplied_object(record.get("transaction"))
    kind = str(borrower.get("borrower_type") or "").upper()
    identity = field_rows(borrower, [
        ("borrower_id", "Borrower ID"), ("display_name", "Name / registered name"),
        ("borrower_type", "Borrower type"), ("segment", "Source segment"),
    ])
    if kind == "CORPORATE":
        identity += field_rows(borrower, [
            ("legal_form", "Legal form"), ("industry", "Industry"),
            ("business_scale", "Business scale"), ("incorporation_year", "Incorporation year"),
        ])
        identity += field_rows(borrower, [("annual_revenue_idr", "Annual revenue (IDR)", True)], "IDR")
        title = "Corporate profile"
    elif kind == "INDIVIDUAL":
        identity += field_rows(borrower, [
            ("employment_type", "Employment type"), ("age_band", "Age band"),
        ])
        identity += field_rows(borrower, [("monthly_income_idr", "Monthly income (IDR)", True)], "IDR")
        title = "Individual profile"
    else:
        title = "Borrower profile"
    metadata = field_rows(report, [
        ("report_id", "Bureau report ID"), ("source_system", "Source system"),
        ("report_requested_at", "Requested at"), ("available_at", "Available at"),
        ("history_start_period", "History starts"), ("history_end_period", "History ends"),
        ("history_calendar_slot_count", "Calendar slots per facility"),
        ("reported_facilities_complete", "Facilities complete, per source"),
        ("historical_balances_available", "Historical balances available"),
    ])
    metadata += field_rows(record, [("analysis_reporting_period", "Analysis period"), ("evaluation_date", "Evaluation date")])
    metadata += field_rows(transaction, [("id", "Transaction ID"), ("date", "Transaction date")])
    return title, identity, metadata


def panel_html(title, rows):
    fields = "".join(f'<div class="bureau-field"><dt>{escape(str(label))}</dt>'
                     f'<dd>{escape(str(value))}</dd></div>' for label, value in rows)
    return f'<section class="bureau-panel"><h3>{escape(title)}</h3><dl class="bureau-fields">{fields}</dl></section>'


def header_html(record):
    borrower = supplied_object(record.get("borrower"))
    report = supplied_object(record.get("report"))
    name = source_value(borrower.get("display_name", MISSING))
    tag = "SYNTHETIC SAMPLE" if record.get("synthetic_data") is True else "SOURCE RECORD"
    report_id = source_value(report.get("report_id", MISSING))
    return f'''<header class="bureau-banner"><div class="bureau-kicker">CREDIT BUREAU REPORT <span>{tag}</span></div>
        <h2>{escape(name)}</h2><p>{escape(report_id)}</p>
        <div class="bureau-source-note">Readable presentation of the selected input record. Values below come from the source report.</div></header>'''


def facility_register(record):
    return [{
        "Facility ID": source_value(f.get("facility_id", MISSING)),
        "Product": source_value(f.get("facility_type_normalized") or f.get("credit_type_raw", MISSING)),
        "Institution": source_value(supplied_object(f.get("reporting_institution")).get("name", MISSING)),
        "Currency": source_value(f.get("currency", MISSING)),
        "Funding": source_value(f.get("funding_type", MISSING)),
        "Source condition": source_value(supplied_object(f.get("latest_position")).get("condition_normalized", MISSING)),
        "Source outstanding": source_value(supplied_object(f.get("latest_position")).get("outstanding_principal", MISSING)),
        "Source limit": source_value(supplied_object(f.get("latest_position")).get("credit_limit", MISSING)),
    } for f in record.get("facilities") or []]


def facility_sections(facility):
    lender = supplied_object(facility.get("reporting_institution"))
    pos = supplied_object(facility.get("latest_position"))
    # No default currency or currency conversion is applied to the raw source view.
    currency = facility.get("currency")
    currency = str(currency) if currency not in (None, "") else "[currency not supplied]"
    contract = field_rows(facility, [
        ("facility_id", "Facility ID"), ("account_number", "Account number"),
        ("facility_type_normalized", "Normalized product type"), ("credit_type_raw", "Credit type, raw"),
        ("credit_nature_raw", "Credit nature, raw"), ("contract_type_raw", "Contract type, raw"),
        ("funding_type", "Funding type"), ("currency", "Currency"),
        ("purpose", "Purpose"), ("revolving", "Revolving"),
        ("initial_contract_number", "Initial contract number"), ("initial_contract_date", "Initial contract date"),
        ("credit_start_date", "Credit start date"), ("maturity_date", "Maturity date"),
        ("reporter_last_updated_at", "Institution last updated at"),
    ])
    contract += field_rows(lender, [("code", "Institution code"), ("name", "Institution name"), ("branch", "Branch")])
    position = field_rows(pos, [
        ("position_date", "Position date"), ("condition_raw", "Condition, raw"),
        ("condition_normalized", "Condition, normalized"), ("condition_date", "Condition date"),
        ("initial_credit_limit", "Initial credit limit", True), ("credit_limit", "Current credit limit", True),
        ("outstanding_principal", "Outstanding principal", True), ("principal_arrears", "Principal arrears", True),
        ("interest_arrears", "Interest arrears", True), ("days_past_due", "Days past due"),
        ("collectibility", "Collectibility code"), ("restructuring_count", "Restructuring count"),
        ("last_restructuring_date", "Last restructuring date"),
    ], currency)
    position += field_rows(pos, [
        ("contingent_exposure_idr", "Contingent exposure (IDR)", True),
        ("written_off_amount_idr", "Written-off amount (IDR)", True),
    ], "IDR")
    return contract, position


def history_rows(facility):
    """Return every supplied row in its original order, including ineligible slots."""
    return [{
        "Source row": index,
        "Period": source_value(row.get("period", MISSING)),
        "Observation status": source_value(row.get("observation_status", MISSING)),
        "DPD (days)": source_value(row.get("days_past_due", MISSING)),
        "Collectibility": source_value(row.get("collectibility", MISSING)),
    } for index, row in enumerate(facility.get("payment_history_24m") or [], 1)]


def _history_tone(row):
    status = row["Observation status"]
    if status == "NOT_REPORTED":
        color = "#fff0f1"
    elif status != "REPORTED":
        color = "#f0f3f7"
    elif row["DPD (days)"] in ("0", "0.0"):
        color = "#edf8f4"
    elif row["DPD (days)"] in ("Not supplied", "Not reported (null)"):
        color = "#f0f3f7"
    else:
        color = "#fff6e6"
    return [f"background-color: {color}; color: #243b53"] * len(row)


def additional_rows(value, prefix=""):
    """Flatten objects for reading. Lists remain JSON values rather than losing rows."""
    if isinstance(value, dict):
        rows = []
        for key, item in value.items():
            label = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, dict) and item:
                rows.extend(additional_rows(item, label))
            else:
                rows.append((label, source_value(item)))
        return rows
    return [(prefix or "Value", source_value(value))]


def source_json(record):
    return json.dumps(record, indent=2, ensure_ascii=False)


PRINT_CSS = '''body{font:14px/1.55 Arial,sans-serif;color:#20334e;background:#f1f4f8;margin:0;padding:32px}
main{max-width:1100px;margin:auto;background:white;padding:40px;border:1px solid #e1e7ef;border-radius:18px}
h1,h2,h3,h4{color:#17345f}h2{font-size:26px}h3{margin-top:24px}.bureau-kicker{font-size:12px;letter-spacing:1px;font-weight:bold}
.bureau-kicker span{margin-left:12px;background:#e9eff9;border-radius:5px;padding:4px 8px}.bureau-banner{border-bottom:3px solid #3157b7;padding-bottom:18px}
.bureau-source-note,.source-note{font-size:12px;color:#5c718b}.bureau-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 24px}
.bureau-field{border-bottom:1px solid #e8edf3;padding:8px 0;break-inside:avoid}.bureau-field dt{font-size:12px;color:#64748b}
.bureau-field dd{margin:4px 0 0;font-weight:600;overflow-wrap:anywhere}.bureau-columns{display:grid;grid-template-columns:1fr 1fr;gap:28px}
table{width:100%;border-collapse:collapse;margin:15px 0;font-size:12px}th,td{padding:9px;border:1px solid #dfe6ed;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{background:#eaf0fa}thead{display:table-header-group}pre{font:11px/1.45 monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f7f9fc;padding:18px}
.facility-section{break-before:page}.source-note{padding:12px;background:#f3f6fb}details{margin:14px 0}
@media(max-width:700px){body{padding:10px}main{padding:20px}.bureau-columns,.bureau-fields{grid-template-columns:1fr}}
@media print{body{background:white;padding:0}main{padding:0;border:0;border-radius:0}details{display:block}summary{font-weight:bold}tr{break-inside:avoid}a{color:inherit}}'''


def table_html(rows):
    if not rows:
        return '<p class="source-note">No source rows supplied.</p>'
    columns = list(rows[0])
    head = "".join(f"<th>{escape(str(c))}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(row[c]))}</td>" for c in columns) + "</tr>" for row in rows)
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def printable_report(record):
    title, identity, metadata = source_sections(record)
    parts = [header_html(record), '<p class="source-note">Source values only. Not supplied = field absent. '
             'Not reported (null) = explicit null. Zero and No retain their original meaning. No risk score or currency conversion is added.</p>',
             '<div class="bureau-columns">', panel_html(title, identity), panel_html("Report information", metadata), '</div>',
             '<h3>Facility register</h3>', table_html(facility_register(record))]
    for index, f in enumerate(record.get("facilities") or [], 1):
        contract, position = facility_sections(f)
        parts += [f'<section class="facility-section"><h2>Facility {index}: {escape(source_value(f.get("facility_id", MISSING)))}</h2>',
                  '<div class="bureau-columns">', panel_html("Contract and institution", contract), panel_html("Latest source position", position), '</div>',
                  panel_html("Collateral, as supplied", additional_rows(f.get("collateral", MISSING))),
                  '<h3>Payment history, source order</h3>', table_html(history_rows(f)), '</section>']
    parts += [panel_html("Complete borrower fields", additional_rows(record.get("borrower", MISSING))),
              '<h3>Complete selected source JSON</h3>', f'<pre id="source-json">{escape(source_json(record))}</pre>']
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' \
           '<title>Credit bureau source report</title><style>' + PRINT_CSS + '</style></head><body><main>' + "".join(parts) + '</main></body></html>'


def render_bureau_report(record):
    title, identity, metadata = source_sections(record)
    st.html(header_html(record))
    st.caption("Source view: no feature calculations or filled-in dates. Not supplied means absent; Not reported (null) means explicitly null. Zero and No are preserved.")
    left, right = st.columns(2, gap="large")
    with left:
        st.html(panel_html(title, identity))
    with right:
        st.html(panel_html("Report information", metadata))
    st.subheader("Facility register", icon=":material/account_balance:")
    register = facility_register(record)
    if register:
        st.caption(f"{len(register)} facility records supplied. Source amounts appear in each facility's currency, without conversion or aggregation.")
        st.dataframe(register, hide_index=True, width="stretch")
        facilities = record["facilities"]
        fingerprint = sha256(source_json(record).encode()).hexdigest()[:16]
        index = st.selectbox("Inspect source facility", range(len(facilities)), key=f"bureau-facility-{fingerprint}",
            format_func=lambda i: f"{source_value(facilities[i].get('facility_id', MISSING))} · "
                                  f"{source_value(facilities[i].get('facility_type_normalized') or facilities[i].get('credit_type_raw', MISSING))}")
        f = facilities[index]
        contract, position = facility_sections(f)
        st.subheader("Selected facility", icon=":material/description:")
        left, right = st.columns(2, gap="large")
        with left:
            st.html(panel_html("Contract and institution", contract))
        with right:
            st.html(panel_html("Latest source position", position))
        with st.expander("Collateral, as supplied", icon=":material/real_estate_agent:"):
            st.html(panel_html("Collateral details", additional_rows(f.get("collateral", MISSING))))
        st.subheader("Payment history · source observations", icon=":material/calendar_month:")
        history = history_rows(f)
        st.caption("All supplied rows remain in source order, including reporting gaps and non-applicable slots. No missing DPD values are replaced with zero.")
        st.html('<div class="bureau-legend"><span class="history-clear">REPORTED, DPD 0</span>'
                '<span class="history-overdue">REPORTED, overdue days</span><span class="history-gap">NOT_REPORTED</span>'
                '<span class="history-na">Non-applicable or unknown</span></div>')
        if history:
            st.dataframe(pd.DataFrame(history).style.apply(_history_tone, axis=1),
                         hide_index=True, width="stretch", height=430)
        else:
            st.info("No payment-history rows were supplied for this facility.")
        with st.expander("Complete selected facility JSON", icon=":material/data_object:"):
            st.json(f, expanded=False)
    else:
        st.info("No facility records were supplied in this report.")
    with st.expander("Other supplied borrower and report fields", icon=":material/list_alt:"):
        extra = [("borrower", record.get("borrower", MISSING)), ("report", record.get("report", MISSING))]
        for name, value in extra:
            st.html(panel_html(f"All {name} fields", additional_rows(value)))
        remainder = {key: value for key, value in record.items() if key not in ("borrower", "report", "facilities")}
        st.html(panel_html("Other top-level fields", additional_rows(remainder)))
    st.subheader("Source record and downloads", icon=":material/download:")
    st.caption("The JSON download contains the selected input object, with formatting only. The HTML report includes every facility and history row. Open it in a browser and use Print to save a PDF.")
    left, right = st.columns(2)
    with left:
        st.download_button("Download source record · JSON", source_json(record),
                           "bureau-source-record.json", "application/json", icon=":material/data_object:", width="stretch")
    with right:
        st.download_button("Download readable report · HTML", printable_report(record),
                           "bureau-source-report.html", "text/html", icon=":material/print:", width="stretch")
    with st.expander("Complete source JSON", icon=":material/code:"):
        st.json(record, expanded=False)
