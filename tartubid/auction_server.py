"""HTTP auction server for TartuBid.

Each server holds one auction in memory. Its clock can be skewed at
startup via the ``--skew`` flag, which is what makes the demo
interesting: with skew, the order in which bids appear to arrive
depends on which server you ask.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from clock_sync import Bid


class BidIn(BaseModel):
    bidder: str
    amount: float


def build_app(server_id: str, skew_seconds: float) -> FastAPI:
    app = FastAPI()
    bids: list[Bid] = []

    def local_now() -> float:
        return time.time() + skew_seconds

    @app.get("/clock")
    def clock():
        return {"server_id": server_id, "local_time": local_now()}

    @app.post("/bid")
    def post_bid(bid: BidIn):
        if bid.amount <= 0:
            raise HTTPException(400, "bid amount must be positive")
        accepted = Bid(
            bidder=bid.bidder,
            amount=bid.amount,
            server_id=server_id,
            server_local_time=local_now(),
        )
        bids.append(accepted)
        return asdict(accepted)

    @app.get("/bids")
    def list_bids():
        return [asdict(b) for b in bids]

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="logical server id, e.g. eu-west")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--skew", type=float, default=0.0,
                        help="seconds to add to this server's local clock")
    args = parser.parse_args()
    uvicorn.run(build_app(args.id, args.skew), host="127.0.0.1", port=args.port,
                log_level="warning")


if __name__ == "__main__":
    main()
