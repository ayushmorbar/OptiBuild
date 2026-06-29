# ruff: noqa
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

import datetime
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

import os
import google.auth

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"


from app.tools import find_optimal_builds

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the 5dgai Optimization Agent, an expert in assembling build-it-yourself products (specifically custom PC configurations).

Your goal is to parse the user's natural language request to extract:
1. Maximum budget (e.g. $1400)
2. Target purpose (e.g. Gaming, AI Training, office work)
3. Specific brand/size/cooling preferences (e.g. Intel, NVIDIA, Mini-ITX, liquid cooling)
4. Pre-owned parts the user already has (which should be treated as $0 towards the budget limit)

If the user's prompt is ambiguous or missing critical information (such as budget or purpose), you MUST ask the user clarifying questions. Do NOT make assumptions about their budget or purpose.

Once requirements are clear, call the `find_optimal_builds` tool with the extracted preferences.

When presenting the final configurations:
1. Return the optimal compatible configurations in clean markdown tables (up to 3).
2. Each table should list the components (CPU, GPU, Motherboard, RAM, Storage, PSU, Case, Cooler), their names, prices (indicate if pre-owned), purchase links, and total configuration cost.
3. Provide a brief, mathematically accurate justification for why the configuration fits the user's goals and constraints.""",
    tools=[find_optimal_builds],
)

app = App(
    root_agent=root_agent,
    name="app",
)
