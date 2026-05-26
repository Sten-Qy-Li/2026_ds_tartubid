"""Coordinator: pulls bids from a list of auction servers and resolves
the winner under each clock-sync strategy.

In a real deployment this would be a long-lived service; for the demo
it is a function called once after the auction's deadline has passed.
"""

from __future__ import annotations

import time

import httpx

from clock_sync import (
    Bid, NaiveResolver, NTPResolver, BerkeleyResolver, TrueTimeResolver,
)


def fetch_clocks(servers: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for url in servers:
        r = httpx.get(f"{url}/clock", timeout=5.0)
        r.raise_for_status()
        data = r.json()
        out[data["server_id"]] = data["local_time"]
    return out


def fetch_bids(servers: list[str]) -> list[Bid]:
    out: list[Bid] = []
    for url in servers:
        r = httpx.get(f"{url}/bids", timeout=5.0)
        r.raise_for_status()
        out.extend(Bid(**b) for b in r.json())
    return out


def estimate_ntp_offsets(server_clocks: dict[str, float], reference: float
                         ) -> dict[str, float]:
    """Trivial offset estimator. In a real NTP setup these would be
    measured via the four-timestamp exchange and filtered."""
    return {sid: clk - reference for sid, clk in server_clocks.items()}


def resolve_all(servers: list[str], deadline_utc: float, epsilon: float = 0.05
                ) -> None:
    coordinator_clock = time.time()
    server_clocks = fetch_clocks(servers)
    bids = fetch_bids(servers)

    offsets_ntp = estimate_ntp_offsets(server_clocks, reference=coordinator_clock)

    print(f"\nCoordinator clock at sync: {coordinator_clock:.3f}")
    print("Per-server local clocks   :", {k: round(v, 3) for k, v in server_clocks.items()})
    print(f"Auction deadline (UTC ref): {deadline_utc:.3f}")
    print()

    resolvers = [
        NaiveResolver(deadline_utc),
        NTPResolver(deadline_utc, offsets_ntp),
        BerkeleyResolver(deadline_utc, server_clocks, coordinator_clock),
        TrueTimeResolver(deadline_utc, epsilon=epsilon, offsets=offsets_ntp),
    ]
    for r in resolvers:
        res = r.resolve(bids)
        if res.winner is None:
            print(f"{res.strategy:<22} -> no commit  ({res.note})")
        else:
            w = res.winner
            note = f" [{res.note}]" if res.note else ""
            print(f"{res.strategy:<22} -> winner: {w.bidder} @ {w.amount} "
                  f"(server={w.server_id}){note}")
