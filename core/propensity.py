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

CAT = ["lead_source", "segment", "city_tier", "has_gstin", "has_udyam", "annual_turnover_band", "current_internet", "current_provider", "preferred_language", "contact_role"]
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
    out = d[d.drop_reason.isin(RECOVERABLE)].sort_values("score", ascending=False)
    return out[SHOW + ["score"]].reset_index(drop=True), float(roc_auc_score(y, p))
