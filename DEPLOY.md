# Deploying Atelier to production

This is a precise, minimal path to get the real app (not `localhost`) live on
the internet. The backend already has everything it needs (`Dockerfile`,
Alembic migrations run automatically on startup, a `/health` endpoint) — this
guide is mostly account setup and environment variables, most of which only
you can do (creating accounts and entering secrets/payment isn't something
Claude does on your behalf).

Two independent pieces, two different hosts:

- **Backend + Postgres** → [Railway](https://railway.com). Recommended
  because it deploys straight from this repo's `Dockerfile`, gives you a
  Postgres database in the same project with one click, and its Hobby plan
  ($5/mo minimum, no credit card required to start on the trial) is enough
  for an early-stage app — no separate database bill, no 30-day database
  expiry like some competitors' free tiers have.
- **Frontend (the `web/app` React app)** → [Vercel](https://vercel.com) or
  [Cloudflare Pages](https://pages.cloudflare.com). Both have a genuinely
  free, no-time-limit tier for a static site like this one, with a global CDN
  and free custom domain support. Either works; pick whichever you already
  have an account style preference for.

(Render is a fine alternative to Railway if you'd rather use it — same
`Dockerfile`-based deploy — but its free Postgres tier expires after 30 days
and its free web service tier sleeps when idle, which is a bad first
impression on a prospect visiting your own signup funnel. Not recommended for
launch, only mentioned in case you already have a Render account.)

## 1. Backend on Railway

1. Sign up at railway.com (GitHub login is the fastest option) and create a
   **New Project → Deploy from GitHub repo**, pointing at
   `AleneSparrow/ai-business-process-engine`. Railway will detect the
   `Dockerfile` automatically.
2. In the same project, click **+ New → Database → PostgreSQL**. Railway
   provisions it and exposes a `DATABASE_URL`-shaped set of variables
   automatically inside the project.
3. On the backend service, open **Variables** and set:
   - `DATABASE_URL` — reference the Postgres plugin's connection string
     (Railway lets you paste a variable reference like
     `${{Postgres.DATABASE_URL}}`, but the value must be in this app's
     expected driver format: `postgresql+psycopg://...` — if Railway's
     Postgres plugin variable comes as a plain `postgresql://...` URL,
     change the scheme prefix to `postgresql+psycopg://` before saving).
   - `APP_ENV` = `production`
   - `AI_PROVIDER` = `deterministic` to launch without any AI dependency at
     all (qualification and booking are deterministic either way; this only
     turns off AI-assisted intake wording), or `openai` if you want that —
     if `openai`, also set `OPENAI_API_KEY` to your own key **directly in
     Railway's Variables tab**, not by giving it to Claude.
   - `CORS_ALLOWED_ORIGINS` — leave a placeholder for now
     (`https://placeholder.example`); you'll come back and set this to your
     real frontend URL in step 3. The app refuses to start in production
     with a wildcard (`*`) here, and refuses every browser request from an
     origin not explicitly listed — so this has to be exact.
   - `LOG_LEVEL` = `INFO` (optional, this is already the default)
4. Deploy. Railway builds the Docker image, runs `alembic upgrade head`, then
   starts the app (see the `Dockerfile` — this is automatic, nothing to run
   by hand). Once it's live, Railway shows a public URL like
   `https://your-service.up.railway.app` — note it, the frontend needs it.
5. Generate a custom domain later from the service's **Settings → Networking**
   if you want `api.yourdomain.com` instead of the railway.app subdomain.

## 2. Frontend on Vercel (or Cloudflare Pages)

1. Sign up, **Add New Project**, import the same GitHub repo.
2. Set the project root to `web/app` (Vercel/Cloudflare both let you point a
   project at a subdirectory of a monorepo).
3. Build command: `npm run build`. Output directory: `dist`.
4. Environment variable: `VITE_API_BASE` = the Railway backend URL from step
   1.4 above (e.g. `https://your-service.up.railway.app`).
5. Deploy. You'll get a URL like `https://your-app.vercel.app` (or a
   `.pages.dev` one on Cloudflare) — note it too.

## 3. Connect them

Go back to the Railway backend's **Variables** and set the real
`CORS_ALLOWED_ORIGINS` to the frontend URL from step 2.5 (comma-separate if
you also want to allow a custom domain once you set one up, e.g.
`https://your-app.vercel.app,https://app.yourdomain.com`). Save — Railway
redeploys automatically on a variable change.

## 4. Smoke test

Once both are live:
- Visit the frontend URL, sign up a real account, run through onboarding, and
  confirm the dashboard loads — this exercises the full stack (frontend →
  backend → Postgres) in one pass.
- Check the backend URL's `/health` and `/ready` directly in a browser — both
  should return `200`.
- If signup fails with a network/CORS-looking error, the almost-certain cause
  is `CORS_ALLOWED_ORIGINS` not exactly matching the frontend's origin
  (scheme + host, no trailing slash) — check step 3.

## Known limitation carried over from local dev

The in-memory rate limiter (`src/api/rate_limit.py`) is process-local — fine
for a single Railway instance (the default), but if you ever scale the
backend to more than one instance, it needs to be replaced with a shared
limiter first (see the root `README.md`'s "What's still not wired" section).
Not a blocker for launch, just don't turn on multiple replicas without
revisiting this.
