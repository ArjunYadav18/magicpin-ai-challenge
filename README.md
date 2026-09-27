# Vera Agent for magicpin AI Challenge

This is a complete, robust FastAPI implementation of the Vera Merchant Assistant for the magicpin VERA AI Challenge.

## Architecture

The bot uses a deterministic core with an LLM attached only for natural language phrasing and conversation handling. This ensures 100% compliance with business rules (versioning, idempotency, consent, suppression, expiry) while providing engaging, context-aware messages.

- **`app/main.py`** & **`app/router.py`**: FastAPI entrypoint and HTTP contract implementation.
- **`app/store.py`**: In-memory, thread-safe Context Store. Handles idempotent versioning and state persistence (conversations, suppression, opt-outs).
- **`app/decision.py`**: Deterministic Decision Engine. Scores and ranks triggers based on relevance, urgency, recency, actionability, and conversation fit. Enforces consent checks.
- **`app/composer.py`** & **`app/prompts.py`**: LLM integration. Builds context-rich prompts ensuring no hallucination by using ONLY the facts present in the payload. Handles graceful deterministic fallback if the LLM fails or times out.
- **`app/validator.py`**: Post-generation fact-grounding validator. Checks for URLs, hallucinations of numbers, and category taboos.
- **`app/conversation.py`**: Intent classifier (Stop, Auto-reply, Accept, Decline).
- **`app/suppression.py`**: Enforces deduplication of suppression keys and trigger expiry.

## How to run locally

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Linux/Mac
   source .venv/bin/activate
   
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and set your API keys:
   ```bash
   cp .env.example .env
   # Edit .env and set LLM_PROVIDER (e.g. openai, gemini) and LLM_API_KEY
   ```

3. Run the FastAPI server:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
   ```

4. Run the Judge Simulator (in a separate terminal):
   ```bash
   python judge_simulator.py
   ```

## Design Choices & Constraints Addressed

- **No Hallucinations**: The `FactValidator` parses numbers from the LLM output and checks if they exist in the allowed set of numbers extracted from the current context. If they don't, the message is dropped.
- **URL Penalty Avoidance**: Strict checks in the validator block any URLs.
- **Idempotency & Versioning**: `ContextStore.put` correctly handles version clashes (409 for stale/same versions, atomic replace for newer versions).
- **Auto-reply Hell**: Tracks merchant replies. 1st auto-reply = flag to owner. 2nd = wait. 3rd = end.
- **Action Mode**: On intent="accept", it immediately switches to concrete action mode without asking further qualifying questions.
- **Deterministic Baseline**: If LLM_PROVIDER is unset or fails, it falls back to hardcoded safe templates so the server never crashes.

## Deployment

This app is stateless except for the in-memory store. For production deployment, you would replace pp.store.ContextStore with a distributed key-value store (e.g., Redis). 

To deploy via Docker:
\\ash
docker build -t vera-bot .
docker run -p 8080:8080 --env-file .env vera-bot
\