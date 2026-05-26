"""Clock-sync strategies for resolving the TartuBid auction winner.

Each strategy takes the raw bids as they arrived at their auction server
(each bid carries the *local* server time at which it was accepted) and
returns the bid that wins the auction, plus an optional warning string
when the result is ambiguous.

The strategies model the three mechanisms compared in the poster:

  * NaiveResolver           -- no synchronisation at all (baseline).
  * NTPResolver             -- NTP-style offset estimation against a
                               reference server.
  * BerkeleyResolver        -- Berkeley averaging across the auction
                               cluster.
  * TrueTimeResolver        -- bounded-uncertainty intervals (as in
                               Google Spanner), plus a commit-wait
                               check at the auction deadline.

The implementations are deliberately small. They are accurate to the
qualitative behaviour described in the literature but skip the
production details (filtering, dispersion, leap-second smearing, ...).
"""

from dataclasses import dataclass
from statistics import mean
from typing import Iterable


@dataclass(frozen=True)
class Bid:
    bidder: str
    amount: float
    server_id: str
    server_local_time: float  # seconds since epoch, on the server's own clock


@dataclass
class Resolution:
    winner: Bid | None
    strategy: str
    note: str = ""


class NaiveResolver:
    """No clock sync: trust each server's local timestamp directly."""

    name = "Naive (no sync)"

    def __init__(self, deadline_utc: float):
        self.deadline_utc = deadline_utc

    def resolve(self, bids: Iterable[Bid]) -> Resolution:
        accepted = [b for b in bids if b.server_local_time <= self.deadline_utc]
        if not accepted:
            return Resolution(None, self.name, "no bids before deadline")
        winner = max(accepted, key=lambda b: (b.amount, -b.server_local_time))
        return Resolution(winner, self.name)


class NTPResolver:
    """Estimate each server's offset against a reference and rewrite
    timestamps to the reference timeline before resolving.

    The offset model mirrors the four-timestamp NTP exchange:
        offset = ((t2 - t1) + (t3 - t4)) / 2
    Here we pass the offsets in directly; in a real deployment they
    would be measured periodically from the reference server.
    """

    name = "NTP"

    def __init__(self, deadline_utc: float, offsets: dict[str, float]):
        self.deadline_utc = deadline_utc
        self.offsets = offsets  # server_id -> estimated offset vs reference

    def resolve(self, bids: Iterable[Bid]) -> Resolution:
        rewritten = [
            Bid(b.bidder, b.amount, b.server_id,
                b.server_local_time - self.offsets.get(b.server_id, 0.0))
            for b in bids
        ]
        accepted = [b for b in rewritten if b.server_local_time <= self.deadline_utc]
        if not accepted:
            return Resolution(None, self.name, "no bids before deadline")
        winner = max(accepted, key=lambda b: (b.amount, -b.server_local_time))
        return Resolution(winner, self.name)


class BerkeleyResolver:
    """Berkeley algorithm: the coordinator computes the average of all
    server clocks (minus the coordinator's own clock as the reference)
    and tells each server how much to adjust.

    For winner resolution we apply the *resulting* offset to each bid's
    timestamp before ordering them.
    """

    name = "Berkeley"

    def __init__(self, deadline_utc: float, server_clocks_at_sync: dict[str, float],
                 coordinator_clock_at_sync: float):
        self.deadline_utc = deadline_utc
        avg = mean(list(server_clocks_at_sync.values()) + [coordinator_clock_at_sync])
        # offset to subtract from each server's timestamps to align them
        # to the post-Berkeley consensus clock.
        self.offsets = {sid: clk - avg for sid, clk in server_clocks_at_sync.items()}

    def resolve(self, bids: Iterable[Bid]) -> Resolution:
        rewritten = [
            Bid(b.bidder, b.amount, b.server_id,
                b.server_local_time - self.offsets.get(b.server_id, 0.0))
            for b in bids
        ]
        accepted = [b for b in rewritten if b.server_local_time <= self.deadline_utc]
        if not accepted:
            return Resolution(None, self.name, "no bids before deadline")
        winner = max(accepted, key=lambda b: (b.amount, -b.server_local_time))
        return Resolution(winner, self.name)


class TrueTimeResolver:
    """TrueTime-style resolver with bounded uncertainty.

    Each timestamp is treated as an interval [t - epsilon, t + epsilon].
    A bid is *unambiguously before* the deadline iff t + epsilon <=
    deadline. If the interval straddles the deadline, we flag the bid
    as ambiguous and refuse to commit a winner (the auction would have
    to commit-wait until the uncertainty drains).
    """

    name = "TrueTime"

    def __init__(self, deadline_utc: float, epsilon: float,
                 offsets: dict[str, float]):
        self.deadline_utc = deadline_utc
        self.epsilon = epsilon
        self.offsets = offsets

    def resolve(self, bids: Iterable[Bid]) -> Resolution:
        rewritten = [
            Bid(b.bidder, b.amount, b.server_id,
                b.server_local_time - self.offsets.get(b.server_id, 0.0))
            for b in bids
        ]
        # commit-wait check at the deadline
        ambiguous = [b for b in rewritten
                     if abs(b.server_local_time - self.deadline_utc) <= self.epsilon]
        if ambiguous:
            return Resolution(
                None, self.name,
                f"commit-wait required: {len(ambiguous)} bid(s) inside "
                f"±{self.epsilon * 1000:.1f} ms uncertainty window around deadline"
            )
        accepted = [b for b in rewritten
                    if b.server_local_time + self.epsilon <= self.deadline_utc]
        if not accepted:
            return Resolution(None, self.name, "no bids unambiguously before deadline")
        winner = max(accepted, key=lambda b: (b.amount, -b.server_local_time))
        return Resolution(winner, self.name,
                          f"uncertainty ±{self.epsilon * 1000:.1f} ms")
