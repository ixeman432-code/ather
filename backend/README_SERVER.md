# Athar backend — first Unity integration

This is the first server version for Unity integration.

Endpoints:
- POST /api/next-scenario
- POST /api/log-event
- GET /health

CORS is enabled for the prototype.

Run locally from the `backend` directory:
`pip install -r requirements.txt`
`uvicorn server:app --reload`

Render:
- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn server:app --host 0.0.0.0 --port $PORT`

The current `/api/next-scenario` response is intentionally static/fallback-first. It reads the approved hadith knowledge from `app/kb.py` and does not call Claude yet.
