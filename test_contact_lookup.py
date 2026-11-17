import unittest
from sync_contact_lookup import row_for, review_gate, field_formula, HEADERS

class ContactLookupTests(unittest.TestCase):
    def test_contact_row_has_links_but_no_invented_phone(self):
        row=row_for("CREEK-CJ-25-417-801SMAINST",
                    "Assessor match — deed pending",11)
        self.assertEqual(len(row),len(HEADERS))
        self.assertIn("truepeoplesearch.com/results?name=",row[4])
        self.assertIn("truepeoplesearch.com/results?streetaddress=",row[5])
        self.assertEqual(row[7],"")
        self.assertEqual(row[8],"Not reviewed")
        self.assertEqual(row[9],"Not reviewed")
        self.assertEqual(row[13],"CREEK-CJ-25-417-801SMAINST")
    def test_protect_manual_verification(self):
        self.assertIn("G4",review_gate(4))
        self.assertIn("I4",review_gate(4))
        self.assertIn("J4",review_gate(4))
        self.assertIn("K4",review_gate(4))
        self.assertIn("REGEXREPLACE",review_gate(4))
    def test_source_lookup_by_stable_lead(self):
        self.assertIn("MATCH(N6",field_formula("C",6))
    def test_estate_discrepancy_flagged(self):
        for status in ["Estate / deceased — deed pending",
                       "Sheriff address discrepancy — research",
                       "Assessor/defendant mismatch — deed pending"]:
            row=row_for("LEAD",status,3)
            self.assertTrue(row[12].startswith("HOLD:"))
if __name__=="__main__":unittest.main()
