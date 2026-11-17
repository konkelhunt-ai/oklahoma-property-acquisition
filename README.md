# Oklahoma Property Acquisition System

Project for monitoring upcoming Oklahoma sheriff auctions, tax resales, and foreclosure filings, prioritizing Tulsa County and surrounding counties.

## Workflow
1. Collect permitted official county auction and court records.
2. Verify current auction dates and case status, preserve source links, and deduplicate leads.
3. Save verified leads to the Google Sheets master database.
4. Research ownership and contact information using permitted sources.
5. Prepare individualized outreach drafts for human approval; do not send texts automatically.
6. Log sent messages, replies, opt-outs, and follow-up status.

## Status
The daily Creek County workflow collects official sheriff sales, refreshes **00 CURRENT SALES**, and reconciles **New Lead Intake** with the existing deal IDs. Intake stages upcoming official listings and tracks changes to dates and statuses. Rows that disappear are flagged for verification. Owner research, budgets and outreach approvals are maintained in their respective sheets.

Tulsa's official Excel report is inspected separately for freshness. The linked historical report does not feed current deals. Court, title, ownership and contact checks are handled in the review workflow. The XT Homes popup prepares individual drafts for manual use in Google Voice.

## Security
Never commit passwords, Google service-account JSON, phone lists, or API tokens. Use GitHub Actions encrypted secrets. Respect source access terms, privacy, consent, and do-not-call requirements.

Master database: https://docs.google.com/spreadsheets/d/1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ/edit
