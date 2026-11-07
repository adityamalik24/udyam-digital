# Personal data breach runbook: Udyam Digital

What we do if personal data may have been exposed. Written for the prototype; the times are our reading of the DPDP Act, 2023 and the DPDP Rules, 2025, and must be confirmed with legal before real use.

## What we hold, and what can't leak
- **Held:** consent records, orders, KYC verdicts with masked fields (last 4 characters), call-back contact details, data-rights requests, an audit log of codes.
- **Never held:** document images, voice recordings, full ID or GSTIN numbers. Chat text is redacted before it is stored or sent to the LLM.

## Steps
| When | Who | What |
|---|---|---|
| As soon as it's noticed | Whoever spots it | Tell the on-call engineer and the grievance officer. Don't delete logs |
| First hour | Engineer | Contain: rotate the `LLM_API_KEY` and any other secret, stop the app if data is still leaking, keep a copy of the database for investigation |
| First day | Grievance officer | Work out whose data and which fields, using the audit log. Tell each affected person without delay: what happened, what data, what we're doing, what they can do, and who to contact |
| Without delay, then within 72 hours | Grievance officer | Tell the Data Protection Board of India: first a short notice, then a full report with the cause, the people and data affected, what we did, and how we'll stop it happening again |
| After | Team | Fix the cause, add a test that would have caught it, and update this runbook |

## Where to look
- `audit` table: who did what, as session references and codes.
- Partner queue, Logs tab: the same, on screen.
- `core/retention.py`: what is deleted automatically, and when.
