"""
Trains a RandomForest classifier that estimates a beverage batch's
*spoilage / quality-failure risk* from its QC readings:
    pH, Brix (sugar content), microbial CFU/mL, storage temperature (C)

The training set is synthetic but domain-plausible: four beverage profiles
(juice, carbonated, iced tea, dairy) each with their own safe QC windows, a
temperature/microbial interaction (warm storage accelerates spoilage), and a
little label noise — so the model has to generalise rather than memorise a
single formula. Swap generate_synthetic_data() for a real lab dataset later
and re-run this script to retrain.

Run:  python -m app.ml.train_model
Produces: app/ml/model.pkl  +  app/ml/metrics.json
"""
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_validate, train_test_split
from sklearn.metrics import classification_report, accuracy_score, f1_score
import joblib

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")
METRICS_PATH = os.path.join(os.path.dirname(__file__), "metrics.json")
FEATURES = ["ph", "brix", "microbial_cfu", "temperature_c"]

# Beverage profiles: sampling ranges for healthy product + the safe QC window
# used to derive labels. Real thresholds vary by product/regulator.
PROFILES = {
    "juice": {
        "ph": (3.4, 0.35, 2.4, 5.2), "brix": (12.5, 2.0, 5, 22),
        "microbial": (25, 1.1), "temp": (4.0, 1.6, -1, 15),
        "safe": {"ph": (3.0, 4.6), "brix": (8, 16), "microbial": 100, "temp": 8},
    },
    "carbonated": {
        "ph": (3.0, 0.3, 2.2, 4.5), "brix": (10.5, 1.8, 4, 20),
        "microbial": (10, 1.2), "temp": (6.0, 2.0, 0, 18),
        "safe": {"ph": (2.5, 4.2), "brix": (6, 14), "microbial": 100, "temp": 10},
    },
    "iced_tea": {
        "ph": (4.0, 0.4, 2.8, 5.5), "brix": (9.0, 1.7, 3, 18),
        "microbial": (35, 1.15), "temp": (4.5, 2.2, -1, 18),
        "safe": {"ph": (3.0, 5.0), "brix": (5, 14), "microbial": 100, "temp": 8},
    },
    "dairy": {
        "ph": (6.6, 0.2, 5.8, 7.2), "brix": (10.5, 1.2, 7, 15),
        "microbial": (18, 1.2), "temp": (3.0, 1.5, -1, 12),
        "safe": {"ph": (6.3, 6.9), "brix": (9, 12), "microbial": 100, "temp": 7},
    },
}


def label_row(profile: dict, ph, brix, microbial_cfu, temperature_c) -> int:
    """Label = 1 (risky) if any reading falls outside the profile's safe window."""
    safe = profile["safe"]
    risky = 0
    if not (safe["ph"][0] <= ph <= safe["ph"][1]):
        risky = 1
    if not (safe["brix"][0] <= brix <= safe["brix"][1]):
        risky = 1
    if microbial_cfu > safe["microbial"]:
        risky = 1
    if temperature_c > safe["temp"] or temperature_c < -1:
        risky = 1
    return risky


def generate_synthetic_data(n=8000, seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    names = list(PROFILES)

    for _ in range(n):
        name = names[rng.integers(len(names))]
        p = PROFILES[name]

        ph = float(np.clip(rng.normal(p["ph"][0], p["ph"][1]), p["ph"][2], p["ph"][3]))
        brix = float(np.clip(rng.normal(p["brix"][0], p["brix"][1]), p["brix"][2], p["brix"][3]))
        temperature_c = float(np.clip(rng.normal(p["temp"][0], p["temp"][1]), p["temp"][2], p["temp"][3]))

        # Warm storage accelerates spoilage — couple microbial load to temp.
        microbial_cfu = float(rng.lognormal(mean=np.log(p["microbial"][0]), sigma=p["microbial"][1]))
        microbial_cfu *= float(np.exp(0.12 * max(0.0, temperature_c - 4.0)))

        label = label_row(p, ph, brix, microbial_cfu, temperature_c)

        # ~2% label noise (rounding, lab error) so the model doesn't assume
        # perfection — mirrors real QC datasets.
        if rng.random() < 0.02:
            label = 1 - label

        rows.append({
            "ph": round(ph, 2), "brix": round(brix, 2),
            "microbial_cfu": round(microbial_cfu, 1),
            "temperature_c": round(temperature_c, 2),
            "risky": label,
        })

    return pd.DataFrame(rows)


def train(verbose: bool = True) -> dict:
    df = generate_synthetic_data()
    X = df[FEATURES]
    y = df["risky"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=300, max_depth=10, min_samples_leaf=4,
        class_weight="balanced", random_state=42, n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

    cv = cross_validate(clf, X, y, cv=5,
                        scoring=["accuracy", "f1"], n_jobs=-1)

    importances = sorted(
        [{"feature": f, "importance": round(float(i), 4)}
         for f, i in zip(FEATURES, clf.feature_importances_)],
        key=lambda d: d["importance"], reverse=True,
    )

    metrics = {
        "trained_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z",
        "n_samples": int(len(df)),
        "positive_rate": round(float(y.mean()), 3),
        "holdout": {
            "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
            "f1": round(float(f1_score(y_test, y_pred)), 4),
            "precision": round(float(report["1"]["precision"]), 4),
            "recall": round(float(report["1"]["recall"]), 4),
        },
        "cross_validation": {
            "folds": 5,
            "accuracy_mean": round(float(cv["test_accuracy"].mean()), 4),
            "accuracy_std": round(float(cv["test_accuracy"].std()), 4),
            "f1_mean": round(float(cv["test_f1"].mean()), 4),
            "f1_std": round(float(cv["test_f1"].std()), 4),
        },
        "feature_importances": importances,
        "confusion": {
            "true_negatives": int(report["0"]["support"]),
            "true_positives": int(report["1"]["support"]),
        },
    }

    joblib.dump(clf, MODEL_PATH)
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    if verbose:
        print("=== Holdout report ===")
        print(classification_report(y_test, y_pred, zero_division=0))
        print("=== 5-fold cross-validation ===")
        print(f"  accuracy: {metrics['cross_validation']['accuracy_mean']:.3f} "
              f"(±{metrics['cross_validation']['accuracy_std']:.3f})")
        print(f"  f1:       {metrics['cross_validation']['f1_mean']:.3f} "
              f"(±{metrics['cross_validation']['f1_std']:.3f})")
        print("=== Feature importances ===")
        for fi in importances:
            print(f"  {fi['feature']:<16} {fi['importance']:.3f}")
        print(f"Model saved to {MODEL_PATH}")
        print(f"Metrics saved to {METRICS_PATH}")

    return metrics


if __name__ == "__main__":
    train()
