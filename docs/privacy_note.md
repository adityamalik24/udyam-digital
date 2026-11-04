# Data privacy and security note: Udyam Digital

**Scope.** Prototype with synthetic data, designed as if handling real customer data under the DPDP Act, 2023.

| Principle | What the design does |
|---|---|
| Notice and consent | A notice before any KYC data states what is collected, why, how long it is kept and who sees it, in English or Hindi. Each purpose has its own unticked checkbox: KYC verification (required), order updates (optional). We store purpose, notice version, language and timestamp. |
| Purpose limitation | KYC data is used only to verify the business and activate service. Order updates are a separate, optional consent. |
| Data minimisation | The advisor asks only for business facts. It never asks for Aadhaar, PAN or bank numbers. If a user volunteers one, it is removed before the text is stored, logged or sent to the LLM, and the user is pointed to KYC. |
| Retention | Uploaded images are held in memory during verification and never written to disk. We keep only the verdict, reason and masked fields. **Proposed policy, to be confirmed with legal:** keep these for the life of the service. |
| Masking | ID and GSTIN values appear in the UI and database as last 4 characters only. |
| Withdrawal | Consent can be withdrawn from the tracker. Withdrawing KYC consent deletes the stored KYC result; the consent record itself stays as proof, with a withdrawal timestamp. |
| Third parties | Document images and ID numbers never go to the LLM. Only redacted chat text does, and only when a key is configured. KYC runs locally with Tesseract. |
| Decision integrity | Code decides products, prices and verdicts. LLM output is validated, and any amount, product or promise not from the engines is discarded. |
| Fair outcomes | An automated `rejected` needs hard evidence: an inactive registration or a number that contradicts the registry. Anything uncertain goes to `needs_review` for a person. |
| Secrets | The API key comes from an environment variable. `.env` and the database are gitignored. |

**Not production-ready.** Before real use, this needs real authentication (the prototype has one demo user), encryption at rest for SQLite, audit logging, a processor agreement with the LLM vendor, a named grievance contact, and legal review of retention periods.
