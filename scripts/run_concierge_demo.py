"""Scripted demonstration run of the Concierge Optimizer Loop."""

import json
from pathlib import Path

from dotenv import load_dotenv

from app.concierge_runner import run


def main():
    # app/.env is NOT auto-loaded for a plain `python` run (only adk web / agents-cli do that).
    load_dotenv(Path(__file__).resolve().parents[1] / "app" / ".env")
    user_request = "cheap PC build, minimize total price, budget 1500"
    print(f"Running run() with request: '{user_request}'...")
    try:
        response = run(user_request)
        print("\n--- Concierge Response ---")
        print(json.dumps(response, indent=2))
    except Exception as e:
        print(f"Failed to execute demo: {e}")
        print("Please check your GEMINI_API_KEY / environment configuration.")


if __name__ == "__main__":
    main()
