# GitHub Talent Hunt

This project finds GitHub users who match a job description.
It can use a fast heuristic or an AI model if configured.

## What is included

- `backend/` - Python app and GitHub search logic
- `frontend/` - simple web pages for search and results
- `.env.example` - example environment settings

## Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Fill in `.env`:
   - `GITHUB_TOKEN=` your GitHub token
   - `SECRET_KEY=` a long secret string
   - `LLM_PROVIDER=` use `none` if you do not want AI
   - `OPENAI_API_KEY=` only if using OpenAI

3. Install dependencies:
   ```bash
   cd backend
   python3 -m pip install -r requirements.txt
   ```

4. Run the app:
   ```bash
   python3 app.py
   ```

5. Open in browser:
   ```text
   http://127.0.0.1:8000
   ```

## Notes

- Do not commit `.env` to GitHub.
- The repository includes `.gitignore` to keep secrets and generated files out of git.
- If you do not set `OPENAI_API_KEY`, the app will use a heuristic fallback.

## How to use

1. Enter job requirements or keywords.
2. Optionally enter a location.
3. Set how many results to show.
4. Click `Search GitHub`.
