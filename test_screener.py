import unittest
import pandas as pd
from screener import _score, _in_ranges, _duration_facts

class ScreenerUnitTests(unittest.TestCase):
    def test_score_is_bounded(self):
        score = _score(200, 100, 50, True, 1e9, 1e8, 36, 0, 1, 5000, 100, 3)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_missing_data_does_not_create_high_score(self):
        missing = _score(None, None, None, None, None, None, None, None, None, None, None, None)
        strong = _score(50, 20, 10, True, 1e9, 1e8, 36, 0, 1, 5000, 100, 3)
        self.assertLess(missing, strong)

    def test_sic_range(self):
        self.assertTrue(_in_ranges("6021", [(6000,6799)]))
        self.assertFalse(_in_ranges("3571", [(6000,6799)]))

    def test_duration_fact_excludes_annual_periods(self):
        cf = {"facts":{"us-gaap":{"RevenueFromContractWithCustomerExcludingAssessedTax":{
            "units":{"USD":[
                {"end":"2025-03-31","start":"2025-01-01","val":100,"form":"10-Q","filed":"2025-05-01"},
                {"end":"2025-12-31","start":"2025-01-01","val":500,"form":"10-K","filed":"2026-02-01"}
            ]}
        }}}}
        result = _duration_facts(cf,["RevenueFromContractWithCustomerExcludingAssessedTax"])
        self.assertEqual(len(result),1)
        self.assertEqual(float(result.iloc[0]["val"]),100)

if __name__ == "__main__":
    unittest.main()
