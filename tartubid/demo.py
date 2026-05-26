"""Scripted end-to-end TartuBid demo.

We skip the HTTP layer here because the goal of the demo is to show
how the *clock-sync strategy* changes the winner, not to exercise
networking. We synthesise the same bid trace that would occur if
two clients had bid against two skewed servers near the deadline.

Run:  python demo.py
"""

from __future__ import annotations

from clock_sync import (
    Bid, NaiveResolver, NTPResolver, BerkeleyResolver, TrueTimeResolver,
)


def main() -> None:
    # --- scenario ------------------------------------------------------
    # The "true" UTC deadline of the auction.
    deadline_utc = 1_000_000.000

    # Two auction servers. eu-west's clock is 80 ms fast; us-east's
    # clock is 60 ms slow. (Realistic-ish skew for NTP-synchronised
    # cloud VMs that haven't been re-synced for a while.)
    skew = {"eu-west": +0.080, "us-east": -0.060}

    # Reference (coordinator) clock at the moment of resolution.
    coordinator_clock = 1_000_000.500  # 500 ms after the deadline

    # Server local clocks captured at the same instant.
    server_clocks = {sid: coordinator_clock + s for sid, s in skew.items()}

    # Bids as they were recorded by each server, with each server
    # stamping the bid using its own (possibly skewed) clock.
    #
    # In *true* UTC:
    #   - Anup bids 100 EUR via eu-west at UTC 999_999.970  (BEFORE deadline)
    #   - Mumin bids 110 EUR via us-east at UTC 1_000_000.030 (AFTER  deadline)
    #
    # But each server stamps with its own skewed clock, giving the
    # timestamps below.
    bids = [
        Bid(bidder="Anup",  amount=100.0, server_id="eu-west",
            server_local_time=999_999.970 + skew["eu-west"]),   # ~1_000_000.050
        Bid(bidder="Mumin", amount=110.0, server_id="us-east",
            server_local_time=1_000_000.030 + skew["us-east"]),  # ~  999_999.970
    ]

    # --- offset estimation (coordinator-side) --------------------------
    offsets_ntp = {sid: clk - coordinator_clock for sid, clk in server_clocks.items()}

    # --- run each strategy ---------------------------------------------
    print("TartuBid -- clock-sync strategy comparison")
    print("-" * 60)
    print(f"True deadline (UTC) : {deadline_utc:.3f}")
    print(f"Server skew         : {skew}")
    print(f"Bids as recorded    :")
    for b in bids:
        print(f"  - {b.bidder:<6} {b.amount:>6.2f} @ {b.server_id} "
              f"(local stamp {b.server_local_time:.3f})")
    print()

    resolvers = [
        NaiveResolver(deadline_utc),
        NTPResolver(deadline_utc, offsets_ntp),
        BerkeleyResolver(deadline_utc, server_clocks, coordinator_clock),
        TrueTimeResolver(deadline_utc, epsilon=0.050, offsets=offsets_ntp),
    ]
    for r in resolvers:
        res = r.resolve(bids)
        if res.winner is None:
            print(f"{res.strategy:<22} -> NO COMMIT  ({res.note})")
        else:
            w = res.winner
            note = f"  [{res.note}]" if res.note else ""
            print(f"{res.strategy:<22} -> winner: {w.bidder} @ {w.amount} EUR "
                  f"(via {w.server_id}){note}")

    print()
    print("Interpretation:")
    print("  - Naive picks Mumin because us-east's slow clock made his")
    print("    late bid look on-time -- the unfair outcome.")
    print("  - NTP and Berkeley both rewrite the timestamps onto a")
    print("    consensus clock and correctly reject Mumin's late bid,")
    print("    awarding the auction to Anup.")
    print("  - TrueTime refuses to commit because the deadline falls")
    print("    inside its uncertainty interval; in Spanner-style")
    print("    'commit-wait' the auction would simply wait for the")
    print("    uncertainty to drain before declaring the winner.")


if __name__ == "__main__":
    main()
