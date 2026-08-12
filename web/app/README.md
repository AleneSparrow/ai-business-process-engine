# Atelier web app

The real, buildable frontend for the AI Business Process Engine — a Vite + React +
TypeScript app that talks to the actual backend in `src/api` (not a mockup).

## What's really wired up

- **Sign up / log in / log out** — `POST /api/v1/auth/signup`, `POST /api/v1/auth/login`,
  `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`.
- **Self-serve onboarding** — the six-step wizard submits `POST /api/v1/businesses` on
  "Launch engine" and creates a real, schema-valid Business DNA (every service starts on
  `human_review`, nothing auto-books until you change that later).
- **Sidebar business name** — reads the real business via `GET /api/v1/businesses/{id}`.
- **Dashboard (leads & cases)** — real cases for your business via
  `GET /api/v1/businesses/{id}/cases`, mapped from the engine's actual `ProcessState`.
- **Conversation view** — real conversation list and message thread via
  `GET /api/v1/businesses/{id}/conversations` and `GET .../conversations/{conversation_id}`,
  plus the real audit trail (`ProcessEvent` history) for the linked case via
  `GET /api/v1/businesses/{id}/cases/{case_id}`.

All of the above (Milestone 8 slice 2) are staff-authenticated and scoped to your own
`business_id` server-side — a session token for one business cannot read another's data.

## What's still not wired

- **Replying and "mark resolved"** on the Conversation screen are visually present but
  disabled — there's no backend action yet for staff to send a message or resolve a case
  (the engine's `NEEDS_HUMAN` state currently has no defined transition out of it in
  `src/domain/state_machine.py`, which is a real design question, not just missing plumbing).
- **Settings** still renders the original prototype's static `SETTINGS_INITIAL` content —
  editing live Business DNA from the UI hasn't been built.

## Running it

```bash
cd web/app
npm install
cp .env.example .env.local   # point VITE_API_BASE at your running API if not localhost:8000
npm run dev
```

In another terminal, run the actual API it talks to. **The API must allow this app's
origin via CORS or every request will fail with "Couldn't reach the server"** (the
browser blocks the response before your code ever sees it) — make sure your
environment (`.env` at the repo root, or exported shell vars) includes
`http://localhost:5173` in `CORS_ALLOWED_ORIGINS`:

```bash
export CORS_ALLOWED_ORIGINS=http://localhost:8000,http://localhost:5173
uvicorn src.api.app:app --reload --port 8000
```

## Structure

```
src/
  api/client.ts       fetch wrapper + typed calls for every real endpoint
  auth/AuthContext.tsx session state, token persisted in localStorage
  components/          Sidebar, route guards, shared design-system pieces
  pages/                Landing, Signup, Login, Onboarding (all real),
                         Dashboard, Conversation, Settings (preview data)
```
