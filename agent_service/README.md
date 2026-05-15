# FactoryFlow ADK service

`server.py` exposes the local planner endpoint used by `frontend/server.mjs`:

```bash
POST http://127.0.0.1:8790/plan
```

It requires the Google ADK agent to run successfully. If `google-adk`, credentials, or the model call are unavailable, the endpoint returns an error instead of using a deterministic fallback plan.

Optional ADK setup:

```bash
cd agent_service
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export GOOGLE_API_KEY="..."
python server.py
```

`start_all.sh` automatically uses `agent_service/.venv/bin/python` when it exists.
