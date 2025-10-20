#!/usr/bin/env python3
"""
Utility script to print messages from a Google Cloud Pub/Sub subscription.

Example:
    python read_pubsub_events.py --project-id your-project --subscription inventory-orders-sub
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from concurrent.futures import TimeoutError
from typing import Optional

from google.cloud import pubsub_v1


def _decode_payload(data: bytes) -> str:
    """Attempt to jsonify the payload for readability."""
    text = data.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(parsed, indent=2, ensure_ascii=False)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read and print messages from a Google Cloud Pub/Sub subscription."
    )
    parser.add_argument(
        "--project-id",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        help="Google Cloud project ID (default: value from GOOGLE_CLOUD_PROJECT env var).",
    )
    parser.add_argument(
        "--subscription",
        default=os.environ.get("PUBSUB_SUBSCRIPTION"),
        help=(
            "Subscription ID or full subscription path "
            "(default: value from PUBSUB_SUBSCRIPTION env var)."
        ),
    )
    parser.add_argument(
        "--no-ack",
        action="store_true",
        help="Do not acknowledge messages after printing them.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Optional seconds to keep the subscriber running before exiting.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    if not args.project_id:
        raise SystemExit("Missing project ID. Provide --project-id or set GOOGLE_CLOUD_PROJECT.")

    if not args.subscription:
        raise SystemExit(
            "Missing subscription. Provide --subscription or set PUBSUB_SUBSCRIPTION."
        )

    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = (
        args.subscription
        if "/" in args.subscription
        else subscriber.subscription_path(args.project_id, args.subscription)
    )

    # Report stats on ctrl+c
    consumed = {"count": 0}

    def callback(message: pubsub_v1.subscriber.message.Message) -> None:
        consumed["count"] += 1
        print(f"\nMessage #{consumed['count']}")
        print(f"  ID:        {message.message_id}")
        print(f"  Published: {message.publish_time}")
        print(f"  Ordering:  {message.ordering_key or '-'}")
        if message.attributes:
            print("  Attributes:")
            for key, value in sorted(message.attributes.items()):
                print(f"    {key}: {value}")
        else:
            print("  Attributes: -")
        print("  Data:")
        print(_decode_payload(message.data))

        if args.no_ack:
            print("  Action: message left unacked")
        else:
            message.ack()
            print("  Action: message acknowledged")

    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    print(f"Listening for messages on {subscription_path}. Press Ctrl+C to stop.")

    def _handle_sigint(signum, frame) -> None:  # type: ignore[override]
        print("\nStopping subscriber...")
        streaming_pull_future.cancel()

    signal.signal(signal.SIGINT, _handle_sigint)

    with subscriber:
        try:
            streaming_pull_future.result(timeout=args.timeout)
        except TimeoutError:
            streaming_pull_future.cancel()
            streaming_pull_future.result()
        except Exception as exc:  # noqa: BLE001
            streaming_pull_future.cancel()
            streaming_pull_future.result()
            raise exc

    print(f"Total messages processed: {consumed['count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
