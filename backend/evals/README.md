# Evaluation harness

Measures the **safety layers** with metrics instead of vibes. These are the parts
that decide whether a wrong or unsafe answer reaches a user, so they are the parts
worth quantifying.

## What it scores

| Detector | Source under test | Needs |
|----------|-------------------|-------|
| `router_injection` | `agents/router.py` — prompt-injection / jailbreak blocking | nothing |
| `guardrail_citation` | `guardrails/citation_check.py` | nothing |
| `guardrail_toxicity` | `guardrails/toxicity_check.py` | nothing |
| `guardrail_pii` | `guardrails/pii_check.py` | `presidio-analyzer` (else auto-skipped) |
| `hallucination` | `guardrails/hallucination_check.py` | real `OPENAI_API_KEY` + `--online` |

Each detector is treated as a **binary classifier** whose positive class is the
*catch* event (router "block", guardrail "flag"). The harness reports
**precision / recall / F1 / accuracy** plus the confusion matrix.

**Recall is the headline metric**: a missed injection or hallucination is far more
costly than a false alarm. The run **fails (exit 1)** if any detector's recall on
the dangerous class drops below `RECALL_GATE` (default `0.90`) — so it can gate CI.

## Run

```bash
cd backend
python -m evals.run_evals                 # offline detectors
python -m evals.run_evals --online        # also the OpenAI hallucination judge
python -m evals.run_evals --json out.json # persist full results
```

No live stack or paid API call is needed for the default run.

## Datasets

Labeled cases live in [`datasets/`](datasets/) as JSON — extend them freely:

- `router_cases.json` — `expect_block` per query (injection/jailbreak vs benign,
  including hard negatives like *"act on the feedback"* that must **not** trip the
  regex).
- `guardrail_cases.json` — `expect_pass` per answer, tagged with the `check` it
  targets.

A good answer to *"how do you know it works?"* is: **add a failing case, watch the
metric move, fix the detector.**

## Roadmap (retrieval eval)

Retrieval quality (recall@k, MRR, nDCG over a labeled query→document set) requires
the live Qdrant + ingested corpus, so it is not part of the offline run yet. The
binary-metric scaffolding in `metrics.py` is reused when that lands.
