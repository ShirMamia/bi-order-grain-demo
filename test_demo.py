import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from demo import build_report, create_model, summarize


class OrderGrainTests(unittest.TestCase):
    def setUp(self):
        self.db = create_model()
        self.addCleanup(self.db.close)

    def test_item_weighted_measure_differs_from_order_kpi(self):
        self.assertEqual(summarize(self.db), {
            'on_time_orders': 3, 'eligible_orders': 4, 'missing_dates': 1,
            'sales_cents': 33100, 'on_time_lines': 4, 'eligible_lines': 10,
        })

    def test_filters_use_the_customer_dimension(self):
        north = summarize(self.db, 'North')
        south = summarize(self.db, 'South')
        self.assertEqual((north['on_time_orders'], north['eligible_orders']), (2, 2))
        self.assertEqual((south['on_time_orders'], south['eligible_orders']), (1, 2))
        self.assertEqual((south['on_time_lines'], south['eligible_lines']), (1, 7))
        self.assertEqual(summarize(self.db, 'Unknown')['eligible_orders'], 0)

    def test_delivery_eligibility(self):
        flags = dict(self.db.execute('SELECT order_id, on_time FROM FactOrder'))
        self.assertEqual(flags['O-103'], 1)  # Delivered on the promised date.
        self.assertIsNone(flags['O-105'])  # Actual date is missing.
        self.assertIsNone(flags['O-106'])  # Canceled.

    def test_duplicate_item_key_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?)', ('O-101', 1, 'P-01', 'S-01', 100, 0))

    def test_report_matches_sql_and_checked_in_artifact(self):
        with TemporaryDirectory() as target:
            output = Path(target)
            build_report(self.db, output)
            html = (output / 'report.html').read_text(encoding='utf-8')
            payload = json.loads(html.split('id="report-data">')[1].split('</script>')[0])
            self.assertEqual(payload['statistics'][0]['eligible_orders'], 4)
            self.assertEqual(payload['statistics'][2]['eligible_lines'], 7)
            self.assertEqual(len(list((output / 'model').glob('*.csv'))), 6)
            self.assertEqual(html, Path(__file__).with_name('report.html').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
