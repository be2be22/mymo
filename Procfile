# Procfile for Railway / Heroku-style deployments
web: python main.py
worker: python -c "from scheduler.jobs import run_check_now; import asyncio; asyncio.run(run_check_now())"
