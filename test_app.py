"""UI smoke tests using Streamlit's browser-independent AppTest runner."""
import json
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent


class AppTests(unittest.TestCase):
    def test_bundled_reports_render_and_selection_updates(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0)
        self.assertEqual(len(app.selectbox[0].options), 5)
        self.assertEqual(len(app.metric), 4)
        self.assertEqual(len(app.tabs), 6)
        for index in range(5):
            app.selectbox[0].select(index).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.error), 0)

    def test_pasted_report_and_validation(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        app.radio[0].set_value("Paste JSON").run()
        self.assertEqual(len(app.metric), 0)
        text = json.dumps({"transaction": {"id": "PASTED"}, "borrower": {"borrower_id": "BORROWER"},
                           "analysis_reporting_period": "2026-03", "facilities": []})
        app.text_area[0].set_value(text).run()
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.metric[0].value, "0")
        app.text_area[0].set_value("not json").run()
        self.assertEqual(len(app.metric), 0)
        app.button[0].click().run()
        self.assertGreater(len(app.error), 0)
        self.assertEqual(len(app.exception), 0)


if __name__ == "__main__":
    unittest.main()
