"""NL front-end demo executing the entire modelization in one-shot."""

import json
import sys
import uuid
from pathlib import Path

# Load env file if present
try:
    from dotenv import load_dotenv

    # Resolve repo root and search for .env
    repo_root = Path(__file__).resolve().parents[1]
    env_paths = [repo_root / "app" / ".env", repo_root / ".env"]
    for path in env_paths:
        if path.exists():
            load_dotenv(path)
            break
except ImportError:
    pass

from app.concierge_runner import build_catalog_summary
from app.evaluator import evaluate_deterministic
from app.llm_extractor import make_oneshot_extractor
from app.modelization import build_schema_oneshot
from app.schema import SolverRequest, SolverRequestContext
from solver_app.agent import solve


def main():
    user_request = (
        " ".join(sys.argv[1:])
        or "cheap PC build, minimize total price, budget 1500 and maximize memory"
    )
    print(f"Executing one-shot modelization for query: '{user_request}'...")

    try:
        # 1. Build catalog summary and extract whole schema at once
        cat_summary = build_catalog_summary()
        oneshot_extractor = make_oneshot_extractor()

        print("Calling LLM extractor (one-shot)...")
        schema = build_schema_oneshot(user_request, cat_summary, oneshot_extractor)
        print("PivotSchema assembled successfully.")
        print(schema.model_dump_json(indent=2))

        # 2. Run deterministic evaluation check
        print("\nEvaluating schema...")
        fb = evaluate_deterministic(schema, 1)
        print(f"Evaluation passed: {fb.passed}")

        if fb.passed:
            # 3. Request solve to in-process Solver Specialist
            print("\nCalling Solver Specialist...")
            req = SolverRequest(
                transaction_id=str(uuid.uuid4()),
                iteration=1,
                pivot_schema=schema,
                context=SolverRequestContext(original_prompt=user_request),
            )
            response = solve(req.model_dump())
            print("\n--- Solver Specialist Response ---")
            print(json.dumps(response, indent=2))
        else:
            print("\n--- Evaluation Feedback (Failed) ---")
            print(fb.model_dump_json(indent=2))

    except ValueError as e:
        # Schema-assembly failure: the LLM output could not be repaired into a
        # valid model. In the full concierge loop this feeds the REPAIR pass.
        print(f"\nModelization failed: {e}")
        print("Tip: rerun, or rephrase the request (this is not a credentials issue).")
    except Exception as e:
        print(f"\nFailed to execute one-shot demo: {e}")
        print("Please check your GOOGLE_API_KEY / environment setup.")


if __name__ == "__main__":
    main()
