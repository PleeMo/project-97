"""
Loads the trained model (or falls back to a rule-based scorer if the model
hasn't been trained yet) and exposes risk_score() for use by the API.
"""
import json
import os

import joblib
import pandas as pd

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")
METRICS_PATH = os.path.join(os.path.dirname(__file__), "metrics.json")
FEATURES = ["ph", "brix", "microbial_cfu", "temperature_c"]

_model = None


def _load():
    if os.path.exists(MODEL_PATH):
        try:
            return joblib.load(MODEL_PATH)
        except Exception as exc:  # corrupt/incompatible pickle -> rule-based fallback
            print(f"Warning: could not load ML model ({exc}); using rule-based scorer.")
    return None


_model = _load()


def reload_model():
    """Re-read model.pkl from disk (used after an online retrain)."""
    global _model
    _model = _load()
    return _model is not None


def _rule_based_fallback(ph, brix, microbial_cfu, temperature_c) -> float:
    """Used only if model.pkl hasn't been generated yet (run train_model.py)."""
    score = 0
    if ph is not None and (ph < 3.0 or ph > 4.6):
        score += 30
    if brix is not None and (brix < 8 or brix > 16):
        score += 20
    if microbial_cfu is not None and microbial_cfu > 100:
        score += 35
    if temperature_c is not None and temperature_c > 8:
        score += 25
    return min(score, 100)


def risk_score(ph: float = None, brix: float = None,
               microbial_cfu: float = None, temperature_c: float = None) -> dict:
    """
    Returns {"risk_score": 0-100, "result": "pass"|"fail", "source": "ml"|"rule_based"}
    """
    if _model is not None:
        # Impute missing readings with safe mid-range defaults so partial QC
        # entries still get a score.
        row = pd.DataFrame([{
            "ph": ph if ph is not None else 3.7,
            "brix": brix if brix is not None else 12.0,
            "microbial_cfu": microbial_cfu if microbial_cfu is not None else 10.0,
            "temperature_c": temperature_c if temperature_c is not None else 4.0,
        }], columns=FEATURES)
        proba = _model.predict_proba(row)[0]
        classes = list(_model.classes_)
        risky_idx = classes.index(1) if 1 in classes else len(classes) - 1
        score = float(proba[risky_idx] * 100)
        result = "fail" if score >= 50 else "pass"
        return {"risk_score": round(score, 1), "result": result, "source": "ml"}

    score = _rule_based_fallback(ph, brix, microbial_cfu, temperature_c)
    result = "fail" if score >= 50 else "pass"
    return {"risk_score": float(score), "result": result, "source": "rule_based"}


def model_info(extra: dict = None) -> dict:
    """Metadata for the dashboard: metrics from the last training run."""
    info = {
        "source": "ml" if _model is not None else "rule_based",
        "trained_at": None,
        "sklearn_version": None,
        "n_samples": None,
        "holdout": None,
        "cross_validation": None,
        "feature_importances": None,
        "message": None,
    }

    if os.path.exists(METRICS_PATH):
        try:
            with open(METRICS_PATH) as f:
                info.update(json.load(f))
        except Exception:
            pass

    if _model is None:
        info["message"] = ("No trained model found — running `python -m app.ml.train_model` "
                           "or the admin retrain endpoint enables ML scoring. "
                           "A rule-based scorer is being used instead.")
    else:
        try:
            import sklearn
            info["sklearn_version"] = sklearn.__version__
        except Exception:
            pass
        info["message"] = "RandomForest risk model loaded."

    if extra:
        info.update(extra)
    return info
