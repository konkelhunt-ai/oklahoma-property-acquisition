import unittest
from datetime import date
from sync_current_sales import choose_rows, HEADERS

class CurrentSalesTests(unittest.TestCase):
    def test_only_active_upcoming_sales_get_displayed(self):
        records=[
            {"case_number":"CJ-26-8","status":"Active","sale_date":"12/07/2026","address":"23569 W 102nd St S, Sapulpa, OK","minimum_bid":"$130,000","appraisal":"$195,000","defendant":"Marquise Stubblefield, et al"},
            {"case_number":"CJ-25-398","status":"Recalled","sale_date":"11/16/2026","address":"7910 Challenger St, Sapulpa, OK","defendant":"Unknown heirs"},
            {"case_number":"CJ-25-363","status":"Recalled","sale_date":"11/16/2026","address":"716 N Moccasin Pl, Sapulpa, OK","defendant":"Durell Ingram"},
            {"case_number":"CJ-26-150","status":"Inactive","sale_date":"11/16/2026","address":"2705 Hickory Bluff Rd, Sapulpa, OK","defendant":"Jordan Dozier"},
            {"case_number":"CJ-25-100","status":"Active","sale_date":"10/01/2026","address":"123 Main St, Sapulpa, OK","defendant":"Old Party"},
        ]
        r=choose_rows(records,[["Address","City","Likely Owner"]],date(2026,11,16),"2026-11-16")
        self.assertEqual(len(r),1)
        self.assertEqual(r[0][0],"23569 W 102nd St S")
        self.assertIn("NOT deed verified",r[0][3])
        self.assertEqual(r[0][8],"CJ-26-8")
        self.assertEqual(len(r[0]),len(HEADERS))
    def test_manually_verified_owner_survives(self):
        records=[{"case_number":"CJ-26-8","status":"Active","sale_date":"12/07/2026","address":"23569 W 102nd St S, Sapulpa, OK","defendant":"Defendant Name"}]
        deals=[["Address","City","Likely Owner"]+[""]*11,
               [""]*2+["Deed Owner","Owner verified"]+[""]*9+["CREEK-CJ-26-8-23569W102NDS"]]
        r=choose_rows(records,deals,date(2026,11,16),"checked")
        self.assertEqual(r[0][2],"Deed Owner")
        self.assertIn("Deed verified",r[0][3])
    def test_no_active_is_no_legacy_leads(self):
        self.assertEqual(choose_rows([{"status":"Inactive"}],[],date(2026,11,16),"checked"),[])
if __name__=="__main__":unittest.main()
