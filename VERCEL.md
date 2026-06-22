# Deploy AdSathi to Vercel

AdSathi is Vercel-ready: `api/index.py` is a serverless (WSGI) entry that wraps the whole
app, and `vercel.json` routes every request to it and bundles `backend/` + `frontend/`.

> Honest note: I can't run the deploy for you — it needs your Vercel login. Below is the
> exact click-path. It takes ~5 minutes. If you want, I can also drive your browser through
> it with the Claude-in-Chrome tools — just say so.

## A. One-time

1. Push this folder to a GitHub repo (or use the Vercel CLI, below).
2. Create a free account at vercel.com.

## B. Deploy (dashboard)

1. Vercel dashboard → **Add New → Project** → import your repo.
2. Framework preset: **Other** (the included `vercel.json` handles the rest). Leave build
   settings default. Deploy.
3. After the first deploy you'll get a URL like `https://adsathi.vercel.app`. It already
   works in **demo mode**.

## C. Deploy (CLI alternative)

```bash
npm i -g vercel
cd adgen-bd
vercel            # follow prompts -> preview URL
vercel --prod     # production URL
```

## D. Environment variables (Vercel → Project → Settings → Environment Variables)

For a **demo** deploy, set just:

| Key | Value |
|-----|-------|
| `DRY_RUN` | `true` |
| `DB_PATH` | `/tmp/adsathi.db` |
| `SECRET_KEY` | any long random string |
| `BASE_URL` | your `https://...vercel.app` URL |

> ⚠ Serverless filesystems are ephemeral — with `DB_PATH=/tmp/...`, accounts/credits reset
> on cold starts. Fine for demos. For **real users you must use Postgres** (next).

For a **persistent / production** deploy, also set:

| Key | Value |
|-----|-------|
| `DATABASE_URL` | a Postgres URL (Vercel Postgres or Neon — both have free tiers) |
| `ANTHROPIC_API_KEY` | for real captions |
| `IMAGE_PROVIDER` / `IMAGE_API_KEY` | `openai` + your key for real images |
| `META_APP_ID` / `META_APP_SECRET` | from your Meta app (see DEPLOY.md step 3) |
| `META_OAUTH_REDIRECT` | `https://<your-vercel-url>/connect/facebook/callback` |
| `META_AGENCY_TOKEN` / `META_AGENCY_AD_ACCOUNT_ID` / `META_AGENCY_PAGE_ID` | agency fallback |
| `SSLCZ_STORE_ID` / `SSLCZ_STORE_PASS` | payments; set `SSLCZ_SANDBOX=false` when live |
| `DRY_RUN` | `false` |

The app auto-detects Postgres when `DATABASE_URL` starts with `postgres`; `requirements.txt`
already includes `psycopg`, so no code changes are needed.

## E. Add Postgres in 2 clicks

Vercel dashboard → **Storage → Create Database → Postgres** → it injects `DATABASE_URL`
into your project automatically. Redeploy. Tables are created on first request.

## F. After Meta approval

Add the Meta env vars above, set `DRY_RUN=false`, redeploy. Update your Meta app's OAuth
redirect URI to the Vercel callback URL. See **DEPLOY.md** for the full Meta App Review +
Bangladesh compliance checklist.

---

### Is Vercel the right host?

Vercel is great for the demo and works for production with Postgres. But because this is a
stateful Python app, a container host (Render / Railway / Fly / a VPS) using the included
**Dockerfile** is often simpler for production — persistent disk, no cold starts, one
command (`docker compose up -d --build`). Use whichever you prefer; the same codebase runs
on both.
