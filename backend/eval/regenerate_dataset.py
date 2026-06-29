#!/usr/bin/env python3
"""Regenerate eval_dataset.json by running the live pipeline against test questions.

Requires running Docker services + indexed documents. Each generated answer is
used as its own ``ground_truth`` baseline — review and tighten ground truths
before committing the result for RAGAS scoring.

Usage: python -m eval.regenerate_dataset
"""
import asyncio
import json
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

TEST_QUESTIONS = [
    "How many vacation days do full-time employees receive per year?",
    "What is the process for resetting a forgotten work password?",
    "What does the code of conduct say about conflicts of interest?",
    "How do I enroll in the company health insurance plan?",
    "What is the remote work policy for employees?",
    "How many sick days are employees entitled to?",
    "What is the expense reimbursement process?",
    "How do I submit a formal complaint to HR?",
    "What software is approved for installation on company laptops?",
    "What is the policy on using personal devices for work?",
    "How do I request parental leave?",
    "What is the performance review cycle and process?",
    "What are the rules around social media and company confidentiality?",
    "How do I access the employee benefits portal?",
    "What is the company's policy on overtime pay?",
    "How long is the probationary period for new employees?",
    "What training is mandatory for all new hires?",
    "What is the process for requesting a salary review?",
    "How do I report a workplace safety hazard?",
    "What are the guidelines for business travel bookings?",
]


async def regenerate():
    from agents.graph import compiled_graph
    from answer.session import load_session

    dataset = []
    for question in TEST_QUESTIONS:
        session_id, _history = await load_session(None)
        state = {
            "query": question,
            "session_id": session_id,
            "user_id": str(uuid.uuid4()),
            "doc_type": None,
            "department": None,
            "query_id": str(uuid.uuid4()),
            "session_history": [],
            "route": "",
            "route_reason": None,
            "verification_passed": False,
            "verification_reason": "",
            "top_score": 0.0,
            "retrieved_chunks": [],
            "answer": None,
            "citations": [],
            "context_block": None,
            "refused": False,
            "refusal_reason": None,
            "agent_trace": [],
            "guardrail_passed": False,
            "guardrail_result": "",
            "guardrail_details": {},
            "escalation_id": None,
        }
        final = await compiled_graph.ainvoke(state)

        if final.get("refused") or not final.get("answer"):
            logger.warning("Skipping '%s' — refused or no answer", question[:60])
            continue

        contexts = [c["content"] for c in final.get("retrieved_chunks", [])]
        dataset.append(
            {
                "question": question,
                "answer": final["answer"],
                "contexts": contexts[:4],
                "ground_truth": final["answer"],  # generated answer as baseline
            }
        )
        logger.info("Generated: %s", question[:60])

    out = Path(__file__).parent / "datasets" / "eval_dataset.json"
    out.write_text(json.dumps(dataset, indent=2))
    logger.info("Wrote %d entries to %s", len(dataset), out)


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    asyncio.run(regenerate())
