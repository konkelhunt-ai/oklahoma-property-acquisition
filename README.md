# Oklahoma Property Acquisition System

Private project for monitoring upcoming Oklahoma sheriff auctions, tax resales, and foreclosure filings, prioritizing Tulsa County and surrounding counties.

## Workflow
1. Collect permitted official county auction and court records.
2. Verify current auction dates and case status, preserve source links, and deduplicate leads.
3. Save verified leads to the Google Sheets master database.
4. Research ownership and contact information using permitted sources.
5. Prepare individualized outreach drafts for human approval; do not send texts automatically.
6. Log sent messages, replies, opt-outs, and follow-up status.

## Status
Repository initialized. Automated collectors, Google credentials, and messaging integration are **not yet deployed**.

## Security
Never commit passwords, Google service-account JSON, phone lists, or API tokens. Use GitHub Actions encrypted secrets. Respect source access terms, privacy, consent, and do-not-call requirements.

Master database: https://docs.google.com/spreadsheets/d/1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ/edit
