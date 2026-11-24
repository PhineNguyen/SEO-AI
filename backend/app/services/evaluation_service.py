"""Quantitative evaluation harness for Search Intent and Keyword Clustering (Golden Dataset)."""

from pydantic import BaseModel, Field
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

INTENT_LABELS = ["INFORMATIONAL", "NAVIGATIONAL", "COMMERCIAL", "TRANSACTIONAL"]


class ClassMetrics(BaseModel):
    """Per-class Precision, Recall, F1, and support count."""

    precision: float
    recall: float
    f1: float
    support: int


class IntentEvaluationReport(BaseModel):
    """Reproducible classification benchmark metrics on a manually labeled Golden Dataset."""

    total_samples: int
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    per_class: dict[str, ClassMetrics] = Field(default_factory=dict)
    misclassified_examples: list[dict[str, str]] = Field(default_factory=list)


def evaluate_intent_predictions(
    *,
    keywords: list[str],
    y_true: list[str],
    y_pred: list[str],
) -> IntentEvaluationReport:
    """Compute Accuracy, Macro Precision/Recall/F1, and per-class metrics."""
    if len(y_true) != len(y_pred) or len(keywords) != len(y_true):
        raise ValueError("keywords, y_true, and y_pred must have equal lengths")

    acc = float(accuracy_score(y_true, y_pred))
    prec, rec, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=INTENT_LABELS,
        zero_division=0,
    )
    macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=INTENT_LABELS,
        average="macro",
        zero_division=0,
    )

    per_class = {
        label: ClassMetrics(
            precision=round(float(prec[i]), 4),
            recall=round(float(rec[i]), 4),
            f1=round(float(f1[i]), 4),
            support=int(support[i]),
        )
        for i, label in enumerate(INTENT_LABELS)
    }

    misclassified = [
        {"keyword": kw, "expected": truth, "predicted": pred}
        for kw, truth, pred in zip(keywords, y_true, y_pred, strict=True)
        if truth != pred
    ]

    return IntentEvaluationReport(
        total_samples=len(y_true),
        accuracy=round(acc, 4),
        macro_precision=round(float(macro_p), 4),
        macro_recall=round(float(macro_r), 4),
        macro_f1=round(float(macro_f1), 4),
        per_class=per_class,
        misclassified_examples=misclassified,
    )
