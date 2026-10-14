import os
import tempfile
import unittest
import pandas as pd
from backtest import evaluate_point_in_time, load_candidates

class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", encoding="utf-8")
        self.tmp.write("date,ticker,score,forward_return_pct,benchmark_return_pct\n")
        self.tmp.write("2024-01-01,AAA,90,12,5\n")
        self.tmp.write("2024-01-01,BBB,80,8,5\n")
        self.tmp.write("2024-01-01,CCC,20,-4,5\n")
        self.tmp.write("2024-02-01,AAA,85,-2,-1\n")
        self.tmp.write("2024-02-01,BBB,75,6,-1\n")
        self.tmp.write("2024-02-01,CCC,10,-8,-1\n")
        self.tmp.close()
    def tearDown(self):
        os.unlink(self.tmp.name)
    def test_top_fraction_and_cost(self):
        summary, by_date, picks = evaluate_point_in_time(self.tmp.name, top_fraction=0.25, cost_bps=20)
        self.assertEqual(summary["rebalance_dates"], 2)
        self.assertEqual(len(picks), 2)
        self.assertAlmostEqual(by_date.iloc[0]["net_return_pct"], 11.8, places=6)
        self.assertAlmostEqual(by_date.iloc[1]["net_return_pct"], -2.2, places=6)
    def test_benchmark_excess(self):
        _, by_date, _ = evaluate_point_in_time(self.tmp.name, top_fraction=0.25, cost_bps=0)
        self.assertAlmostEqual(by_date.iloc[0]["excess_return_pct"], 7.0, places=6)
    def test_reject_bad_score(self):
        bad = self.tmp.name + ".bad.csv"
        pd.DataFrame([{"date":"2024-01-01","ticker":"AAA","score":120,"forward_return_pct":3}]).to_csv(bad,index=False)
        try:
            with self.assertRaises(ValueError): load_candidates(bad)
        finally: os.unlink(bad)
    def test_required_columns(self):
        bad = self.tmp.name + ".bad.csv"
        pd.DataFrame([{"date":"2024-01-01","ticker":"AAA"}]).to_csv(bad,index=False)
        try:
            with self.assertRaises(ValueError): load_candidates(bad)
        finally: os.unlink(bad)

if __name__ == "__main__":
    unittest.main()
