"""Independent reference calculations and edge cases. Run: python -m unittest -v"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from engine import Expressions, PipelineError, load_config, lookup, parse_records, profile

ROOT = Path(__file__).resolve().parent


def ym(period):
    year, month = map(int, period[:7].split("-"))
    return year * 12 + month - 1


def reference(record):
    facilities = record.get("facilities", [])
    active = [f for f in facilities if f.get("latest_position", {}).get("condition_normalized") == "ACTIVE"]
    end = ym(record["analysis_reporting_period"])
    expected = {
        "reported_facility_count": len(facilities),
        "active_facility_count": len(active),
        "active_lender_count": len({f["reporting_institution"]["code"] for f in active
                                    if f.get("reporting_institution", {}).get("code") is not None}),
        "total_outstanding_idr": sum(f.get("latest_position", {}).get("outstanding_principal") or 0 for f in facilities),
        "active_restructured_facility_count": sum((f.get("latest_position", {}).get("restructuring_count") or 0) > 0 for f in active),
        "new_facility_count_3m": sum(end - 2 <= ym(f["credit_start_date"]) <= end
                                     for f in facilities if f.get("credit_start_date")),
    }
    slots = [slot for f in facilities for slot in f.get("payment_history_24m", [])
             if slot.get("observation_status") == "REPORTED" and slot.get("period")]
    for window in (3, 12, 24):
        selected = [s for s in slots if end - window + 1 <= ym(s["period"]) <= end]
        expected[f"max_dpd_{window}m"] = max([s.get("days_past_due") or 0 for s in selected] + [0])
        expected[f"worst_collectibility_{window}m"] = max([s.get("collectibility") or 0 for s in selected] + [0])
        if window != 3:
            bad = sum((s.get("days_past_due") or 0) > 0 for s in selected)
            expected[f"delinquent_slot_count_{window}m"] = bad
            expected[f"reported_slot_count_{window}m"] = len(selected)
            expected[f"delinquency_rate_{window}m"] = bad / len(selected) if selected else None
    bad_months = [ym(s["period"]) for s in slots if end - 23 <= ym(s["period"]) <= end
                  and (s.get("days_past_due") or 0) > 0]
    expected["months_since_last_delinquency"] = end - max(bad_months) if bad_months else None
    return expected


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT / "config")
        cls.records = parse_records((ROOT / "data" / "test-data.jsonl").read_text())

    def assert_reference(self, record):
        actual = profile(record, self.config)["features"]
        for key, value in reference(record).items():
            with self.subTest(feature=key):
                self.assertEqual(actual[key], value)

    def test_all_five_reports_against_independent_calculation(self):
        self.assertEqual(len(self.records), 5)
        for record in self.records:
            with self.subTest(report=record["transaction"]["id"]):
                self.assert_reference(record)

    def test_summary_graph_and_hidden_timestamp(self):
        result = profile(self.records[0], self.config)
        self.assertEqual(len(result["graph"]["vertices"]), 2)
        self.assertEqual(result["graph"]["edges"][0]["label"], "SUBMITTED")
        self.assertEqual(result["summary"][0]["value"], self.records[0]["transaction"]["id"])
        self.assertNotIn("transaction.ts", result["features"])
        json.dumps(result, allow_nan=False)

    def test_empty_history_and_missing_facilities(self):
        record = {"transaction": {"id": "empty"}, "borrower": {"borrower_id": "b"},
                  "analysis_reporting_period": "2026-03"}
        self.assert_reference(record)
        features = profile(record, self.config)["features"]
        self.assertEqual(features["reported_facility_count"], 0)
        self.assertIsNone(features["delinquency_rate_24m"])
        self.assertIsNone(features["months_since_last_delinquency"])

    def test_missing_fields_preserve_array_alignment(self):
        record = deepcopy(self.records[0])
        record["facilities"][0]["latest_position"].pop("outstanding_principal", None)
        record["facilities"][0]["latest_position"].pop("restructuring_count", None)
        record["facilities"][0]["reporting_institution"].pop("code", None)
        record["facilities"][0]["payment_history_24m"][0].pop("days_past_due", None)
        self.assert_reference(record)
        values = lookup(record, "$.facilities..latest_position.outstanding_principal")
        self.assertIsNone(values[0])
        self.assertEqual(len(values), len(record["facilities"]))

    def test_inclusive_windows_and_year_rollover(self):
        record = deepcopy(self.records[0])
        record["analysis_reporting_period"] = "2026-01"
        facility = record["facilities"][0]
        record["facilities"] = [facility]
        facility["payment_history_24m"] = [
            {"period": period, "days_past_due": dpd, "collectibility": 2, "observation_status": status}
            for period, dpd, status in [("2025-10", 80, "REPORTED"), ("2025-11", 10, "REPORTED"),
                                       ("2026-01", 20, "REPORTED"), ("2026-02", 999, "REPORTED"),
                                       ("2025-12", 888, "NOT_APPLICABLE_BEFORE_START")]]
        self.assert_reference(record)
        self.assertEqual(profile(record, self.config)["features"]["max_dpd_3m"], 20)

    def test_date_only_and_explicit_fallback(self):
        record = deepcopy(self.records[0])
        record["transaction"]["date"] = "2026-04-15"
        self.assertEqual(profile(record, self.config)["features"]["transaction.date"], "2026-04-15T00:00:00Z")
        del record["transaction"]["date"]
        now = datetime(2026, 11, 2, tzinfo=timezone.utc)
        self.assertEqual(profile(record, self.config, now)["features"]["transaction.date"], "2026-11-02T00:00:00Z")

    def test_invalid_inputs(self):
        for text in ("", "[]", '[1]', '{"a":', '{}\n{bad}'):
            with self.subTest(text=text), self.assertRaises(PipelineError):
                parse_records(text)
        for mutation in ({"analysis_reporting_period": "2026-13"}, {"transaction": None}, {"facilities": [1]}):
            record = deepcopy(self.records[0])
            record.update(mutation)
            with self.assertRaises(PipelineError):
                profile(record, self.config)
        with self.assertRaises(PipelineError):
            profile({}, self.config)

    def test_input_formats(self):
        record = self.records[0]
        self.assertEqual(parse_records(json.dumps(record, indent=2)), [record])
        self.assertEqual(parse_records(json.dumps(self.records)), self.records)

    def test_expressions_are_bounded_and_isolated(self):
        runtime = Expressions()
        for expr in ('out.$1 = os.execute("echo unsafe")', 'out.$1 = python.eval("1")', 'while true do end'):
            with self.subTest(expression=expr), self.assertRaises(Exception):
                runtime.evaluate(expr, [])
        self.assertEqual(runtime.evaluate("out.$1 = 42", []), 42)


if __name__ == "__main__":
    unittest.main()
