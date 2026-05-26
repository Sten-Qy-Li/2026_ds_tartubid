# TartuBid

A small distributed online-auction prototype used to motivate the
*Clock synchronization* topic of the Distributed Systems poster session
(LTAT.06.007, University of Tartu).

The system is intentionally tiny: it is a vehicle for showing **why**
clock synchronization matters in an auction (close-to-deadline bid
ordering decides the winner), not a production system.

## Components

- `auction_server.py` &mdash; HTTP server that accepts bids for a single
  auction. Each server has its own (possibly skewed) local clock.
- `bidder_client.py` &mdash; CLI client that submits bids to a chosen
  server.
- `coordinator.py` &mdash; central registry / winner-resolver. Pulls
  bids from all auction servers after the deadline and resolves the
  winner using a configurable clock-sync strategy.
- `clock_sync.py` &mdash; three pluggable strategies:
  *naive (no sync)*, *NTP-style offset estimation*, *Berkeley
  averaging*, and a *TrueTime-style uncertainty interval* resolver.
- `demo.py` &mdash; runs a scripted scenario: starts two servers with
  artificial clock skew, submits a few near-deadline bids, then resolves
  the winner under each strategy and prints the outcome.

## Quick start

```
python -m venv .venv
. .venv/Scripts/activate     # PowerShell: . .venv\Scripts\Activate.ps1
pip install fastapi uvicorn httpx
python demo.py
```

`demo.py` prints, for each clock-sync strategy, who would win the
auction under the same bid traffic. With deliberately skewed clocks
the naive strategy picks the wrong winner; NTP and Berkeley converge
on the right one; TrueTime additionally reports its uncertainty and
flags the result as **commit-wait required** when the deadline falls
inside the uncertainty interval.

## Status

Prototype-grade. Not hardened, not tested under load, persistence is
in-memory only. Source of truth for the poster is the qualitative
behaviour shown by `demo.py`.
