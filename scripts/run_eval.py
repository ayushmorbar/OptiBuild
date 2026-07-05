"""Admin-only entry point for the GAUSS evaluation suite.

The 23-case evaluation runs the live agent (LLM calls billed on real credits) and
is meant for INTERNAL quality testing only. It is gated behind an explicit opt-in:

    GAUSS_EVAL_ENABLED=1  (required — refuses to run otherwise)

Defaults are cost-bounded: one-shot modelization (GAUSS_FAST_MODELIZATION=1) and
generation only. Grading (Vertex eval service, GCP-billed) is a separate opt-in.

Usage (PowerShell):
    $env:GAUSS_EVAL_ENABLED = "1"; uv run python scripts/run_eval.py
    $env:GAUSS_EVAL_ENABLED = "1"; uv run python scripts/run_eval.py --mode staged
    $env:GAUSS_EVAL_ENABLED = "1"; uv run python scripts/run_eval.py --grade --project <GCP_PROJECT>
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / ".agents-cli-scripts" / "_inference_runner.py"
DATASET = REPO_ROOT / "tests" / "eval" / "datasets" / "basic-dataset.json"
TRACES = REPO_ROOT / "artifacts" / "traces" / "traces_baseline.json"
EVAL_CONFIG = REPO_ROOT / "tests" / "eval" / "eval_config.yaml"


def require_admin_gate() -> None:
    """Refuse to run unless the admin opt-in env var is set."""
    if os.environ.get("GAUSS_EVAL_ENABLED") != "1":
        sys.exit(
            "Evaluation is DISABLED.\n"
            "The eval suite runs the live agent over 23 cases and spends real "
            "LLM credits; it is intended for internal quality testing by admins "
            "only.\nTo proceed, explicitly set:  GAUSS_EVAL_ENABLED=1"
        )


def main() -> None:
    require_admin_gate()

    parser = argparse.ArgumentParser(
        description="Run the GAUSS eval suite (admin only)."
    )
    parser.add_argument(
        "--mode",
        choices=["fast", "staged"],
        default="fast",
        help="fast = one-shot modelization, ~5x fewer LLM calls (default); "
        "staged = full 4-stage loop + LLM judge (costlier, highest fidelity).",
    )
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--output", default=str(TRACES))
    parser.add_argument(
        "--grade",
        action="store_true",
        help="Also grade the generated traces (Vertex eval service, GCP-billed).",
    )
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
    args = parser.parse_args()

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if args.mode == "fast":
        env["GAUSS_FAST_MODELIZATION"] = "1"
    else:
        env.pop("GAUSS_FAST_MODELIZATION", None)

    if not RUNNER.exists():
        sys.exit(
            f"Inference runner not found at {RUNNER}. Run once:  agents-cli eval generate\n"
            "(it stages the runner script), or copy _inference_runner.py there."
        )

    print(f"[eval] mode={args.mode} dataset={args.dataset}")
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-u",
            str(RUNNER),
            str(REPO_ROOT / "app"),
            args.dataset,
            args.output,
        ],
        cwd=str(REPO_ROOT),
        env=env,
    )
    if result.returncode != 0:
        sys.exit(f"[eval] generation failed (exit {result.returncode})")
    print(f"[eval] traces written to {args.output}")

    if args.grade:
        if not args.project:
            sys.exit("[eval] --grade requires --project (or GOOGLE_CLOUD_PROJECT).")
        agents_cli = shutil.which("agents-cli") or "agents-cli"
        grade = subprocess.run(
            [
                agents_cli,
                "eval",
                "grade",
                "--traces",
                args.output,
                "--config",
                str(EVAL_CONFIG),
                "--project",
                args.project,
                "--output",
                str(REPO_ROOT / "artifacts" / "eval"),
            ],
            cwd=str(REPO_ROOT),
            env=env,
        )
        if grade.returncode != 0:
            sys.exit(f"[eval] grading failed (exit {grade.returncode})")
        print("[eval] grading complete -> artifacts/eval/")


if __name__ == "__main__":
    main()
