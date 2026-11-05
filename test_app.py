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
        self.assertEqual(len(app.selectbox[0].options), 25)
        self.assertEqual(len(app.metric), 4)
        self.assertEqual(len(app.tabs), 7)
        self.assertEqual(app.tabs[1].label, "📄 Bureau report")
        for index in range(25):
            app.selectbox[0].select(index).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.error), 0)

    def test_individual_and_corporate_filters(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        app.radio(key="borrower-type-filter").set_value("Corporate").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.selectbox[0].options), 10)
        self.assertTrue(all("Corporate" in label for label in app.selectbox[0].options))
        app.selectbox[0].select(9).run()
        self.assertEqual(len(app.exception), 0)
        app.selectbox[1].select(1).run()
        self.assertEqual(len(app.exception), 0)
        app.radio(key="borrower-type-filter").set_value("Individual").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.selectbox[0].options), 15)
        self.assertTrue(all("Individual" in label for label in app.selectbox[0].options))

    def test_pasted_report_and_validation(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        app.sidebar.radio[0].set_value("Paste JSON").run()
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
