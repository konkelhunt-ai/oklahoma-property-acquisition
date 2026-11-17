"""Stage current official Creek listings in the existing New Lead Intake sheet."""
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

from collector import SOURCE
from sync_owner_queue import INPUT, SHEET_ID, iso_date, key, parse_address

TAB = "New Lead Intake"
HEADERS = [
    "Discovered At", "County", "Property Address", "Parcel / Legal Description",
    "Lead Type", "Case Number", "Sale Date", "Source URL", "Source Published Date",
    "Officially Verified", "Status", "Existing Lead ID", "Import Status",
    "Research Owner", "Last Checked", "Notes",
]
VERIFIED = "Yes — official sheriff page"


def listing_key(case, address):
    case = str(case or "").strip().upper()
    street_and_city = re.sub(r"\s*,?\s+OK(?:\s+\d{5}(?:-\d{4})?)?\s*$", "", address or "", flags=re.I)
    address_key = re.sub(r"[^A-Z0-9]", "", street_and_city.upper())
    if not re.fullmatch(r"(?:CJ|CV)-\d{2,4}-\d{1,6}", case) or not address_key:
        return None
    return case, address_key


def official_source(url):
    return url.rstrip("/") in (SOURCE, SOURCE.replace("www.", ""))


def plan_sync(records, existing, deal_ids, today):
    indexed = defaultdict(list)
    for number, original in enumerate(existing, 2):
        row = (original + [""] * len(HEADERS))[:len(HEADERS)]
        identity = listing_key(row[5], row[2])
        if row[1].strip().lower() == "creek" and identity:
            indexed[identity].append((number, row))

    listings = defaultdict(list)
    unresolved_cases = set()
    for record in records:
        if record.get("county") != "Creek" or not official_source(record.get("source_url", "")):
            continue
        address = record.get("address", "")
        identity = listing_key(record.get("case_number"), address)
        day = iso_date(record.get("sale_date", ""))
        status = str(record.get("status", "")).strip().lower()
        if not identity or not day or status not in {"active", "recalled", "inactive", "sold", "postponed", "cancelled", "canceled"}:
            continue
        if re.match(r"^(?:see details|unknown|address unavailable)\b", address, re.I):
            # The sheriff sometimes publishes a placeholder for acreage. Match
            # only an unambiguous already-staged case on the same sale date.
            candidates = [
                old_key for old_key, matches in indexed.items()
                if old_key[0] == identity[0] and len(matches) == 1
                and iso_date(matches[0][1][6]) == day
                and official_source(matches[0][1][7]) and matches[0][1][9] == VERIFIED
            ]
            if len(candidates) != 1:
                unresolved_cases.add(identity[0])
                continue
            identity = candidates[0]
        listings[identity].append((day, status, record))

    updates, inserts = [], []
    checked = today.isoformat()
    for identity, versions in sorted(listings.items()):
        latest = max(day for day, _, _ in versions)
        current = [(status, record) for day, status, record in versions if day == latest]
        if len({status for status, _ in current}) != 1 or len(indexed.get(identity, ())) > 1:
            continue
        status, record = current[0]
        address = record["address"]
        parsed = parse_address(address)
        candidate_id = key(identity[0], parsed[0]) if parsed else ""
        deal_id = candidate_id if candidate_id in deal_ids else ""
        active = status == "active" and latest > today
        label = ("Active on source" if active else
                 "Sale date reached — verify" if status == "active" else
                 status.capitalize() + " on source")
        if identity in indexed:
            number, row = indexed[identity][0]
            if not official_source(row[7]) or row[9] != VERIFIED:
                continue
            for column, value, old in [
                ("G", latest.isoformat(), row[6]),
                ("K", label, row[10]),
                ("L", row[11] or deal_id, row[11]),
                ("O", checked, row[14]),
            ]:
                if value != old:
                    updates.append({"range": f"'{TAB}'!{column}{number}", "values": [[value]]})
        elif active:
            figures = "; ".join(
                f"{label} {record[field]}" for label, field in
                [("Appraisal", "appraisal"), ("Minimum bid", "minimum_bid")] if record.get(field)
            )
            display_address = f"{parsed[0]}, {parsed[1]}, OK" if parsed else address
            inserts.append([
                checked, "Creek", display_address, "", "Sheriff foreclosure", identity[0],
                latest.isoformat(), SOURCE, "", VERIFIED, label, deal_id,
                "Verified public listing", "", checked, figures,
            ])
    # An official row that disappears needs review; disappearance alone does
    # not establish a recall, cancellation or completed sale.
    if listings:
        for identity, matches in indexed.items():
            if identity in listings or identity[0] in unresolved_cases or len(matches) != 1:
                continue
            number, row = matches[0]
            if official_source(row[7]) and row[9] == VERIFIED and row[10] == "Active on source":
                updates.extend([
                    {"range": f"'{TAB}'!K{number}", "values": [["Not on latest sheriff list — verify"]]},
                    {"range": f"'{TAB}'!O{number}", "values": [[checked]]},
                ])
    return updates, inserts


def main():
    records = json.loads(INPUT.read_text(encoding="utf-8"))
    if not records:
        raise RuntimeError("Missing official auction records; intake was left unchanged.")
    credentials = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    book = gspread.authorize(credentials).open_by_key(SHEET_ID)
    target = book.worksheet(TAB)
    existing = target.get_all_values()
    deals = book.worksheet("01 DEALS").get_all_values()
    if not existing or existing[0][:len(HEADERS)] != HEADERS:
        raise RuntimeError("Unexpected New Lead Intake headers")
    if not deals or deals[0][13:14] != ["Lead ID"]:
        raise RuntimeError("Unexpected 01 DEALS lead ID header")
    deal_ids = {row[13] for row in deals[1:] if len(row) > 13 and row[13]}
    updates, inserts = plan_sync(records, existing[1:], deal_ids, datetime.now(ZoneInfo("America/Chicago")).date())
    for start in range(0, len(updates), 100):
        book.values_batch_update({"valueInputOption": "RAW", "data": updates[start:start + 100]})
    if inserts:
        target.append_rows(inserts, value_input_option="RAW", table_range="A:P")
    print(f"Lead intake: {len(inserts)} listings added, {len(updates)} source fields refreshed.")


if __name__ == "__main__":
    main()
