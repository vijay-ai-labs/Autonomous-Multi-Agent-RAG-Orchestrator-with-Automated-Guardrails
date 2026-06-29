#!/usr/bin/env python3
"""Run all eval suites and produce a JSON report.

Exit code 0 = all gates passed. Exit code 1 = any failure.

Usage:
    python -m eval.runner                        # full eval
    python -m eval.runner --skip-ragas           # adversarial only (faster, no API)
    python -m eval.runner --report-file out.json
"""
import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level="INFO", format="%(levelname)s %(message)s")


def run_adversarial() -> dict:
    """Run adversarial pytest suites, return pass/fail per suite."""
    suites = [
        ("injection", "eval/adversarial/test_injection.py"),
        ("jailbreak", "eval/adversarial/test_jailbreak.py"),
        ("refusal", "eval/adversarial/test_refusal.py"),
        ("pii_output", "eval/adversarial/test_pii_output.py"),
    ]
    results = {}
    for name, path in suites:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", path, "-v", "--tb=short", "-q"],
            capture_output=True,
            text=True,
        )
        passed = proc.returncode == 0
        results[name] = {"passed": passed, "output": proc.stdout[-2000:]}
        logger.info("Adversarial %s: %s", name, "PASS" if passed else "FAIL")
    return results


def run_ragas_eval() -> dict:
    """Run RAGAS metrics on the pre-generated dataset."""
    from eval.ragas_eval import load_dataset, run_ragas

    dataset = load_dataset()
    report = run_ragas(dataset)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ragas", action="store_true")
    parser.add_argument("--report-file", default="eval_report.json")
    args = parser.parse_args()

    report = {"adversarial": {}, "ragas": {}, "overall_passed": False}

    # 1. Adversarial suites
    report["adversarial"] = run_adversarial()
    adversarial_passed = all(v["passed"] for v in report["adversarial"].values())

    # 2. RAGAS eval
    if not args.skip_ragas:
        report["ragas"] = run_ragas_eval()
        ragas_passed = report["ragas"].get("passed", False)
    else:
        report["ragas"] = {"skipped": True}
        ragas_passed = True

    report["overall_passed"] = adversarial_passed and ragas_passed

    # Write report
    Path(args.report_file).write_text(json.dumps(report, indent=2))
    logger.info("Eval report written to %s", args.report_file)

    if not report["overall_passed"]:
        logger.error("EVAL GATE FAILED")
        if not adversarial_passed:
            for suite, result in report["adversarial"].items():
                if not result["passed"]:
                    logger.error("  FAIL: %s", suite)
        if not ragas_passed and not args.skip_ragas:
            for failure in report["ragas"].get("gate_failures", []):
                logger.error("  FAIL: %s", failure)
        sys.exit(1)

    logger.info("ALL EVAL GATES PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
