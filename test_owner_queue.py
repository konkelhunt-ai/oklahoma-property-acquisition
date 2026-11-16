import unittest
from datetime import date
from sync_owner_queue import parse_address, rows_from_records

class OwnerQueueTests(unittest.TestCase):
    def test_valid_sapulpa_address(self):
        self.assertEqual(parse_address("23569 W 102nd St S, Sapulpa, OK 74066"),("23569 W 102nd St S","Sapulpa"))
    def test_unusable_address_rejected(self):
        self.assertIsNone(parse_address("0 UNKNOWN SAPULPA"))
        self.assertIsNone(parse_address("Sapulpa, OK"))
    def test_future_active_record_keeps_owner_unverified(self):
        x=rows_from_records([{"address":"23569 W 102nd St S, Sapulpa, OK 74066",
            "case_number":"CJ-26-8","status":"Active","sale_date":"12/07/2026",
            "defendant":"Named Defendant","minimum_bid":"130000","appraisal":"195000"}],date(2026,11,16))
        self.assertEqual(len(x),1)
        self.assertEqual(x[0][2],"NOT YET VERIFIED")
        self.assertEqual(x[0][3],"Named Defendant")
        self.assertEqual(x[0][4],"2026-12-07")
    def test_past_or_recalled_not_added(self):
        x=rows_from_records([
            {"address":"23569 W 102nd St S, Sapulpa, OK","case_number":"CJ-26-8","status":"Recalled","sale_date":"12/07/2026"},
            {"address":"6125 W Hilton Rd, Sapulpa, OK","case_number":"CJ-26-122","status":"Active","sale_date":"10/01/2026"}],
            date(2026,11,16))
        self.assertEqual(x,[])
if __name__=="__main__":unittest.main()
