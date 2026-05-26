"""CLI client that submits a bid to one of the auction servers."""

import argparse

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True, help="e.g. http://127.0.0.1:8001")
    parser.add_argument("--bidder", required=True)
    parser.add_argument("--amount", type=float, required=True)
    args = parser.parse_args()

    r = httpx.post(f"{args.server}/bid",
                   json={"bidder": args.bidder, "amount": args.amount},
                   timeout=5.0)
    r.raise_for_status()
    print(r.json())


if __name__ == "__main__":
    main()
