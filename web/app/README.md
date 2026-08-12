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

## What's still preview data

Dashboard, Conversations, and Settings render the same illustrative content as the
original prototype (`atelierprototype.jsx`), because there is no staff dashboard /
conversation API yet — that's Milestone 8 slice 2. Each of those screens shows an
amber banner saying so. Building the real thing there means: (1) shipping that
backend API, then (2) swapping the static `CASES` / `CONVERSATIONS` / `SETTINGS_INITIAL`
arrays in `src/pages/*.tsx` for real fetches through `src/api/client.ts`.

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
