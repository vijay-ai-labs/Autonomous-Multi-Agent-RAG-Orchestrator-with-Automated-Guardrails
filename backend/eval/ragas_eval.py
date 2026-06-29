"""RAGAS metric runner over a pre-generated eval dataset.

Heavy deps (``ragas``, ``datasets``) are imported at module level inside a
``try/except`` so the names are patchable in unit tests (``eval.ragas_eval.evaluate``,
``eval.ragas_eval.Dataset``) yet a missing install never breaks import — that lets
adversarial-only CI runs, which never call :func:`run_ragas`, skip these packages.
Gate thresholds live in :data:`GATES`; any metric below its threshold lands in
``gate_failures`` and flips ``passed`` to False.
"""

import json
import logging
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

try:  # heavy, optional — only needed when run_ragas() is actually called
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    _RAGAS_METRICS = [faithfulness, answer_relevancy, context_precision, context_recall]
except ImportError:  # pragma: no cover - exercised only when deps absent
    Dataset = None  # type: ignore[assignment,misc]
    evaluate = None  # type: ignore[assignment]
    _RAGAS_METRICS = []

DATASET_PATH = Path(__file__).parent / "datasets" / "eval_dataset.json"


class EvalEntry(TypedDict):
    question: str
    ground_truth: str
    answer: str
    contexts: list[str]


class RAGASReport(TypedDict):
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float
    passed: bool
    gate_failures: list[str]


GATES = {
    "faithfulness": 0.85,
    "answer_relevancy": 0.80,
    "context_precision": 0.75,
    "context_recall": 0.70,
}


def load_dataset(path: Path = DATASET_PATH) -> list[EvalEntry]:
    """Load the pre-generated eval dataset from JSON."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_ragas(dataset: list[EvalEntry]) -> RAGASReport:
    """Run RAGAS metrics on a pre-generated dataset.

    Uses ``ragas.evaluate()`` over a ``datasets.Dataset`` built from the entries
    and returns a :class:`RAGASReport` with per-metric scores and gate results.
    """
    if evaluate is None or Dataset is None:
        raise RuntimeError(
            "ragas and datasets must be installed to run RAGAS evaluation "
            "(pip install ragas datasets)."
        )

    data = {
        "question": [e["question"] for e in dataset],
        "answer": [e["answer"] for e in dataset],
        "contexts": [e["contexts"] for e in dataset],
        "ground_truth": [e["ground_truth"] for e in dataset],
    }
    hf_dataset = Dataset.from_dict(data)

    result = evaluate(hf_dataset, metrics=_RAGAS_METRICS)
    scores = result.to_pandas().mean().to_dict()

    gate_failures = []
    for metric, threshold in GATES.items():
        score = scores.get(metric, 0.0)
        if score < threshold:
            gate_failures.append(f"{metric}={score:.3f} < {threshold}")

    return RAGASReport(
        faithfulness=scores.get("faithfulness", 0.0),
        answer_relevancy=scores.get("answer_relevancy", 0.0),
        context_precision=scores.get("context_precision", 0.0),
        context_recall=scores.get("context_recall", 0.0),
        passed=len(gate_failures) == 0,
        gate_failures=gate_failures,
    )
