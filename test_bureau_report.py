"""Source fidelity checks for readable bureau reports and their exports."""
from copy import deepcopy
from html import unescape
import json
from pathlib import Path
import re
import unittest

from bureau_report import (source_value, source_sections, history_rows,
                           printable_report, facility_register, facility_sections)

ROOT = Path(__file__).resolve().parent


class BureauReportTests(unittest.TestCase):
    def test_missing_null_zero_and_false_remain_distinct(self):
        self.assertEqual(source_value(), "Not supplied")
        self.assertEqual(source_value(None), "Not reported (null)")
        self.assertEqual(source_value(0), "0")
        self.assertEqual(source_value(False), "No")
        self.assertEqual(source_value(1234.567, "USD"), "USD 1,234.567")
        _, _, metadata = source_sections({})
        self.assertEqual(dict(metadata)["Transaction date"], "Not supplied")

    def test_history_preserves_all_source_observations(self):
        observations = [
            {"period": "2026-03", "observation_status": "REPORTED", "days_past_due": 0},
            {"period": "2026-02", "observation_status": "NOT_REPORTED", "days_past_due": None},
            {"period": "2026-01", "observation_status": "NOT_APPLICABLE_NON_FUNDED"},
            {"period": "2025-12", "observation_status": "AFTER_CLOSURE", "days_past_due": 30},
        ]
        rows = history_rows({"payment_history_24m": observations})
        self.assertEqual([r["Period"] for r in rows], [r["period"] for r in observations])
        self.assertEqual([r["DPD (days)"] for r in rows], ["0", "Not reported (null)", "Not supplied", "30"])
        self.assertEqual(len(rows), 4)

    def test_bundled_reports_preserve_source_and_cover_both_entity_types(self):
        records = [json.loads(line) for line in (ROOT / "data/test-data.jsonl").read_text().splitlines()]
        kinds = set()
        for record in records:
            before = deepcopy(record)
            kind = record["borrower"]["borrower_type"]
            kinds.add(kind)
            title, identity, _ = source_sections(record)
            self.assertEqual(title, "Individual profile" if kind == "INDIVIDUAL" else "Corporate profile")
            self.assertIn("Employment type" if kind == "INDIVIDUAL" else "Legal form", dict(identity))
            html = printable_report(record)
            encoded = re.search(r'<pre id="source-json">(.*?)</pre>', html, re.S).group(1)
            self.assertEqual(json.loads(unescape(encoded)), record)
            self.assertEqual(html.count('class="facility-section"'), len(record["facilities"]))
            self.assertEqual(len(facility_register(record)), len(record["facilities"]))
            for facility in record["facilities"]:
                self.assertIn(facility["facility_id"], html)
                self.assertEqual(len(history_rows(facility)), len(facility["payment_history_24m"]))
            self.assertEqual(record, before)
        self.assertEqual(kinds, {"INDIVIDUAL", "CORPORATE"})

    def test_uploaded_strings_escape_html_and_currency_is_not_assumed(self):
        record = {"borrower": {"display_name": '<script>alert("x")</script>'},
                  "facilities": [{"facility_id": "F<1>", "latest_position": {"outstanding_principal": 12.25}}]}
        html = printable_report(record)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("F&lt;1&gt;", html)
        _, position = facility_sections(record["facilities"][0])
        self.assertEqual(dict(position)["Outstanding principal"], "[currency not supplied] 12.25")


if __name__ == "__main__":
    unittest.main()
