"""Deterministically add 20 synthetic reports to the preserved five-report fixture.

Run from any directory: python generate_demo_data.py
No external data, network, or random personal identifiers are used.
"""
from collections import Counter
from copy import deepcopy
from datetime import date
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ANALYSIS = "2026-03"
AS_OF = "2026-03-31"
AVAILABLE = "2026-04-15"

PRODUCTS = {
    "MORTGAGE": ("Residential mortgage", "Home purchase", "RESIDENTIAL_PROPERTY", False),
    "AUTO_LOAN": ("Vehicle instalment loan", "Vehicle purchase", "VEHICLE", False),
    "PERSONAL_LOAN": ("Unsecured personal loan", "Personal expenditure", "UNSECURED", False),
    "CREDIT_CARD": ("Revolving credit card", "Retail purchases", "UNSECURED", True),
    "MICRO_BUSINESS_LOAN": ("Micro business loan", "Small business working capital", "BUSINESS_EQUIPMENT", False),
    "SHARIA_HOME_FINANCING": ("Sharia home financing", "Home purchase", "RESIDENTIAL_PROPERTY", False),
    "EDUCATION_LOAN": ("Education instalment loan", "Education", "UNSECURED", False),
    "WORKING_CAPITAL_REVOLVER": ("Working capital revolver", "Operating cash flow", "INVENTORY", True),
    "INVESTMENT_TERM_LOAN": ("Investment term loan", "Plant and equipment", "MACHINERY", False),
    "INVOICE_FINANCING": ("Invoice financing", "Receivables finance", "RECEIVABLES", True),
    "EQUIPMENT_LEASE": ("Equipment financing lease", "Equipment acquisition", "MACHINERY", False),
    "COMMERCIAL_PROPERTY_LOAN": ("Commercial property loan", "Business premises", "COMMERCIAL_PROPERTY", False),
    "PROJECT_FINANCE": ("Project finance loan", "Project construction", "PROJECT_ASSETS", False),
    "TRADE_IMPORT_LOAN": ("Funded import trade loan", "Import settlement", "INVENTORY", True),
    "BANK_GUARANTEE": ("Bank guarantee", "Performance guarantee", "CASH_MARGIN", True),
    "LETTER_OF_CREDIT": ("Undrawn letter of credit", "Import undertaking", "CASH_MARGIN", True),
}

# Each plan includes a borrower segment, descriptive scenario, and several products.
# Scenario descriptions are metadata for demonstrations, never outcome labels.
PLANS = [
    ("INDIVIDUAL", "Synthetic Individual Aditya", "Salaried", "CLEAN", ["MORTGAGE", "AUTO_LOAN", "CREDIT_CARD"]),
    ("INDIVIDUAL", "Synthetic Individual Bening", "Self-employed", "SPORADIC", ["MICRO_BUSINESS_LOAN", "CREDIT_CARD", "PERSONAL_LOAN"]),
    ("INDIVIDUAL", "Synthetic Individual Cakra", "Salaried", "RECENT_EARLY", ["MORTGAGE", "PERSONAL_LOAN", "CREDIT_CARD"]),
    ("INDIVIDUAL", "Synthetic Individual Dara", "Professional", "RECENT_SEVERE", ["AUTO_LOAN", "CREDIT_CARD", "PERSONAL_LOAN"]),
    ("INDIVIDUAL", "Synthetic Individual Elang", "Self-employed", "PERSISTENT", ["MICRO_BUSINESS_LOAN", "AUTO_LOAN", "CREDIT_CARD"]),
    ("INDIVIDUAL", "Synthetic Individual Fajar", "Salaried", "RECOVERED", ["MORTGAGE", "CREDIT_CARD", "PERSONAL_LOAN"]),
    ("INDIVIDUAL", "Synthetic Individual Gita", "Graduate employee", "THIN_FILE", ["EDUCATION_LOAN", "CREDIT_CARD"]),
    ("INDIVIDUAL", "Synthetic Individual Hana", "Salaried", "RESTRUCTURED_RECOVERED", ["SHARIA_HOME_FINANCING", "AUTO_LOAN", "CREDIT_CARD"]),
    ("INDIVIDUAL", "Synthetic Individual Intan", "Entrepreneur", "CLOSED_MIX", ["MICRO_BUSINESS_LOAN", "AUTO_LOAN", "CREDIT_CARD", "PERSONAL_LOAN"]),
    ("INDIVIDUAL", "Synthetic Individual Jaya", "Professional", "REPORTING_GAPS", ["MORTGAGE", "PERSONAL_LOAN", "CREDIT_CARD"]),
    ("CORPORATE", "PT Synthetic Aruna Manufacturing", "Manufacturing", "CLEAN", ["WORKING_CAPITAL_REVOLVER", "INVESTMENT_TERM_LOAN", "EQUIPMENT_LEASE", "BANK_GUARANTEE"]),
    ("CORPORATE", "PT Synthetic Bahari Trading", "Wholesale trade", "SEASONAL", ["WORKING_CAPITAL_REVOLVER", "TRADE_IMPORT_LOAN", "INVOICE_FINANCING", "LETTER_OF_CREDIT"]),
    ("CORPORATE", "PT Synthetic Cendana Logistics", "Transportation and logistics", "RECENT_EARLY", ["EQUIPMENT_LEASE", "WORKING_CAPITAL_REVOLVER", "COMMERCIAL_PROPERTY_LOAN", "BANK_GUARANTEE"]),
    ("CORPORATE", "PT Synthetic Damar Construction", "Construction", "RECENT_SEVERE", ["PROJECT_FINANCE", "WORKING_CAPITAL_REVOLVER", "EQUIPMENT_LEASE", "BANK_GUARANTEE"]),
    ("CORPORATE", "PT Synthetic Embun Agriculture", "Agriculture", "RESTRUCTURED_RECOVERED", ["INVESTMENT_TERM_LOAN", "WORKING_CAPITAL_REVOLVER", "EQUIPMENT_LEASE", "BANK_GUARANTEE"]),
    ("CORPORATE", "PT Synthetic Falah Retail", "Retail", "RESTRUCTURED_STRESS", ["WORKING_CAPITAL_REVOLVER", "COMMERCIAL_PROPERTY_LOAN", "INVOICE_FINANCING", "INVESTMENT_TERM_LOAN"]),
    ("CORPORATE", "PT Synthetic Garuda Digital", "Software and IT services", "THIN_FILE", ["WORKING_CAPITAL_REVOLVER", "EQUIPMENT_LEASE", "INVOICE_FINANCING"]),
    ("CORPORATE", "PT Synthetic Harsa Hospitality", "Hospitality", "CLOSED_MIX", ["COMMERCIAL_PROPERTY_LOAN", "WORKING_CAPITAL_REVOLVER", "INVESTMENT_TERM_LOAN", "EQUIPMENT_LEASE"]),
    ("CORPORATE", "PT Synthetic Indra Energy", "Renewable energy", "FUNDED_AND_CONTINGENT", ["PROJECT_FINANCE", "INVESTMENT_TERM_LOAN", "BANK_GUARANTEE", "LETTER_OF_CREDIT", "WORKING_CAPITAL_REVOLVER"]),
    ("CORPORATE", "PT Synthetic Jati Textiles", "Textile manufacturing", "WRITE_OFF_AND_GAPS", ["WORKING_CAPITAL_REVOLVER", "INVESTMENT_TERM_LOAN", "INVOICE_FINANCING", "TRADE_IMPORT_LOAN"]),
]


def month_index(value):
    return int(value[:4]) * 12 + int(value[5:7]) - 1


def period_at(index):
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_end(period):
    nxt = month_index(period) + 1
    return date.fromordinal(date(nxt // 12, nxt % 12 + 1, 1).toordinal() - 1).isoformat()


def demo_collectibility(dpd):
    """Illustrative ordered buckets, not a regulatory classification rule."""
    return 1 if dpd == 0 else 2 if dpd <= 30 else 3 if dpd <= 90 else 4 if dpd <= 180 else 5


def payment_dpd(scenario, offset, facility_no):
    # offset zero is the oldest month, 23 is the analysis month.
    if scenario == "SPORADIC":
        return {8: 7, 15: 18, 20: 5}.get(offset, 0) if facility_no == 0 else 0
    if scenario == "SEASONAL":
        return 12 + facility_no * 3 if offset in (5, 11, 17, 23) and facility_no < 2 else 0
    if scenario == "RECENT_EARLY":
        return {21: 5, 22: 12, 23: 25}.get(offset, 0) if facility_no == 0 else 0
    if scenario == "RECENT_SEVERE":
        return {19: 20, 20: 45, 21: 70, 22: 100, 23: 130}.get(offset, 0) if facility_no < 2 else 0
    if scenario == "PERSISTENT":
        return min(210, (offset - 7) * 15) if offset >= 8 and facility_no == 0 else 0
    if scenario in ("RECOVERED", "RESTRUCTURED_RECOVERED"):
        return {3: 30, 4: 60, 5: 95, 6: 125, 7: 60, 8: 15}.get(offset, 0) if facility_no == 0 else 0
    if scenario == "RESTRUCTURED_STRESS":
        return ({7: 45, 8: 90, 9: 125}.get(offset, 0) if offset < 18 else (offset - 17) * 20) if facility_no == 0 else 0
    if scenario == "CLOSED_MIX":
        return {6: 10, 7: 20}.get(offset, 0) if facility_no == 0 else 0
    if scenario == "WRITE_OFF_AND_GAPS":
        return min(240, (offset + 1) * 15) if facility_no == 0 else (10 if offset in (18, 22) else 0)
    return 0


def make_facility(template, report_no, facility_no, product, scenario, corporate):
    f = deepcopy(template)
    label, purpose, collateral, revolving = PRODUCTS[product]
    contingent = product in ("BANK_GUARANTEE", "LETTER_OF_CREDIT")
    seq = report_no * 10 + facility_no + 1
    lender = (report_no + facility_no) % 6 + 1
    # Deterministic amounts stay in IDR, avoiding mixed-currency sum ambiguity.
    scale = 1_000_000_000 if corporate else 25_000_000
    limit = scale * (2 + (report_no + facility_no) % 7)
    if product in ("MORTGAGE", "SHARIA_HOME_FINANCING"):
        limit *= 5
    if product == "CREDIT_CARD":
        limit = 15_000_000 + report_no % 5 * 5_000_000
    if product == "PROJECT_FINANCE":
        limit *= 3
    if scenario == "THIN_FILE":
        start_period = "2026-01" if facility_no == 0 else "2026-03"
    elif scenario == "FUNDED_AND_CONTINGENT" and facility_no == 4:
        start_period = "2026-02"
    else:
        start_period = ("2023-06", "2024-08", "2025-03", "2025-10", "2025-06")[facility_no % 5]
    start = start_period + "-01"
    closed = scenario == "CLOSED_MIX" and facility_no == 0
    written_off = scenario == "WRITE_OFF_AND_GAPS" and facility_no == 0
    terminal = "2025-11" if closed else "2025-09" if written_off else None
    history = []
    for offset in range(24):
        period = period_at(month_index(ANALYSIS) - 23 + offset)
        status = "REPORTED"
        if period < start_period:
            status = "NOT_APPLICABLE_BEFORE_OPENING"
        elif terminal and period > terminal:
            status = "NOT_APPLICABLE_AFTER_CLOSURE"
        elif contingent:
            status = "NOT_APPLICABLE_NON_FUNDED"
        elif scenario in ("REPORTING_GAPS", "WRITE_OFF_AND_GAPS") and facility_no == 1 and offset in (10, 14, 19):
            status = "NOT_REPORTED"
        dpd = payment_dpd(scenario, offset, facility_no) if status == "REPORTED" else None
        if contingent and dpd is not None:
            dpd = 0
        history.append({"period": period, "collectibility": demo_collectibility(dpd) if dpd is not None else None,
                        "days_past_due": dpd, "observation_status": status})
    condition = "CLOSED_PAID" if closed else "WRITTEN_OFF" if written_off else "ACTIVE"
    dpd = 0 if terminal or contingent else history[-1]["days_past_due"]
    outstanding = 0 if contingent or terminal else int(limit * (0.35 + (seq % 5) * 0.11))
    restructured = scenario in ("RESTRUCTURED_RECOVERED", "RESTRUCTURED_STRESS") and facility_no == 0
    maturity = f"{int(start[:4]) + (10 if product in ('MORTGAGE', 'SHARIA_HOME_FINANCING') else 5)}{start[4:]}"
    f.update({
        "facility_id": f"DEMO-FAC-{seq:04d}", "facility_id_origin": "SYNTHETIC",
        "reporting_institution": {"code": f"DEMO-LENDER-{lender}", "name": f"Synthetic Lender {lender}", "branch": "Synthetic Demo Branch"},
        "account_number": f"DEMO-ACCOUNT-{seq:04d}",
        "credit_nature_raw": "Revolving" if revolving else "Instalment",
        "credit_type_raw": label, "facility_type_normalized": product,
        "funding_type": "CONTINGENT" if contingent else "FUNDED",
        "purpose": purpose, "revolving": revolving,
        "contract_type_raw": "Syariah" if product == "SHARIA_HOME_FINANCING" else "Konvensional",
        "currency": "IDR", "initial_contract_number": f"DEMO-CONTRACT-{seq:04d}",
        "initial_contract_date": start, "credit_start_date": start, "maturity_date": maturity,
        "reporter_last_updated_at": "2026-04-10",
        "collateral": {"type": collateral, "estimated_value_idr": 0 if collateral == "UNSECURED" else int(limit * (0.2 if contingent else 1.3)), "valuation_date": AS_OF, "synthetic": True},
        "latest_position": {
            "position_date": AS_OF, "initial_credit_limit": limit,
            "credit_limit": 0 if terminal else limit, "outstanding_principal": outstanding,
            "collectibility": 5 if written_off else demo_collectibility(dpd), "days_past_due": dpd,
            "principal_arrears": int(outstanding * min(dpd / 300, 0.6)),
            "interest_arrears": int(outstanding * min(dpd / 3600, 0.04)),
            "restructuring_count": 2 if scenario == "RESTRUCTURED_STRESS" and restructured else int(restructured),
            "last_restructuring_date": "2025-03-15" if restructured else None,
            "condition_raw": {"ACTIVE": "Aktif", "CLOSED_PAID": "Lunas", "WRITTEN_OFF": "Hapus buku"}[condition],
            "condition_normalized": condition, "condition_date": month_end(terminal) if terminal else start,
            "contingent_exposure_idr": int(limit * 0.65) if contingent else 0,
            "written_off_amount_idr": int(limit * 0.7) if written_off else 0,
        },
        "payment_history_24m": history,
    })
    return f


def generate():
    original = [json.loads(line) for line in (DATA / "original-test-data.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(original) != 5:
        raise ValueError("Expected the preserved original five-report fixture.")
    records = deepcopy(original)
    for r in records:
        r["borrower"]["borrower_type"] = "INDIVIDUAL"
        r["borrower"]["segment"] = "Original synthetic individual fixture"
    for no, (kind, name, segment, scenario, products) in enumerate(PLANS, 6):
        corporate = kind == "CORPORATE"
        borrower = {"borrower_id": f"DEMO-BORROWER-{no:03d}", "display_name": name,
                    "borrower_type": kind, "segment": segment}
        if corporate:
            borrower.update({"legal_form": "PT", "industry": segment, "business_scale": "MID_MARKET" if no % 2 else "SME",
                             "incorporation_year": 2010 + no % 12, "annual_revenue_idr": (10 + no % 9) * 10_000_000_000})
        else:
            borrower.update({"employment_type": segment, "age_band": ["25-34", "35-44", "45-54"][no % 3],
                             "monthly_income_idr": (8 + no % 12) * 1_000_000})
        r = {"schema_version": "synthetic-slik-facility-history-v2", "synthetic_data": True,
             "payload_type": "BUREAU_REPORT", "transaction": {"id": f"DEMO-REPORT-{no:03d}", "date": AVAILABLE + "T00:00:00Z"},
             "evaluation_date": AVAILABLE, "analysis_reporting_period": ANALYSIS,
             "report": {"report_id": f"DEMO-BUREAU-REPORT-{no:03d}", "source_system": "SYNTHETIC_SLIK_STRUCTURE",
                        "report_requested_at": AVAILABLE, "available_at": AVAILABLE,
                        "history_start_period": "2024-04", "history_end_period": ANALYSIS,
                        "history_calendar_slot_count": 24, "reported_facilities_complete": True,
                        "historical_balances_available": False},
             "borrower": borrower,
             "demo_scenario": {"code": scenario, "description": "Synthetic historical pattern for demonstration, not a predictive label."},
             "facilities": [make_facility(original[0]["facilities"][0], no, i, product, scenario, corporate)
                            for i, product in enumerate(products)]}
        records.append(r)
    (DATA / "test-data.jsonl").write_text("".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    (DATA / "individual-samples.jsonl").write_text("".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n" for r in records if r["borrower"]["borrower_type"] == "INDIVIDUAL"), encoding="utf-8")
    (DATA / "corporate-samples.jsonl").write_text("".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n" for r in records if r["borrower"]["borrower_type"] == "CORPORATE"), encoding="utf-8")
    facilities = [f for r in records for f in r["facilities"]]
    slots = [p for f in facilities for p in f["payment_history_24m"]]
    manifest = {"synthetic_data": True, "report_count": len(records), "new_report_count": len(PLANS),
                "borrower_types": dict(Counter(r["borrower"]["borrower_type"] for r in records)),
                "facility_count": len(facilities), "payment_slot_count": len(slots),
                "facility_types": dict(Counter(f.get("facility_type_normalized") or "UNSPECIFIED_ORIGINAL" for f in facilities)),
                "observation_statuses": dict(Counter(p["observation_status"] for p in slots)),
                "scenarios": dict(Counter(r.get("demo_scenario", {}).get("code", "ORIGINAL_FIXTURE") for r in records)),
                "analysis_period": ANALYSIS, "report_available_at": AVAILABLE,
                "notes": ["All identifiers, names, and financial amounts are fictional.",
                          "All facilities use IDR. No future outcomes or supervised labels are included.",
                          "Contingent guarantees and letters of credit carry zero outstanding principal and separate contingent exposure. Their non-funded history slots are not payment observations.",
                          "New collectibility values use illustrative DPD buckets, not regulatory classification rules.",
                          "The original five cases are retained with added borrower-type metadata."]}
    (DATA / "demo-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2))
