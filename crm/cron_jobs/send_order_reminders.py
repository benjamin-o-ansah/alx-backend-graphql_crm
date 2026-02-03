#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport


GRAPHQL_ENDPOINT = "http://localhost:8000/graphql"
LOG_FILE = "/tmp/order_reminders_log.txt"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_z(dt: datetime) -> str:
    # GraphQL DateTime commonly accepts ISO8601; keep it explicit UTC
    return dt.astimezone(timezone.utc).isoformat()


def log_line(message: str) -> None:
    ts = utc_now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} - {message}\n")


def main() -> None:
    # last 7 days window
    since = utc_now() - timedelta(days=7)

    transport = RequestsHTTPTransport(
        url=GRAPHQL_ENDPOINT,
        verify=True,
        retries=2,
        timeout=20,
    )

    # Query orders with order_date >= since
    # Works with typical Relay connection shape: edges { node { ... } }
    query = gql(
        """
        query PendingOrders($since: DateTime!) {
          allOrders(filter: { orderDateGte: $since }) {
            edges {
              node {
                id
                orderDate
                customer {
                  email
                }
              }
            }
          }
        }
        """
    )

    try:
        with Client(transport=transport, fetch_schema_from_transport=False) as session:
            result = session.execute(query, variable_values={"since": isoformat_z(since)})

        edges = (
            result.get("allOrders", {})
            .get("edges", [])
        )

        for edge in edges:
            node = edge.get("node") or {}
            order_id = node.get("id")
            customer = node.get("customer") or {}
            customer_email = customer.get("email")

            # Log reminder line
            log_line(f"Reminder: Order {order_id} for {customer_email}")

        print("Order reminders processed!")

    except Exception as e:
        # Still log failures to help debugging cron runs
        log_line(f"ERROR: Failed to process order reminders - {e}")
        # Re-raise so failures are visible when running manually
        raise


if __name__ == "__main__":
    main()
