from datetime import datetime

from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

LOG_FILE = "/tmp/crm_heartbeat_log.txt"
GRAPHQL_URL = "http://localhost:8000/graphql"


def log_crm_heartbeat():
    # Optional GraphQL hello check (endpoint responsiveness)
    try:
        transport = RequestsHTTPTransport(url=GRAPHQL_URL, verify=True, retries=1, timeout=10)
        client = Client(transport=transport, fetch_schema_from_transport=False)
        query = gql("{ hello }")
        result = client.execute(query)
        _ = result.get("hello")
    except Exception:
        # We still log heartbeat even if GraphQL fails
        pass

    timestamp = datetime.now().strftime("%d/%m/%Y-%H:%M:%S")
    line = f"{timestamp} CRM is alive"

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
