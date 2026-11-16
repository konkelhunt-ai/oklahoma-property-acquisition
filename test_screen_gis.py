"""Local regression checks for screening review flags."""
import unittest
from screen_gis import classify

class ScreeningTests(unittest.TestCase):
    def test_unmatched_is_not_candidate(self):
        self.assertEqual(classify("Not found", "", "", "")[0], "UNMATCHED")
    def test_common_land_flagged(self):
        self.assertEqual(classify("Exact parcel match", "A COMMON AREA", "LOT 3", "1")[0], "SPECIAL-USE RISK")
    def test_strip_flagged(self):
        self.assertEqual(classify("Exact parcel match", "", "WLY 25FT LOTS 002 THRU 005", "0.2296")[0], "STRIP / ACCESS RISK")
    def test_small_lot_flagged(self):
        self.assertEqual(classify("Exact parcel match", "", "LOT 12", "0.0763")[0], "SMALL PARCEL")
    def test_candidate_requires_review(self):
        self.assertEqual(classify("Exact parcel match", "100 MAIN ST", "LOT 12", "0.25")[0], "RESEARCH CANDIDATE")

if __name__ == "__main__":
    unittest.main()
