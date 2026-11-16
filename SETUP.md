# Deployment and next steps

## Working first stage
The workflow runs daily at 13:17 UTC (not a fixed local time across DST) and on demand.
It reads the official Creek County sheriff-sales page and saves a JSON and CSV snapshot
as a **private GitHub Actions artifact**. It retains canceled/recalled records and
does not mistake the same court case's separate lots for duplicates.

### First test
Go to repository > Actions > Collect official Oklahoma auction records > Run workflow.
Open the resulting run and download its `creek-auctions-...` artifact. Inspect the log.
The job fails rather than writing an empty dataset when the source cannot be parsed.

## Not yet wired
- Google Sheets writeback requires a securely provisioned Google service account with
  spreadsheet edit access and a GitHub Actions secret. Do not commit credentials.
- Tulsa County's public Excel/PDF auction feed needs a verified parser.
- Additional counties, tax resales, and foreclosure court records need distinct adapters.
- Ownership/contact lookups and individual Google Voice sending are not automatic.
- Personal Google Voice has no supported general-purpose SMS automation API.
- All outreach needs manual review, opt-out handling, and applicable legal compliance.

Master sheet: https://docs.google.com/spreadsheets/d/1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ/edit
