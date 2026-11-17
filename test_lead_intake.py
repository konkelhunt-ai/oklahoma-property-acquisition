from datetime import date
import unittest

from collector import SOURCE
from sync_lead_intake import HEADERS, plan_sync


class LeadIntakeTests(unittest.TestCase):
    today = date(2026, 11, 16)
    lead = "CREEK-CJ-25-417-801SMAINST"
    record = {
        "county": "Creek", "case_number": "CJ-25-417", "address": "801 S Main St Bristow",
        "source_url": SOURCE, "sale_date": "12/07/2026", "status": "Active",
        "appraisal": "$70,000",
    }

    def test_stage_once_and_link_existing_deal(self):
        changes, inserts = plan_sync([self.record] * 2, [], {self.lead}, self.today)
        self.assertEqual(changes, [])
        self.assertEqual(len(inserts), 1)
        self.assertEqual(len(inserts[0]), len(HEADERS))
        self.assertEqual(inserts[0][11], self.lead)
        self.assertEqual(plan_sync([self.record], inserts, {self.lead}, self.today), ([], []))

    def test_reschedule_and_recall_preserve_manual_fields(self):
        _, rows = plan_sync([self.record], [], set(), self.today)
        rows[0][13] = "Analyst"
        rows[0][15] = "Keep this note"
        recalled = dict(self.record, sale_date="12/14/2026", status="Recalled")
        changes, inserts = plan_sync([self.record, recalled], rows, set(), self.today)
        self.assertEqual(inserts, [])
        self.assertEqual([c["values"][0][0] for c in changes], ["2026-12-14", "Recalled on source"])
        self.assertEqual([c["range"].rsplit("!", 1)[1] for c in changes], ["G2", "K2"])

    def test_excludes_past_conflicting_status_and_unapproved_source(self):
        for records in [
            [dict(self.record, sale_date="11/15/2026")],
            [self.record, dict(self.record, status="Recalled")],
            [dict(self.record, source_url="https://example.com")],
        ]:
            self.assertEqual(plan_sync(records, [], set(), self.today), ([], []))

    def test_disappearance_preserves_last_date_and_does_not_imply_sale(self):
        _, rows = plan_sync([self.record], [], set(), self.today)
        another = dict(self.record, case_number="CJ-25-418", status="Inactive")
        changes, inserts = plan_sync([another], rows, set(), self.today)
        self.assertEqual(inserts, [])
        self.assertEqual(changes[0]["values"], [["Not on latest sheriff list — verify"]])
        self.assertEqual(plan_sync([], rows, set(), self.today), ([], []))

    def test_preserves_manual_rows(self):
        _, rows = plan_sync([self.record], [], set(), self.today)
        rows[0][7] = "https://example.com"
        self.assertEqual(plan_sync([self.record], rows, {self.lead}, self.today), ([], []))


if __name__ == "__main__":
    unittest.main()
