"""Validate synthetic dataset coverage, chronology, and exposure invariants."""
from collections import Counter
import json
from pathlib import Path
import unittest

from engine import load_config, parse_records, profile

ROOT = Path(__file__).resolve().parent


class DemoDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = parse_records((ROOT / "data/test-data.jsonl").read_text())

    def test_sample_coverage_and_unique_identifiers(self):
        self.assertEqual(len(self.records), 25)
        self.assertEqual(Counter(r["borrower"]["borrower_type"] for r in self.records),
                         {"INDIVIDUAL": 15, "CORPORATE": 10})
        self.assertEqual(len({r["transaction"]["id"] for r in self.records}), 25)
        self.assertEqual(len({r["borrower"]["borrower_id"] for r in self.records}), 25)
        facilities = [f for r in self.records for f in r["facilities"]]
        self.assertEqual(len(facilities), 78)
        self.assertEqual(len({f["facility_id"] for f in facilities}), 78)
        self.assertEqual(len({f["facility_type_normalized"] for r in self.records[5:] for f in r["facilities"]}), 16)
        self.assertTrue(all(r["synthetic_data"] for r in self.records))
        self.assertTrue(all(len(r["facilities"]) >= 2 for r in self.records[5:]))

    def test_original_five_retained_except_explicit_metadata(self):
        originals = parse_records((ROOT / "data/original-test-data.jsonl").read_text())
        for original, expanded in zip(originals, self.records[:5]):
            self.assertEqual(original["facilities"], expanded["facilities"])
            for key in original:
                if key != "borrower":
                    self.assertEqual(original[key], expanded[key])
            for key, value in original["borrower"].items():
                self.assertEqual(value, expanded["borrower"][key])

    def test_new_facility_histories_and_exposure_consistency(self):
        for r in self.records[5:]:
            self.assertEqual(r["analysis_reporting_period"], "2026-03")
            for f in r["facilities"]:
                with self.subTest(report=r["transaction"]["id"], facility=f["facility_id"]):
                    history = f["payment_history_24m"]
                    pos = f["latest_position"]
                    self.assertEqual(len(history), 24)
                    self.assertEqual(len({p["period"] for p in history}), 24)
                    self.assertEqual(history[0]["period"], "2024-04")
                    self.assertEqual(history[-1]["period"], "2026-03")
                    self.assertEqual(f["currency"], "IDR")
                    self.assertLessEqual(f["credit_start_date"], pos["position_date"])
                    self.assertGreater(f["maturity_date"], f["credit_start_date"])
                    self.assertGreaterEqual(pos["outstanding_principal"], 0)
                    self.assertLessEqual(pos["outstanding_principal"], pos["credit_limit"])
                    self.assertLessEqual(pos["credit_limit"], pos["initial_credit_limit"])
                    for p in history:
                        if p["period"] < f["credit_start_date"][:7]:
                            self.assertEqual(p["observation_status"], "NOT_APPLICABLE_BEFORE_OPENING")
                        if p["observation_status"] == "REPORTED":
                            self.assertIsInstance(p["days_past_due"], int)
                            self.assertGreaterEqual(p["days_past_due"], 0)
                            self.assertIn(p["collectibility"], (1, 2, 3, 4, 5))
                        else:
                            self.assertIsNone(p["days_past_due"])
                            self.assertIsNone(p["collectibility"])
                    if f["funding_type"] == "CONTINGENT":
                        self.assertEqual(pos["outstanding_principal"], 0)
                        self.assertGreater(pos["contingent_exposure_idr"], 0)
                        self.assertFalse(any(p["observation_status"] == "REPORTED" for p in history))
                    elif pos["condition_normalized"] == "ACTIVE":
                        self.assertEqual(pos["days_past_due"], history[-1]["days_past_due"])
                        self.assertEqual(pos["collectibility"], history[-1]["collectibility"])
                    else:
                        self.assertEqual(pos["outstanding_principal"], 0)
                        self.assertTrue(all(p["observation_status"] == "NOT_APPLICABLE_AFTER_CLOSURE"
                                            for p in history if p["period"] > pos["condition_date"][:7]))

    def test_manifest_and_split_files_match_combined_dataset(self):
        manifest = json.loads((ROOT / "data/demo-manifest.json").read_text())
        facilities = [f for r in self.records for f in r["facilities"]]
        statuses = Counter(p["observation_status"] for f in facilities for p in f["payment_history_24m"])
        self.assertEqual(manifest["report_count"], len(self.records))
        self.assertEqual(manifest["facility_count"], len(facilities))
        self.assertEqual(manifest["observation_statuses"], statuses)
        for kind, filename in [("INDIVIDUAL", "individual-samples.jsonl"), ("CORPORATE", "corporate-samples.jsonl")]:
            split = parse_records((ROOT / "data" / filename).read_text())
            self.assertEqual(split, [r for r in self.records if r["borrower"]["borrower_type"] == kind])

    def test_borrower_category_export_and_missing_metadata_compatibility(self):
        config = load_config(ROOT / "config")
        for record in self.records:
            result = profile(record, config)
            self.assertEqual(result["features"]["borrower.type"], record["borrower"]["borrower_type"])
            json.dumps(result, allow_nan=False)
        original = parse_records((ROOT / "data/original-test-data.jsonl").read_text())[0]
        self.assertIsNone(profile(original, config)["features"]["borrower.type"])


if __name__ == "__main__":
    unittest.main()
