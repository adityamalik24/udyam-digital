"""Scores which dropped leads are worth a call. Uses only what is known when a lead arrives, so outcome columns can't leak.
Scores are cross-validated: a lead's score comes from a model that never saw it."""
from __future__ import annotations
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from .catalogue import DATA

# Language is left out on purpose: a lead shouldn't rank lower for the language its owner speaks.
CAT = ["lead_source", "segment", "city_tier", "has_gstin", "has_udyam", "annual_turnover_band", "current_internet", "current_provider", "contact_role"]
NUM = ["employee_count", "num_sites", "monthly_telecom_spend_inr"]
# Drops caused by our process, where a call can change the result. Excludes refusals, price and bad numbers.
RECOVERABLE = {"Owner had no time for a visit", "Visit not scheduled by sales", "Quote too complex to understand", "Quote took too long to arrive",
               "Found paperwork too long", "Missing GST or Udyam document", "Authorised signatory not available", "Unreachable after 3 attempts"}
SHOW = ["business_name", "segment", "city", "preferred_language", "lead_source", "drop_reason"]  # no contact details or identifiers


def score_leads() -> tuple[pd.DataFrame, float]:
    """Returns (recoverable dropped leads, best first; AUC across all leads)."""
    d = pd.read_csv(DATA / "smb_leads.csv")
    X = d[CAT + NUM].copy()
    X[CAT] = X[CAT].astype(str)
    X[NUM] = X[NUM].fillna(X[NUM].median())
    y = (d.outcome == "Activated").astype(int)
    model = make_pipeline(ColumnTransformer([("c", OneHotEncoder(handle_unknown="ignore"), CAT), ("n", StandardScaler(), NUM)]),
                          LogisticRegression(max_iter=2000, class_weight="balanced"))
    p = cross_val_predict(model, X, y, cv=5, method="predict_proba")[:, 1]
    d["score"] = (p * 100).round().astype(int)  # relative rank, not a probability: classes are reweighted
    model.fit(X, y)  # fitted once on everything, only to explain the ranking; the scores above stay cross-validated
    d["why"] = _reasons(model, X)
    out = d[d.drop_reason.isin(RECOVERABLE)].sort_values("score", ascending=False)
    out = out.assign(opening=out.drop_reason.map(OPENING))
    return out[SHOW + ["score", "why", "opening"]].reset_index(drop=True), float(roc_auc_score(y, p))


LABEL = {"lead_source": "came from", "segment": "segment", "city_tier": "city tier", "has_gstin": "has GSTIN", "has_udyam": "has Udyam", "annual_turnover_band": "turnover",
         "current_internet": "now uses", "current_provider": "now with", "employee_count": "staff", "num_sites": "sites", "monthly_telecom_spend_inr": "spends per month"}
# What to say first, by why the lead dropped. Each points to something the new journey actually changes.
OPENING = {"Owner had no time for a visit": "No visit needed now: you can see your price and finish the paperwork on your phone.",
           "Visit not scheduled by sales": "Sorry we never came back to you. You can get your price on your phone today, with no visit.",
           "Quote too complex to understand": "We now show one monthly price, with each item explained in plain words.",
           "Quote took too long to arrive": "Your price now appears straight away in the chat.",
           "Found paperwork too long": "It's four documents now, sent as phone photos, and we check them in minutes.",
           "Missing GST or Udyam document": "If your plan doesn't need a GSTIN, your ID and address proof are enough.",
           "Authorised signatory not available": "The signatory can upload their ID from their own phone, whenever suits them.",
           "Unreachable after 3 attempts": "Try a different time of day, and send the quote link so they can look when it suits them."}


def _reasons(model, X) -> list[str]:
    """The two features that lift each lead's score most: coefficient times its (scaled) value."""
    import numpy as np
    pre, lr = model[0], model[-1]
    Z = pre.transform(X)
    Z = Z.toarray() if hasattr(Z, "toarray") else np.asarray(Z)
    names = pre.get_feature_names_out()
    contrib = Z * lr.coef_[0]
    out = []
    for row, x in zip(contrib, X.itertuples(index=False)):
        top = [i for i in np.argsort(row)[::-1][:2] if row[i] > 0]
        words = []
        for i in top:
            kind, col = names[i].split("__", 1)
            if kind == "c":
                base = next(c for c in CAT if col.startswith(c + "_"))
                words.append(f"{LABEL.get(base, base)}: {col[len(base) + 1:]}")
            else:
                words.append(f"{LABEL.get(col, col)}: {getattr(x, col):g}")
        out.append("; ".join(words))
    return out
