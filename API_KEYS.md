# API Keys — How to Configure Each Research Provider

The app auto-detects which providers are configured. Providers without a key
appear disabled in the "Research engine" tabs with an amber dot.

| Provider | Environment variable | Where to get a key |
|---|---|---|
| Gemini Deep Research | `GOOGLE_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) |
| OpenAI Deep Research | `OPENAI_API_KEY` | [OpenAI Platform → API keys](https://platform.openai.com/api-keys) |
| Claude Research | `ANTHROPIC_API_KEY` | [Anthropic Console → API keys](https://console.anthropic.com/settings/keys) |

## 1. Local development

Add the keys to the `.env` file in the project root (never commit this file):

```env
GOOGLE_API_KEY=your_gemini_key
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

Restart the backend (`uv run uvicorn backend.main:app --port 8000`) and the
provider tabs will activate automatically.

## 2. Cloud Run

### Option A — plain environment variables (quick)

```bash
gcloud run services update SERVICE_NAME --region REGION \
  --update-env-vars OPENAI_API_KEY=sk-...,ANTHROPIC_API_KEY=sk-ant-...
```

### Option B — Secret Manager (recommended)

```bash
# Store each key once
echo -n "sk-..." | gcloud secrets create openai-api-key --data-file=-
echo -n "sk-ant-..." | gcloud secrets create anthropic-api-key --data-file=-

# Allow the Cloud Run service account to read them
gcloud secrets add-iam-policy-binding openai-api-key \
  --member serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com \
  --role roles/secretmanager.secretAccessor

# Wire them into the service
gcloud run services update SERVICE_NAME --region REGION \
  --update-secrets OPENAI_API_KEY=openai-api-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest
```

## 3. Provider-specific notes

### Gemini (`GOOGLE_API_KEY`)
- Deep Research agents (`deep-research-preview-04-2026`,
  `deep-research-max-preview-04-2026`, and the legacy
  `deep-research-pro-preview-12-2025`) are available **on paid tiers** of the
  Gemini API.
- **Important (June 2026):** the key currently in `.env` works for extraction
  (Gemini Flash) but the Interactions API returns
  `403 — Your project has been denied access` for ALL Deep Research agents.
  This also affects the old v2 app, which used the same agent. To fix it,
  create an API key in a Google Cloud project with **billing enabled / paid
  Gemini API tier** (AI Studio → API keys → create key in a paid project), or
  contact Google support about the existing project.

### OpenAI (`OPENAI_API_KEY`)
- Uses the Responses API in background mode. Models: `o4-mini-deep-research`
  (fast, $2/M input + $8/M output) and `o3-deep-research` ($10/M input +
  $40/M output). Web search calls are billed additionally ($10/1k calls).
- The key's organization must be verified to use deep research models
  (platform.openai.com → Settings → Organization → Verification).

### Claude (`ANTHROPIC_API_KEY`)
- Anthropic has no dedicated deep-research API. The app runs Claude
  (Sonnet 4.6 fast / Opus 4.8 max) with the native **web search tool**, which
  performs up to 25 progressive searches with citations.
- Web search pricing: $10 per 1,000 searches plus standard token costs.
