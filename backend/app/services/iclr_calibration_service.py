from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any


def _rank_data(values: list[float]) -> list[float]:
    """Compute average ranks (1-based) with tie handling for Spearman correlation."""
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def compute_pearson_correlation(x: list[float], y: list[float]) -> float:
    """Compute Pearson linear correlation coefficient r in [-1, 1]."""
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    den_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    den_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
    if den_x == 0.0 or den_y == 0.0:
        return 0.0
    return round(num / (den_x * den_y), 4)


def compute_spearman_correlation(x: list[float], y: list[float]) -> dict[str, float]:
    """Compute Spearman rank correlation rho and approximate two-sided t-distribution p-value."""
    n = len(x)
    if n != len(y) or n < 2:
        return {"spearman_rho": 0.0, "p_value_approx": 1.0}
    rx = _rank_data(x)
    ry = _rank_data(y)
    rho = compute_pearson_correlation(rx, ry)
    if abs(rho) >= 1.0 or n <= 2:
        p_approx = 0.0 if abs(rho) >= 1.0 else 1.0
    else:
        t_stat = abs(rho) * math.sqrt((n - 2) / max(1e-12, 1.0 - rho * rho))
        # Normal-tail approximation for two-sided p-value
        p_approx = round(math.erfc(t_stat / math.sqrt(2.0)), 6)
    return {"spearman_rho": rho, "p_value_approx": p_approx}


def evaluate_review_calibration_metrics(
    *,
    human_decisions: list[int],
    llm_decisions: list[int],
    human_scores: list[float],
    llm_scores: list[float],
) -> dict[str, Any]:
    """Compute classification metrics (Accuracy, F1, FPR, FNR) plus Spearman & Pearson score correlations."""
    if not human_decisions or len(human_decisions) != len(llm_decisions):
        raise ValueError("human_decisions and llm_decisions must have equal non-zero length")

    n = len(human_decisions)
    tp = sum(1 for h, p in zip(human_decisions, llm_decisions) if h == 1 and p == 1)
    tn = sum(1 for h, p in zip(human_decisions, llm_decisions) if h == 0 and p == 0)
    fp = sum(1 for h, p in zip(human_decisions, llm_decisions) if h == 0 and p == 1)
    fn = sum(1 for h, p in zip(human_decisions, llm_decisions) if h == 1 and p == 0)

    accuracy = round((tp + tn) / n, 4)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0
    fpr = round(fp / (fp + tn), 4) if (fp + tn) > 0 else 0.0
    fnr = round(fn / (fn + tp), 4) if (fn + tp) > 0 else 0.0

    spearman = compute_spearman_correlation(human_scores, llm_scores)
    pearson_r = compute_pearson_correlation(human_scores, llm_scores)

    return {
        "sample_count": n,
        "accuracy": accuracy,
        "f1": f1,
        "fpr": fpr,
        "fnr": fnr,
        "spearman_rho": spearman["spearman_rho"],
        "spearman_p_value_approx": spearman["p_value_approx"],
        "pearson_r": pearson_r,
    }


def load_iclr_calibration_benchmark(
    ratings_tsv_path: str | Path,
    llm_review_csv_path: str | Path,
) -> dict[str, Any]:
    """Load offline ICLR calibration TSV + LLM review CSV and compute full calibration report including Spearman rho."""
    ratings_path = Path(ratings_tsv_path)
    llm_path = Path(llm_review_csv_path)

    human_map: dict[str, tuple[int, float]] = {}
    with ratings_path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            paper_id = (row.get("paper_id") or row.get("id") or "").strip()
            decision_str = (row.get("decision") or "").strip().lower()
            if not paper_id or decision_str == "withdrawn":
                continue
            human_dec = 0 if "reject" in decision_str else 1
            ratings_vals: list[float] = []
            for k in range(7):
                val = row.get(f"rating_{k}")
                if val is not None and str(val).strip() != "":
                    try:
                        ratings_vals.append(float(val))
                    except ValueError:
                        pass
            if ratings_vals:
                human_map[paper_id] = (human_dec, sum(ratings_vals) / len(ratings_vals))

    human_decisions: list[int] = []
    llm_decisions: list[int] = []
    human_scores: list[float] = []
    llm_scores: list[float] = []

    with llm_path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            paper_id = (row.get("paper_id") or row.get("id") or "").strip()
            if paper_id not in human_map:
                # Fallback positional match if paper_id is not explicitly named
                keys = list(human_map.keys())
                if idx < len(keys):
                    paper_id = keys[idx]
                else:
                    continue
            Overall_raw = row.get("Overall")
            Decision_raw = (row.get("Decision") or "").strip().lower()
            if Overall_raw is None or str(Overall_raw).strip() == "":
                continue
            try:
                llm_overall = float(Overall_raw)
            except ValueError:
                continue
            h_dec, h_score = human_map[paper_id]
            human_decisions.append(h_dec)
            llm_decisions.append(1 if Decision_raw == "accept" else 0)
            human_scores.append(h_score)
            llm_scores.append(llm_overall)

    return evaluate_review_calibration_metrics(
        human_decisions=human_decisions,
        llm_decisions=llm_decisions,
        human_scores=human_scores,
        llm_scores=llm_scores,
    )
