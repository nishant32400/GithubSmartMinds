# GitHub Talent Hunt (GITRadar)

An LLM-assisted talent-hunt service that reads a job description, plans a focused
GitHub search, enriches candidate profiles, and ranks developers by a blend of a
deterministic heuristic and large-language-model evaluation — always degrading
gracefully to the heuristic when no model is configured.

## Features

- **Natural-language search** — turns a job description into a focused GitHub
  user-search query and a canonical skill list.
- **Deep ranking** — blends keyword overlap with log-scaled reach (followers,
  repos, stars, forks) and refines the shortlist with LLM evaluation.
- **GitHub achievements** — scrapes profile badges (Pull Shark, Starstruck,
  Arctic Code Vault, …) that the API does not expose, shown per candidate.
- **Provider-agnostic LLM** — OpenAI, Groq (OpenAI-compatible, serves
  `gpt-oss-20b`), or AWS Bedrock. Set `LLM_PROVIDER=none` to run heuristic-only.
- **CSV export** — download the on-screen shortlist (names, scores, skills,
  stars, achievements, …); cells are sanitized against formula injection.
- **Search history** — a per-browser sidebar of recent searches, each re-runnable.
- **Web UI + JSON API** — server-rendered pages and a `/api/search` endpoint.
- **Hardened for public exposure** — security headers, strict CSP, per-IP rate
  limiting, and sanitized error messages.

## What's included

- `backend/` — Flask app, agent pipeline, ranker, LLM client, GitHub scraper
- `frontend/` — server-rendered search and results pages (no client-side JS)
- `docs/` — generated technical design document (see below)
- `.env.example` — example environment settings

## Setup

1. Copy the example env file and fill it in:

   ```bash
   cp .env.example backend/.env
   ```

   Minimum useful values:
   - `GITHUB_TOKEN=` — a GitHub token (raises the API limit from 60/hr to 5000/hr)
   - `SECRET_KEY=` — a long random string (`python3 -c "import secrets; print(secrets.token_hex(32))"`)
   - `LLM_PROVIDER=` — `none`, `openai`, `groq`, or `bedrock`

2. Install dependencies:

   ```bash
   cd backend
   python3 -m pip install -r requirements.txt
   ```

3. Run the development server:

   ```bash
   python3 app.py
   ```

4. Open <http://127.0.0.1:8000>.

For production, use gunicorn: `gunicorn -c gunicorn.conf.py wsgi:app`.

## Configuration

All settings are environment-driven (see `.env.example`). Highlights:

| Variable | Purpose |
| --- | --- |
| `GITHUB_TOKEN` | GitHub API auth (higher rate limit). |
| `LLM_PROVIDER` | `none` \| `openai` \| `groq` \| `bedrock`. |
| `GROQ_API_KEY` / `GROQ_MODEL` | Groq key and model (default `openai/gpt-oss-20b`). |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | OpenAI (or any compatible endpoint via `OPENAI_BASE_URL`). |
| `LLM_EVAL_TOP_K` | How many top candidates to deeply evaluate. |
| `LLM_MAX_CONCURRENCY` | Parallel LLM eval calls. |
| `LLM_MAX_RETRIES` | Retries honoring the provider's `Retry-After`. |
| `LLM_EVAL_MAX_TOKENS` | Output-token ceiling per evaluation. |
| `FETCH_ACHIEVEMENTS` | Toggle achievement-badge scraping. |
| `MAX_SEARCH_SIZE` / `MAX_RESULTS` | Hard request ceilings for the public endpoint. |
| `RATELIMIT_*` | Per-IP rate limits (Flask-Limiter). |

### Using Groq (free tier)

Groq's free tier is limited to **8000 tokens/minute**, so a burst of parallel
evaluations can hit HTTP 429. The defaults are tuned for it — keep
`LLM_MAX_CONCURRENCY=1`, a modest `LLM_EVAL_TOP_K` (~6), and
`LLM_MAX_RETRIES=5`. On a paid tier, raise concurrency and `LLM_EVAL_TOP_K`
for faster, deeper ranking.

## How to use

### Web UI

1. Enter job requirements or keywords.
2. Optionally add a location and adjust result/scan size.
3. Click **Search GitHub**.
4. Review the ranked shortlist, open profiles, **Download CSV**, or reopen a past
   search from the **History** sidebar.

### JSON API

```bash
curl -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Python backend Flask Docker", "location": "Berlin", "max_results": 10}'
```

Returns the plan, whether the LLM was used, and the ranked `results` array.

## How ranking works

1. **Plan** — job description → focused GitHub query + skills.
2. **Search** — GitHub user-search API → candidate usernames.
3. **Enrich** — parallel fetch of profiles and repositories.
4. **Rank** — heuristic score over the full pool (skills + log-scaled reach).
5. **Evaluate** — the LLM scores the shortlist; achievements fold into the raw
   heuristic before normalization, then `final = 0.75·LLM_fit + 0.25·heuristic`
   (0–100). Every stage falls back to the heuristic if the LLM is unavailable.

## Technical document

A full design document — with data-flow diagrams and a Q&A of engineering
problems and solutions — can be (re)generated as a PDF:

```bash
cd backend
python3 generate_technical_document.py
# -> docs/GitHub_Talent_Hunt_Technical_Document.pdf
```

## Security notes

- Never commit `.env` (it is git-ignored). Rotate any key that has been shared.
- A strict `script-src 'none'` CSP means the UI ships **no client-side
  JavaScript** — CSV export and history are fully server-side.
- Search history lives in the signed Flask session (per browser); a stable
  `SECRET_KEY` keeps it valid across restarts.
