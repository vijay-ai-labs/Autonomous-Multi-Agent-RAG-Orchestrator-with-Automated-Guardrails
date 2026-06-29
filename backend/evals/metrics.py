"""Binary-classification metrics for the eval harness.

Positive class is the *detection* event (router "block", guardrail "flag"). A
confusion matrix is built from (expected_positive, predicted_positive) pairs and
turned into precision / recall / F1 / accuracy.
"""

from dataclasses import dataclass


@dataclass
class Confusion:
    """Counts for a binary detector. Positive = the thing we want to catch."""

    tp: int = 0  # correctly flagged
    fp: int = 0  # flagged a clean item (false alarm)
    fn: int = 0  # missed a bad item (the dangerous one)
    tn: int = 0  # correctly let a clean item through

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.total if self.total else 0.0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 1.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def observe(self, expected_positive: bool, predicted_positive: bool) -> None:
        if expected_positive and predicted_positive:
            self.tp += 1
        elif expected_positive and not predicted_positive:
            self.fn += 1
        elif not expected_positive and predicted_positive:
            self.fp += 1
        else:
            self.tn += 1

    def as_dict(self) -> dict:
        return {
            "n": self.total,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }
