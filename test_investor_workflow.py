import unittest
from sync_investor_workflow import (
    owner_status, text_formula, max_bid_formula, deposit_formula,
    DEALS_HEADERS, TEXTS_HEADERS, RESEARCH_HEADERS
)
class WorkflowTests(unittest.TestCase):
    def test_defendant_is_only_likely(self):
        self.assertEqual(owner_status("Tracy Dewayne Hayes","Needs assessor/deed verification"),"Likely court defendant")
        self.assertEqual(owner_status("Owner identity needs research","Needs assessor/deed verification"),"Unclear / estate")
        self.assertEqual(owner_status("Tracy Dewayne Hayes","Verified — source in notes"),"Owner verified")
    def test_new_text_is_manual_only(self):
        expressions=text_formula(2)
        self.assertEqual(len(expressions),5)
        self.assertIn("MATCH($L2",expressions[0])
        self.assertIn("voice.google.com",expressions[4])
        self.assertNotIn("send",expressions[4].lower())
    def test_offer_math_requires_real_costs(self):
        self.assertIn("ISNUMBER(K2)",max_bid_formula(2))
        self.assertIn("ISNUMBER(T2)",max_bid_formula(2))
        self.assertIn("10%",deposit_formula(2))
    def test_stable_schemas(self):
        self.assertEqual(len(DEALS_HEADERS),16)
        self.assertEqual(len(TEXTS_HEADERS),12)
        self.assertEqual(len(RESEARCH_HEADERS),22)
if __name__ == "__main__":unittest.main()
