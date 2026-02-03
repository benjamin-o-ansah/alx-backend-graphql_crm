from datetime import datetime

from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

LOG_FILE = "/tmp/crm_heartbeat_log.txt"
GRAPHQL_URL = "http://localhost:8000/graphql"
LOW_STOCK_LOG_FILE = "/tmp/low_stock_updates_log.txt"



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
def update_low_stock():
    transport = RequestsHTTPTransport(url=GRAPHQL_URL, verify=True, retries=1, timeout=20)
    client = Client(transport=transport, fetch_schema_from_transport=False)

    mutation = gql(
        """
        mutation {
          updateLowStockProducts {
            updatedProducts {
              name
              stock
            }
            message
          }
        }
        """
    )

    ts = datetime.now().strftime("%d/%m/%Y-%H:%M:%S")

    try:
        result = client.execute(mutation)
        payload = result.get("updateLowStockProducts", {})
        updated_products = payload.get("updatedProducts", []) or []
        message = payload.get("message", "OK")

        with open(LOW_STOCK_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{ts} - {message}\n")
            for p in updated_products:
                f.write(f"{ts} - Updated: {p.get('name')} -> stock={p.get('stock')}\n")

    except Exception as e:
        with open(LOW_STOCK_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{ts} - ERROR running updateLowStockProducts: {e}\n")
        raise