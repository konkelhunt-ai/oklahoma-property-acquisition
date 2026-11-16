"""Collect official Creek County sheriff listings; never infer missing values."""
import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SOURCE = "https://www.creekcountysheriff.gov/sheriff-sales"
FIELDS = ["lead_id", "county", "case_number", "status", "sale_date", "appraisal", "minimum_bid", "plaintiff", "defendant", "address", "description", "source_url", "checked_at"]


def clean(value):
    return re.sub(r"\\s+", " ", value or "").strip()


def extract(html, checked_at=None):
    soup = BeautifulSoup(html, "html.parser")
    # Preserve line boundaries in the official site's text.
    lines = [clean(line) for line in soup.get_text("\\n").splitlines()]
    lines = [line for line in lines if line]
    starts = [i for i, line in enumerate(lines) if re.match(r"^Case#\\s+(?:CJ|CV)-\\d{2}-\\d+", line, re.I)]
    starts.append(len(lines))
    out = []
    for i, j in zip(starts, starts[1:]):
        block = lines[i:j]
        if not block:
            continue
        joined = "\\n".join(block)
        def value(label):
            match = re.search(r"(?im)^" + re.escape(label) + r":?\\s*(.*)$", joined)
            return clean(match.group(1)) if match else ""
        case = re.search(r"^Case#\\s+([^\\s]+)", block[0], re.I)
        if not case:
            continue
        status = value("Status")
        date = value("Sale Date")
        address = value("Address")
        # The same court case may contain several distinct lots.
        key = "|".join(["Creek", case.group(1), date, address]).lower()
        import hashlib
        lead_id = "CREEK-" + hashlib.sha256(key.encode()).hexdigest()[:14]
        out.append({
            "lead_id": lead_id, "county": "Creek", "case_number": case.group(1),
            "status": status, "sale_date": date, "appraisal": value("Appraisal Amount"),
            "minimum_bid": value("Minimum Bid Amount"),
            "plaintiff": value("Plantiff") or value("Plaintiff"),
            "defendant": value("Defendant"), "address": address,
            "description": value("Description"), "source_url": SOURCE,
            "checked_at": checked_at or datetime.now(timezone.utc).isoformat(),
        })
    return out


def main():
    response = requests.get(SOURCE, timeout=40, headers={"User-Agent": "OklahomaAcquisitionResearch/1.0 (public records monitoring)"})
    response.raise_for_status()
    records = extract(response.text)
    if not records:
        raise RuntimeError("No sale records parsed: source layout may have changed. No empty overwrite.")
    folder = Path("output")
    folder.mkdir(exist_ok=True)
    (folder / "creek_sheriff.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    with (folder / "creek_sheriff.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    active = sum(r["status"].lower() == "active" for r in records)
    print(f"Collected {len(records)} Creek County records, {active} marked active.")
    # Keep a historical snapshot; never auto-mark missing records as sold.
    print("Source: " + SOURCE)


if __name__ == "__main__":
    main()
