"""Exercise the real app, including historical evidence and session caching."""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


class DashboardSmokeTest(unittest.TestCase):
    def test_local_analysis_and_historical_navigation(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'dashboard.py'), default_timeout=60).run()
        self.assertFalse(app.exception)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.tabs), 5)
        repo = app.session_state['repo']
        try:
            choices = app.selectbox(key='snapshot_choice').options
            if len(choices) > 1:
                app.selectbox(key='snapshot_choice').select(choices[-1]).run()
                self.assertFalse(app.exception)
                self.assertIs(app.session_state['repo'], repo)
                app.selectbox(key='snapshot_choice').select('Latest workspace').run()
                self.assertFalse(app.exception)
            search = next(t for t in app.text_input if t.label == 'Search files or findings')
            search.input('complexity').run()
            self.assertFalse(app.exception)
        finally:
            repo.close()


if __name__ == '__main__':
    unittest.main()
