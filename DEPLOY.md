# Deploy `nextstep-agent` to Vercel

One deployment serves **both the Ops Console and the API** from the same URL:

| Path                    | What it serves                          |
|-------------------------|-----------------------------------------|
| `/`                     | Ops Console (static HTML/JS)            |
| `/health`               | JSON — provider, model, status          |
| `/v1/situations`        | POST — run the agent                    |
| `/v1/situations/{sid}`  | GET — replay a stored run               |
| `/v1/situations/{sid}/confirm/{aid}` | POST — approve a confirm-tier action |
| `/v1/ledger`            | GET — recent ledger rows                |
| `/v1/me`                | DELETE — GDPR purge                     |

So a reviewer can **test the frontend** by opening the URL, or **test the backend independently** with curl / Postman.

---

## One-time setup

```bash
# install Vercel CLI (needs Node.js)
npm i -g vercel

# from THIS folder:
cd C:\Users\hamza\OneDrive\Desktop\Hazhteq\nextstep-agent
vercel login          # sign in with the browser
```

---

## Deploy

```bash
vercel --prod
```

Vercel will ask ~4 questions:
1. **Set up and deploy?** → `y`
2. **Which scope?** → your account
3. **Link to existing project?** → `n` (first time)
4. **Project name?** → `nextstep-agent-<yourname>` (or accept default)
5. **Directory?** → `.` (accept default)
6. **Override settings?** → `n`

After ~60 seconds it prints a production URL like `https://nextstep-agent-hamza.vercel.app`.

---

## Set the Gemini API key

The backend needs `GEMINI_API_KEY` to call the real LLM. Without it, the deployed agent falls back to the deterministic mock (which still works for the 7 shared scenarios).

**Option A — via CLI:**
```bash
vercel env add GEMINI_API_KEY production
# paste your key when prompted
vercel --prod       # redeploy so the env var takes effect
```

**Option B — via Vercel dashboard:**
1. Go to https://vercel.com/dashboard → your project
2. Settings → Environment Variables
3. Add `GEMINI_API_KEY` = `<your-key>`, scope = Production
4. Deployments tab → click the latest → **Redeploy**

---

## Verify it's live

```bash
# health check — should show provider: gemini if the key is set
curl https://your-deployment.vercel.app/health

# submit a situation
curl -X POST https://your-deployment.vercel.app/v1/situations \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test-1" \
  -d "{\"text\":\"laptop dead and viva at 10am tomorrow\"}"

# open the console
start https://your-deployment.vercel.app/
```

---

## Serverless caveats (documented honestly)

- **Ledger writes go to `/tmp/nextstep_ledger.jsonl`** on Vercel (only writable path). This does NOT persist across cold starts. The auto-switch is handled by `nextstep_agent/api.py`.
- **Session store** (`_runs` dict — used by `/confirm`) is in-memory per instance. If a cold start hits between `POST /v1/situations` and `POST /v1/confirm/{aid}`, the confirm returns 404. In production this would be Redis; documented as a roadmap item.
- **Idempotency cache** (`_idem` dict) is also in-memory. Duplicate POSTs within a warm invocation dedupe; across cold starts they don't. Not a real problem for the demo flow.
- **Cold start ~1–2s**, warm response ~50ms + Gemini latency.

---

## Redeploying after code changes

```bash
git commit -am "…"
vercel --prod
```

Vercel picks up `vercel.json`, `requirements.txt`, `api/index.py`, `nextstep_agent/`, and `web/` automatically.
