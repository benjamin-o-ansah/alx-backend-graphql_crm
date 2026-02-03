from __future__ import annotations

from datetime import datetime
from pathlib import Path

import requests

LOG_PATH = Path("/tmp/crm_heartbeat_log.txt")
GRAPHQL_URL = "http://localhost:8000/graphql"


def log_crm_heartbeat() -> None:
    """
    Logs a heartbeat line:
    DD/MM/YYYY-HH:MM:SS CRM is alive
    Optionally verifies GraphQL 'hello' is responsive.
    Appends to /tmp/crm_heartbeat_log.txt
    """
    timestamp = datetime.now().strftime("%d/%m/%Y-%H:%M:%S")

    # Optional GraphQL health check
    graphql_ok = True
    try:
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": "{ hello }"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        graphql_ok = bool(data.get("data", {}).get("hello") == "Hello, GraphQL!")
    except Exception:
        graphql_ok = False

    # Build message (keep required format exact; append GraphQL status after)
    line = f"{timestamp} CRM is alive"
    if not graphql_ok:
        line += " (GraphQL DOWN)"
    else:
        line += " (GraphQL OK)"

    # Append to file
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
