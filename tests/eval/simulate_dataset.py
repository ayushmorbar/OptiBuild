# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import asyncio
import json
import os
import sys

# Ensure app directory is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agent import root_agent
from google.adk.runners import InMemoryRunner
from google.genai import Client
from google.genai import types

def load_agents_block():
    """Loads the agents topology block from the latest trace file to ensure rubric compatibility."""
    trace_dir = "/home/kejia/gauss/artifacts/traces"
    if os.path.exists(trace_dir):
        for filename in sorted(os.listdir(trace_dir), reverse=True):
            if filename.startswith("traces_") and filename.endswith(".json"):
                filepath = os.path.join(trace_dir, filename)
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                        if "eval_cases" in data and len(data["eval_cases"]) > 0:
                            case = data["eval_cases"][0]
                            if "agent_data" in case and "agents" in case["agent_data"]:
                                return case["agent_data"]["agents"]
                except Exception:
                    continue
    return {}

def generate_user_response(client, history, original_goal, simulator_model):
    """Uses a Gemini model to generate a natural follow-up response acting as the user."""
    prompt = f"""You are a simulated user participating in a multi-turn conversation with a custom PC building assistant.
Your original goal was: "{original_goal}"

Here is the conversation history so far (alternating User and Assistant):
{history}

Please write your next response as the user.
Follow these rules:
1. Stay in character as a consumer who wants to build a PC according to the original goal.
2. If the assistant asked clarifying questions, answer them naturally and logically.
3. If the assistant provided a PC configuration recommendation:
   - Ask a relevant follow-up question (e.g., "Can we use a 1TB SSD instead of 2TB?", "Could we use a cheaper case to save money?", "Is this power supply sufficient for future upgrades?", "Can we use an AMD processor instead?", "Is the cooler quiet?").
   - Do NOT just agree and say thank you immediately; always ask at least one follow-up question or adjustment request.
4. Keep your response brief, natural, and realistic (1-3 sentences).
5. Output ONLY the raw user text response. Do not add labels, headers, quotes, or markdown."""

    try:
        response = client.models.generate_content(
            model=simulator_model,
            contents=prompt,
        )
        return response.text.strip().strip('"').strip("'")
    except Exception as e:
        print(f"Error calling simulator model: {e}")
        return "Okay, what parts are included in that configuration?"

def clean_event(event_dict):
    """Filters out all extra fields not allowed by the strict EvaluationDataset schema."""
    cleaned = {}
    if event_dict.get("author") is not None:
        cleaned["author"] = event_dict["author"]
    
    if event_dict.get("content") is not None:
        content = event_dict["content"]
        cleaned_content = {}
        if content.get("role") is not None:
            cleaned_content["role"] = content["role"]
        if content.get("parts") is not None:
            cleaned_parts = []
            for part in content["parts"]:
                cleaned_part = {}
                if part.get("text") is not None:
                    cleaned_part["text"] = part["text"]
                elif part.get("function_call") is not None:
                    fc = part["function_call"]
                    cleaned_fc = {}
                    if fc.get("name") is not None:
                        cleaned_fc["name"] = fc["name"]
                    if fc.get("args") is not None:
                        cleaned_fc["args"] = fc["args"]
                    if fc.get("id") is not None:
                        cleaned_fc["id"] = fc["id"]
                    cleaned_part["function_call"] = cleaned_fc
                elif part.get("function_response") is not None:
                    fr = part["function_response"]
                    cleaned_fr = {}
                    if fr.get("name") is not None:
                        cleaned_fr["name"] = fr["name"]
                    if fr.get("response") is not None:
                        cleaned_fr["response"] = fr["response"]
                    if fr.get("id") is not None:
                        cleaned_fr["id"] = fr["id"]
                    cleaned_part["function_response"] = cleaned_fr
                cleaned_parts.append(cleaned_part)
            cleaned_content["parts"] = cleaned_parts
        cleaned["content"] = cleaned_content
    return cleaned

def serialize_event(event):
    """Utility to turn an ADK Event object into a JSON-serializable dictionary."""
    raw_dict = json.loads(event.model_dump_json(exclude_none=True))
    return clean_event(raw_dict)

async def simulate_case(client, case, max_turns, simulator_model):
    """Simulates a single case by running user simulation over max_turns."""
    eval_case_id = case["eval_case_id"]
    initial_prompt = case["prompt"]["parts"][0]["text"]
    print(f"\n--- Simulating case: {eval_case_id} ---")
    print(f"Goal: {initial_prompt}")

    runner = InMemoryRunner(agent=root_agent, app_name="app")
    runner.auto_create_session = True
    uid = f"user_{eval_case_id}"
    sid = f"session_{eval_case_id}"

    turns = []
    final_agent_text = ""

    # Turn 0: Send the initial prompt
    print("Turn 0 (User Request)...")
    new_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=initial_prompt)]
    )
    turn_events = []
    async for event in runner.run_async(user_id=uid, session_id=sid, new_message=new_message):
        turn_events.append(serialize_event(event))

    # Extract agent response text for the simulator
    agent_text_parts = []
    for ev in turn_events:
        if ev.get("author") == "root_agent" and ev.get("content"):
            for part in ev["content"].get("parts", []):
                if part.get("text") is not None:
                    agent_text_parts.append(part["text"])
    turn_agent_text = "".join(agent_text_parts)
    print(f"Agent response: {turn_agent_text[:120]}...")

    turns.append({
        "turn_index": 0,
        "turn_id": "turn_0",
        "events": turn_events
    })
    final_agent_text = turn_agent_text

    # Multi-turn follow-ups
    for t_idx in range(1, max_turns):
        # Build conversation history
        history_str = ""
        for t in turns:
            u_text = ""
            a_text = ""
            for ev in t["events"]:
                # User event
                if ev.get("content") and ev["content"].get("role") == "user":
                    for part in ev["content"].get("parts", []):
                        if part.get("text") is not None:
                            u_text += part["text"]
                # Agent event (not tool)
                elif ev.get("author") == "root_agent" and ev.get("content") and ev["content"].get("role") == "model":
                    for part in ev["content"].get("parts", []):
                        if part.get("text") is not None:
                            a_text += part["text"]
            if u_text:
                history_str += f"User: {u_text}\n"
            if a_text:
                history_str += f"Assistant: {a_text}\n"

        print(f"Generating follow-up for Turn {t_idx}...")
        simulated_user_input = generate_user_response(client, history_str, initial_prompt, simulator_model)
        print(f"Simulated User: {simulated_user_input}")

        print(f"Turn {t_idx} (Follow-up execution)...")
        followup_message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=simulated_user_input)]
        )
        f_events = []
        async for event in runner.run_async(user_id=uid, session_id=sid, new_message=followup_message):
            f_events.append(serialize_event(event))

        agent_text_parts = []
        for ev in f_events:
            if ev.get("author") == "root_agent" and ev.get("content"):
                for part in ev["content"].get("parts", []):
                    if part.get("text") is not None:
                        agent_text_parts.append(part["text"])
        turn_agent_text = "".join(agent_text_parts)
        print(f"Agent response: {turn_agent_text[:120]}...")

        turns.append({
            "turn_index": t_idx,
            "turn_id": f"turn_{t_idx}",
            "events": f_events
        })
        final_agent_text = turn_agent_text

    # Build the trace structure for this case
    case_trace = {
        "prompt": {
            "parts": [{"text": initial_prompt}],
            "role": "user"
        },
        "responses": [
            {
                "response": {
                    "parts": [{"text": final_agent_text}],
                    "role": "model"
                }
            }
        ],
        "eval_case_id": eval_case_id,
        "agent_data": {
            "agents": load_agents_block(),
            "turns": turns
        }
    }
    return case_trace

async def main():
    parser = argparse.ArgumentParser(description="Simulate multi-turn user follow-ups on the evaluation dataset.")
    parser.add_argument("--max-turns", type=int, default=2, help="Max turns to simulate (default 2)")
    parser.add_argument("--simulator-model", type=str, default="gemini-2.5-flash", help="Gemini model for simulated user (default gemini-2.5-flash)")
    parser.add_argument("--dataset", type=str, default="tests/eval/datasets/basic-dataset.json", help="Path to input dataset")
    parser.add_argument("--output", type=str, default="artifacts/traces/traces_simulated_multiturn.json", help="Path to save trace output")
    args = parser.parse_args()

    print(f"Simulator settings:")
    print(f"- Max Turns: {args.max_turns}")
    print(f"- Simulator Model: {args.simulator_model}")
    print(f"- Dataset: {args.dataset}")
    print(f"- Output: {args.output}")

    with open(args.dataset, "r") as f:
        dataset = json.load(f)

    client = Client()
    simulated_cases = []

    for case in dataset["eval_cases"]:
        try:
            case_trace = await simulate_case(client, case, args.max_turns, args.simulator_model)
            simulated_cases.append(case_trace)
        except Exception as e:
            print(f"Error simulating case {case.get('eval_case_id')}: {e}")

    # Save all traces
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump({"eval_cases": simulated_cases}, f, indent=2)
    print(f"\nAll traces successfully saved to {args.output}!")

if __name__ == "__main__":
    asyncio.run(main())
