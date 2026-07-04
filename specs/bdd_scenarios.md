# BDD Scenarios: 5dgai - Optimisation Agent

This document defines behavior-driven development (BDD) scenarios for the Optimization Agent.

## Scenario 1: Standard PC Build Request within Reasonable Budget
* **Given** a component database containing CPUs, GPUs, Motherboards, RAM, Storage, PSUs, and Cases with compatibility rules and prices.
* **When** a user requests a PC build with:
  * **Purpose**: "Gaming (Cyberpunk 2077, Rust) and AI training"
  * **Max budget**: "$1400"
* **Then** the agent must:
  * Parse the requirements (needs a powerful GPU for Cyberpunk/AI, decent CPU, 16GB+ RAM, compatible motherboard, sufficient PSU).
  * Run the optimization/solver to find compatible configurations under $1400.
  * Return at least 1 (and up to 3) compatible configurations.
  * Print each component's name, price, link, and total build cost.
  * Ensure the total build cost is <= $1400.
  * Verify motherboard socket matches CPU socket, and RAM is compatible.

## Scenario 2: Budget Too Low
* **Given** a component database where the minimum cost of any fully compatible PC is $600.
* **When** a user requests a PC build with:
  * **Max budget**: "$400"
* **Then** the agent must:
  * Recognize that no compatible configuration can be constructed within the $400 budget limit.
  * Inform the user that a valid configuration cannot be built for that budget, explaining the minimum required budget for a basic build.
  * Suggest a minimal valid build with its actual price.

## Scenario 3: Request with Brand Preference
* **Given** a component database containing both AMD and Intel CPUs, and NVIDIA and AMD GPUs.
* **When** a user requests a PC build with:
  * **Purpose**: "Gaming"
  * **Max budget**: "$1500"
  * **Preference**: "Intel CPU and NVIDIA GPU"
* **Then** the agent must:
  * Filter/prioritize components to include only Intel CPUs and NVIDIA GPUs.
  * Return configurations matching these brand constraints.
  * Verify full compatibility of all components in the build.
  * Ensure total cost is <= $1500.

## Scenario 4: Ambiguous Request / Missing Information
* **Given** the Optimization Agent is ready to receive input.
* **When** a user requests: "Build me a computer for video editing" (omitting budget and other constraints).
* **Then** the agent must:
  * Pause/respond to ask the user for their maximum budget and any specific preferences they have.
  * Wait for user clarification before attempting to run the optimization.
