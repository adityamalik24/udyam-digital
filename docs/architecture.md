# Architecture

```mermaid
flowchart TD
  U[Owner on phone] --> UI[Streamlit pages: Advisor, Quote, Consent, KYC, Tracker]
  UI --> ADV[advisor.py: conversation flow]
  ADV --> RED[guardrails: redact identifiers, screen input]
  RED --> EXT[Regex extraction]
  RED -. redacted text only, optional .-> LLM[(LLM API)]
  LLM -. fields, validated .-> ADV
  EXT --> ADV
  ADV --> RULES[rules.py: eligibility, dependencies, smallest bundle]
  RULES --> PRICE[pricing.py: server-side price]
  PRICE --> CAT[(product_catalogue.csv)]
  RULES --> CAT
  ADV -. wording only .-> LLM
  LLM -. checked by guardrails, else template .-> ADV
  UI --> CONS[consent.py]
  UI --> KYC[kyc: Tesseract OCR in memory, validators, cross-checks]
  KYC --> REG[(Mock GSTIN and Udyam registries)]
  KYC --> V[verified / needs_review / rejected]
  UI --> ORD[orders.py: stage machine]
  CONS --> DB[(SQLite: masked fields only)]
  V --> DB
  ORD --> DB
  ADV -->|hand-off summary| DB
```

**Key choice:** the LLM can fill profile gaps and reword replies. It cannot choose a product or a price, and the advisor works fully without it.
