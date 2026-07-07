"""Interactive command-line chat (REPL) for the GAUSS Concierge Agent.

Loads credentials, generates fresh session UUIDs on startup, prints agent 
interactions and tool calls in real-time, and automatically saves a complete 
session trace file (in standard platform flat events format) inside 
artifacts/traces/ on exit.

Usage:
    uv run python scripts/chat.py
"""

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from dotenv import load_dotenv

# Ensure the root directory and app directory are in the import path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Load .env credentials before importing ADK/GenAI
load_dotenv(REPO_ROOT / ".env")

from google.genai import types
from google.adk.runners import InMemoryRunner
from app.agent import root_agent


def serialize_event(event):
    """Utility to turn an ADK Event object into a JSON-serializable dictionary with camelCase fields."""
    return event.model_dump(mode="json", by_alias=True, exclude_none=True)


async def main():
    # Generate unique IDs matching standard platform format
    session_id = str(uuid.uuid4())
    user_id = "user"

    schema_only = "--schema-only" in sys.argv

    if schema_only:
        print("====================================================")
        print("GAUSS Schema Extractor (One-Shot / Staged Modelization)")
        print(f"Active Session ID: {session_id}")
        print("====================================================\n")
        
        try:
            user_input = input("User > ")
            if not user_input.strip():
                print("Empty input. Exiting.")
                return

            print("Agent > Running modelization...")
            import app.concierge_runner
            result = app.concierge_runner.run(user_input)
            
            schema = result.get("schema")
            if schema is not None:
                schema_json_str = schema.model_dump_json(indent=2)
                print("\n--- GENERATED PIVOT SCHEMA ---")
                print(schema_json_str)
                
                # Build flat events list for the platform trace
                user_event = {
                    "id": str(uuid.uuid4()),
                    "timestamp": time.time(),
                    "invocationId": f"e-{uuid.uuid4()}",
                    "author": "user",
                    "content": {
                        "role": "user",
                        "parts": [{"text": user_input}]
                    },
                    "actions": {"stateDelta": {}, "artifactDelta": {}, "requestedAuthConfigs": {}, "requestedToolConfirmations": {}},
                    "nodeInfo": {"path": ""}
                }
                agent_event = {
                    "id": str(uuid.uuid4()),
                    "timestamp": time.time() + 1.0,
                    "invocationId": f"e-{uuid.uuid4()}",
                    "author": "root_agent",
                    "content": {
                        "role": "model",
                        "parts": [{"text": schema_json_str}]
                    },
                    "actions": {"stateDelta": {}, "artifactDelta": {}, "requestedAuthConfigs": {}, "requestedToolConfirmations": {}},
                    "nodeInfo": {"path": "root_agent@1"}
                }
                flat_events = [user_event, agent_event]
                
                # Save trace and logs
                trace_data = {
                    "id": session_id,
                    "appName": "app",
                    "userId": user_id,
                    "state": {
                        "__session_metadata__": {
                            "displayName": user_input[:60] + "..." if len(user_input) > 60 else user_input
                        }
                    },
                    "events": flat_events
                }
                
                trace_dir = REPO_ROOT / "artifacts" / "traces"
                trace_dir.mkdir(parents=True, exist_ok=True)
                
                output_filepath = trace_dir / f"chat_trace_{session_id}.json"
                with open(output_filepath, "w", encoding="utf-8") as out_f:
                    json.dump(trace_data, out_f, indent=2)
                
                log_filepath = trace_dir / f"chat_log_{session_id}.jsonl"
                with open(log_filepath, "w", encoding="utf-8") as log_f:
                    for event in flat_events:
                        log_f.write(json.dumps(event) + "\n")
                
                print(f"\n[info] Session trace successfully saved to: {output_filepath}")
                print(f"[info] Session log successfully saved to: {log_filepath}")
            else:
                print("\n[error] Modelization failed to produce a schema.")
                if result.get("questions"):
                    print("Clarification needed / Errors:")
                    for q in result["questions"]:
                        print(f" - {q}")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
        return

    runner = InMemoryRunner(agent=root_agent, app_name="app")
    runner.auto_create_session = True
    
    flat_events = []

    try:
        while True:
            try:
                user_input = input("User > ")
                if not user_input.strip():
                    continue
                if user_input.strip().lower() in ("exit", "quit"):
                    print("Exiting session...")
                    break

                # Create standard platform-format user event
                user_event = {
                    "id": str(uuid.uuid4()),
                    "timestamp": time.time(),
                    "invocationId": f"e-{uuid.uuid4()}",
                    "author": "user",
                    "content": {
                        "role": "user",
                        "parts": [{"text": user_input}]
                    },
                    "actions": {
                        "stateDelta": {},
                        "artifactDelta": {},
                        "requestedAuthConfigs": {},
                        "requestedToolConfirmations": {}
                    },
                    "nodeInfo": {
                        "path": ""
                    }
                }
                flat_events.append(user_event)

                print("Agent > ", end="", flush=True)
                
                new_message = types.Content(
                    role="user", parts=[types.Part.from_text(text=user_input)]
                )
                
                # Start runner
                async for event in runner.run_async(
                    user_id=user_id, session_id=session_id, new_message=new_message
                ):
                    # Store serialized event in the flat events array
                    serialized = serialize_event(event)
                    flat_events.append(serialized)

                    try:
                        # Real-time console prints (handles both camelCase and snake_case safely)
                        author = serialized.get("author")
                        content = serialized.get("content")
                        
                        if content and content.get("parts"):
                            for part in content["parts"]:
                                if part.get("text"):
                                    if author == "root_agent" and content.get("role") == "model":
                                        print(part["text"], end="", flush=True)
                                elif part.get("functionCall") or part.get("function_call"):
                                    fc = part.get("functionCall") or part.get("function_call")
                                    print(f"\n\n[⚙️ Calling Tool: {fc.get('name')}]")
                                    print(f"Args: {json.dumps(fc.get('args'), indent=2)}")
                                    print("Running...")
                                elif part.get("functionResponse") or part.get("function_response"):
                                    fr = part.get("functionResponse") or part.get("function_response")
                                    print(f"\n[📥 Tool Response: {fr.get('name')}]")
                                    print(f"Output: {json.dumps(fr.get('response'), indent=2)}\n")
                                    print("Agent > ", end="", flush=True)
                    except Exception:
                        pass
                print("\n")

            except KeyboardInterrupt:
                print("\nSession interrupted. Exiting...")
                break
    finally:
        # Save trace if any events were recorded
        if flat_events:
            display_name = "Interactive Session"
            if flat_events[0].get("content") and flat_events[0]["content"].get("parts"):
                first_text = flat_events[0]["content"]["parts"][0].get("text", "")
                if first_text:
                    display_name = first_text[:60] + "..." if len(first_text) > 60 else first_text

            trace_data = {
                "id": session_id,
                "appName": "app",
                "userId": user_id,
                "state": {
                    "__session_metadata__": {
                        "displayName": display_name
                    }
                },
                "events": flat_events
            }
            
            trace_dir = REPO_ROOT / "artifacts" / "traces"
            trace_dir.mkdir(parents=True, exist_ok=True)
            
            output_filepath = trace_dir / f"chat_trace_{session_id}.json"
            with open(output_filepath, "w", encoding="utf-8") as out_f:
                json.dump(trace_data, out_f, indent=2)
            
            log_filepath = trace_dir / f"chat_log_{session_id}.jsonl"
            with open(log_filepath, "w", encoding="utf-8") as log_f:
                for event in flat_events:
                    log_f.write(json.dumps(event) + "\n")
            
            print(f"\n[info] Session trace successfully saved to: {output_filepath}")
            print(f"[info] Session log successfully saved to: {log_filepath}")
        else:
            print("\nNo messages exchanged. Trace and log files skipped.")


if __name__ == "__main__":
    asyncio.run(main())
