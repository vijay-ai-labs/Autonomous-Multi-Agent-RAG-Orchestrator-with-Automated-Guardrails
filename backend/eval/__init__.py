"""SP4 evaluation suite: RAGAS quality metrics + adversarial safety tests.

``eval.runner`` orchestrates everything for CI; ``eval.ragas_eval`` runs the
quality metrics on a pre-generated dataset; ``eval.adversarial`` holds the
attack suites that exercise graph logic without any live API calls.
"""
