# Vercel Deployment Guide — Forex Signal Scanner Web App

This guide walks you through deploying the FastAPI web app to Vercel, step by step.
The repo is already configured for Vercel:

- [`vercel.json`](vercel.json) — catch-all rewrite to `api/index.py` + bundles `webapp/static/**` into the serverless function
- [`api/index.py`](api/index.py) — ASGI entry point (Vercel auto-detects the `app` object)
- [`requirements.txt`](requirements.txt) — includes `fastapi` and `uvicorn`

---

## Prerequisites (5 minutes)

1. A **Vercel account** — free at <https://vercel.com/signup>. Sign in with GitHub so it can access your repo.
2. **Node.js 18+** installed (needed for the Vercel CLI). Check with:
   ```bash
   node --version
   ```
   If missing, install from <https://nodejs.org> (LTS version).
3. Your code already pushed to GitHub: `github.com/Saifullahgg/forex-scanner` (done).

> No environment variables / API keys are needed. The app fetches public Yahoo Finance data directly.

---

## Option A — Deploy with the Vercel CLI (recommended, full control)

### Step 1: Install the Vercel CLI

Open a terminal (Command Prompt / PowerShell / VS Code terminal) and run:

```bash
npm install -g vercel
```

Verify:

```bash
vercel --version
```

### Step 2: Go into the project folder

```bash
cd C:\Users\DELL\Desktop\forex-scanner
```

### Step 3: Log in

```bash
vercel login
```

- It will show a URL and ask you to authenticate in your browser (or open it automatically).
- Sign in with the same GitHub account that owns the repo.
- Back in the terminal, you'll see a success message.

### Step 4: Link the project (first time only)

```bash
vercel link
```

Answer the prompts:

| Prompt | Answer |
|---|---|
| Set up `forex-scanner`? | `Y` |
| Which scope should contain your project? | your account (use arrow keys, Enter) |
| Link to existing project? | `N` (create a new one) |
| What's your project's name? | press Enter (defaults to `forex-scanner`) |
| In which directory is your code located? | `.` (the current folder — press Enter) |

This creates a local `.vercel/` folder linking your machine to the Vercel project.

### Step 5: Preview deployment (optional but recommended)

```bash
vercel
```

This deploys to a **preview** URL (not production), e.g. `https://forex-scanner-xxxx.vercel.app`.
Wait for the build to finish (first build can take 2–5 minutes because pandas/numpy/yfinance are large).
Test the preview URL.

### Step 6: Production deployment

```bash
vercel --prod
```

This deploys to **production**. Your project's URL will be printed at the end.
Note: if the bare name is already taken on Vercel, it gets a suffix — this project
deployed as `https://forex-scanner-eta.vercel.app` (the plain `forex-scanner.vercel.app`
belongs to a different, unrelated app). Always use the exact URL Vercel prints.

### Step 7: Verify it works

- Open the production URL in your browser → you should see the dark trading dashboard.
- Check the API health endpoint:
  ```bash
  curl https://forex-scanner-eta.vercel.app/api/health
  ```
  Expected: JSON with `"status": "ok"` and the 8 strategy names.
- Test a scan:
  ```
  https://forex-scanner-eta.vercel.app/api/scan?pairs=EURUSD&interval=1h&period=1mo
  ```
- Open a chart:
  ```
  https://forex-scanner-eta.vercel.app/api/pair/EURUSD/chart?interval=1h&period=1mo
  ```

---

## Option B — Deploy from the Vercel Dashboard (no CLI, auto-deploy on push)

### Step 1: Import the repo

1. Go to <https://vercel.com/new> (logged in).
2. Click **Add New… → Project**.
3. In "Import Git Repository", find and select **`Saifullahgg/forex-scanner`**.
   - If it's not listed, click **Adjust GitHub App Permissions** and grant access to the repo.

### Step 2: Configure (leave defaults)

- **Framework Preset:** leave as **Other** (there is no npm build step).
- **Build Command:** leave empty.
- **Output Directory:** leave empty.
- **Install Command:** leave empty.
- **Root Directory:** leave as the repo root (vercel.json is at the root).

### Step 3: Deploy

Click **Deploy**. Wait for the build (2–5 minutes first time).

### Step 4: Done

Vercel gives you a production URL. Every future `git push` to `main` auto-redeploys.

---

## How the Vercel config works (why it won't break)

- Vercel sees `api/index.py` exporting `app` (a FastAPI/ASGI object) and auto-detects the Python ASGI app — no special handler needed.
- [`vercel.json`](vercel.json) rewrites **every** request (`/(.*)`) to `api/index.py`, so the FastAPI routes `/api/health`, `/api/scan`, `/api/pair/{pair}/chart`, `/static/*` and `/` all work unchanged.
- `"includeFiles": "webapp/static/**"` bundles the static dashboard **into** the serverless function, so the frontend is served same-origin — no CORS configuration required.
- Vercel installs dependencies from [`requirements.txt`](requirements.txt) (fastapi + uvicorn already added).
- The 300-second TTL cache in `webapp/cache.py` protects against Yahoo rate limits.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Build fails on `maxDuration` (Hobby plan) | In `vercel.json`, change `"maxDuration": 60` to `"maxDuration": 10` or remove the `functions` block, then redeploy. |
| `ModuleNotFoundError: webapp` | Make sure you ran `vercel` from inside the `forex-scanner` folder (the repo root), not the Desktop. |
| Scan takes >10s and times out (Hobby plan) | Reduce the number of pairs (scan 1–5 pairs at a time). Free-plan functions have a max duration of 10s by default; Pro allows 60s+. |
| Slow first load / cold start | Normal — pandas/numpy/yfinance are large. Subsequent requests are faster due to the TTL cache. |
| Chart shows no data | Try a smaller `period` (e.g. `1mo`) or a different `interval` (`1h`, `4h`). Some exotic pairs have sparse Yahoo data. |
| Project got created with the wrong name (e.g. `y`) during `vercel link` | Delete it in the dashboard (Project → Settings → Danger Zone → Delete Project) or run `vercel project rm <wrong-name>`. Then re-run `vercel link`, choose **Create a new project**, and type the name exactly: `forex-scanner`. |
| `Failed to connect <repo> to project` during `vercel link` | The Vercel GitHub App has no access to that repo yet. Two fixes: (1) quickest — answer **No** to the "Connect this Git repository?" question and deploy from local files with `vercel --prod`; (2) proper — grant access: GitHub → Settings → Applications → Vercel → Configure → Repository access → grant `Saifullahgg/forex-scanner`, then re-run `vercel link` and answer **Yes**. |
| `vercel link` shows `.env.local` / `.vercel` added to `.gitignore` | Expected — Vercel auto-ignores its local files. Commit the `.gitignore` change; `.env.local` and `.vercel/` stay local and are never pushed. |

---

## Updating after changes

- **Dashboard (GitHub) method:** push to `main` → Vercel auto-redeploys.
- **CLI method:** `cd C:\Users\DELL\Desktop\forex-scanner` then `vercel --prod`.

## Optional: Custom domain

Vercel dashboard → your project → **Settings → Domains** → add your domain and follow the DNS instructions.
