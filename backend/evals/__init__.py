"""Offline evaluation harness for the safety layers (router + guardrails).

Runs without the live stack or any paid API call: the router and the
citation/toxicity/PII checks are pure functions. The hallucination check needs
OpenAI and is only exercised with ``--online``.
"""
