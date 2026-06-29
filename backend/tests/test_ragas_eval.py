"""Unit tests for eval.ragas_eval — RAGAS itself is mocked (no live API calls)."""
import re
from unittest.mock import MagicMock, patch


def test_load_dataset_returns_list():
    from eval.ragas_eval import load_dataset

    dataset = load_dataset()
    assert isinstance(dataset, list)
    assert len(dataset) > 0
    entry = dataset[0]
    assert "question" in entry
    assert "answer" in entry
    assert "contexts" in entry
    assert "ground_truth" in entry


def test_dataset_answers_contain_citations():
    from eval.ragas_eval import load_dataset

    dataset = load_dataset()
    pattern = re.compile(r"\[Source\s+\d+\]", re.I)
    for entry in dataset:
        assert pattern.search(entry["answer"]), (
            f"Dataset entry missing citation: {entry['question'][:60]}"
        )


def test_ragas_report_schema():
    from eval.ragas_eval import load_dataset, run_ragas

    mock_result = MagicMock()
    mock_df = MagicMock()
    mock_df.mean.return_value.to_dict.return_value = {
        "faithfulness": 0.92,
        "answer_relevancy": 0.88,
        "context_precision": 0.81,
        "context_recall": 0.77,
    }
    mock_result.to_pandas.return_value = mock_df

    with patch("eval.ragas_eval.evaluate", return_value=mock_result), patch(
        "eval.ragas_eval.Dataset"
    ):
        dataset = load_dataset()
        report = run_ragas(dataset)

    assert report["faithfulness"] == 0.92
    assert report["passed"] is True
    assert report["gate_failures"] == []


def test_ragas_gate_failure():
    from eval.ragas_eval import load_dataset, run_ragas

    mock_result = MagicMock()
    mock_df = MagicMock()
    mock_df.mean.return_value.to_dict.return_value = {
        "faithfulness": 0.70,  # below 0.85 gate
        "answer_relevancy": 0.88,
        "context_precision": 0.81,
        "context_recall": 0.77,
    }
    mock_result.to_pandas.return_value = mock_df

    with patch("eval.ragas_eval.evaluate", return_value=mock_result), patch(
        "eval.ragas_eval.Dataset"
    ):
        report = run_ragas(load_dataset())

    assert report["passed"] is False
    assert any("faithfulness" in f for f in report["gate_failures"])
