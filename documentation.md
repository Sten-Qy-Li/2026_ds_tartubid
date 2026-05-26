# TartuBid &mdash; Clock Synchronization in a Distributed Online Auction

**Project documentation** &mdash; companion write-up for the poster
*"TartuBid: Clock Synchronization in a Distributed Online Auction"*
and the Python prototype in [`tartubid/`](tartubid/).

| | |
|---|---|
| **Course** | LTAT.06.007 Distributed Systems (Spring 2026) |
| **Institution** | Institute of Computer Science, University of Tartu |
| **Team** | Anup Kumar &middot; Md Mumin Ul Bari &middot; Sten (Qun-yan Li) |
| **Topic** | Clock synchronization |
| **Poster session** | 5 June 2026, 12:15&ndash;14:00, Delta building 2nd-floor lobby |

This document is intentionally longer-form than the poster. It walks
through every block of the poster in depth and then explains the
prototype code that backs the *Prototype evidence* block.

---

## Table of contents

1. [Project overview](#1-project-overview)
2. [Introduction](#2-introduction)
3. [System model](#3-system-model)
4. [Mechanisms](#4-mechanisms)
5. [Comparison and design choice](#5-comparison-and-design-choice)
6. [Implementation](#6-implementation)
7. [Prototype evidence](#7-prototype-evidence)
8. [Conclusion and future work](#8-conclusion-and-future-work)
9. [References](#9-references)

---

## 1. Project overview

The assignment asks each team to (1) describe the background and
system model of a chosen application and (2) compare three different
mechanisms for one specific distributed-systems challenge &mdash; in our
case, **clock synchronization**. At least one mechanism must come
from the course material and at least one must be researched
independently.

We chose to anchor the discussion in a concrete application,
**TartuBid**, a distributed online auction platform. Auctions are a
natural setting for clock-synchronization questions: the entire
fairness of the system hinges on whose timestamp the platform
trusts when two bids arrive close to the deadline.

The three mechanisms we compare are:

* **NTP** (Network Time Protocol) &mdash; covered in the course.
* **Berkeley algorithm** &mdash; covered in the course.
* **TrueTime** (as used in Google Spanner) &mdash; independently
  researched, not covered in the course.

Our chosen design adopts NTP everywhere and augments it with a
TrueTime-inspired *commit-wait* band around every auction's closing
instant. The reasoning is fleshed out in [&sect;5](#5-comparison-and-design-choice).

---

## 2. Introduction

### 2.1 The TartuBid application

TartuBid is a distributed online auction platform. Items belong to
auctions with a published closing instant; bidders on the public
Internet place bids over HTTPS up to that instant; whoever holds the
highest bid **strictly before** the deadline wins. To handle large
catalogues, items are sharded across a small number of regional
auction servers. A central coordinator maintains the
item-to-shard registry and is responsible for resolving the winner
of each auction after its deadline has passed.

We deliberately picked an application that is

* **time-sensitive by construction** &mdash; the auction outcome depends
  on a strict before/after relation around a single instant;
* **operationally familiar** &mdash; the architectural skeleton is the
  same as any sharded e-commerce stack, which keeps the system-model
  block of the poster honest;
* **representable at student scale** &mdash; the prototype in
  [`tartubid/`](tartubid/) is &lt;500 lines of Python and runs locally.

### 2.2 Why clock synchronization matters here

Computer clocks drift. A cheap quartz oscillator drifts roughly
1&nbsp;ms per 20&nbsp;s of running uncorrected [[1]](#ref-vansteen2017ds).
For an auction with second-granularity deadlines that drift is
usually invisible, but for two **competing bids arriving in the same
closing window** the difference between "won fairly" and "won
unfairly" can be a handful of milliseconds.

The poster's *Introduction* block illustrates this with a worked
example, which we reproduce here:

* **eu-west** &mdash; clock runs **+80 ms fast** vs. true UTC.
* **us-east** &mdash; clock runs **&minus;60 ms slow** vs. true UTC.
* **Anup** bids 100&nbsp;EUR on eu-west at true UTC **&minus;40 ms** (i.e. 40&nbsp;ms
  before the deadline &mdash; on time).
* **Mumin** bids 110&nbsp;EUR on us-east at true UTC **+30 ms** (30 ms
  after the deadline &mdash; late).

Each server stamps the bid with its own (skewed) local clock, so:

* Anup's bid gets stamped at &minus;40 + 80 = **+40 ms** &mdash; *appears late*.
* Mumin's bid gets stamped at +30 &minus; 60 = **&minus;30 ms** &mdash; *appears on time*.

A coordinator that trusts the raw local stamps will reject Anup's
on-time bid and accept Mumin's late one. **This is the failure mode
the rest of the poster is about preventing.**

---

## 3. System model

The poster compresses the system model into a single block with one
diagram. This section expands on each part.

### 3.1 Architecture

TartuBid follows a **tiered client&ndash;server** architecture:

* **Bidder clients.** Web/mobile UIs over HTTPS. Number is open-ended
  and treated as untrusted: clients do not participate in any cluster
  protocol; they only submit bids and receive outcome notifications.
* **Auction servers.** A small set of regional servers, each
  authoritative for a shard of items. In the poster we draw two
  (`auction-eu`, `auction-us`); the model generalises to *n*.
* **Coordinator.** A single logical service that maintains the
  item-to-shard registry and resolves the winner of every auction
  after its deadline. In a real deployment it would be made highly
  available via a consensus protocol; for this project we model it
  as a single point with crash-recovery semantics.

### 3.2 Communication model

Three communication patterns are present in the system and are
distinguished in the poster diagram by arrow style:

| Pattern | Used between | Arrow style on poster |
|---|---|---|
| Synchronous request/response | Bidder client &rarr; auction server | solid blue |
| Asynchronous notification | Auction server &rarr; bidder client | dashed orange |
| Reliable unicast (TCP + retry) | Auction server &harr; coordinator | thick dark-blue |

* **Synchronous request/response.** Bid submission must return a
  durable receipt before the user moves on, so it has to be
  request/response. The same channel is used for clock queries
  (`GET /clock`) during the prototype demo.
* **Asynchronous notification.** Bid outcomes (`you won`, `you were
  outbid`) are delivered out-of-band by push/email after the
  coordinator resolves the auction.
* **Reliable unicast.** Coordinator&harr;server traffic must not be
  lost, so it runs over TCP with application-level retries to mask
  crash and omission failures.

The poster diagram puts all three patterns into a single figure
with a legend, so the communication model is communicated visually
without the need for separate text bullets.

### 3.3 Timing model

We assume a **partially synchronous** model: in normal operation
message delay and clock drift are bounded, but the bounds are not
known statically. The bound on cross-server clock skew is the
dominant timing hazard during a closing window &mdash; that is the
single fact that all the chosen mechanisms attack.

This rules out designs that depend on a known, tight upper bound on
delay (such as some real-time synchronous protocols) and is the
reason the *Refuses ambiguous order* row of the comparison table
matters: under partial synchrony, NTP and Berkeley can be **wrong**
about whether a bid was on time but never report any uncertainty,
whereas TrueTime explicitly reports uncertainty and uses
commit-wait when it cannot be sure.

### 3.4 Failure model

The system tolerates:

* **Crash failures** of any single auction server or the coordinator,
  masked by persistence + replay on restart.
* **Omission failures** (lost messages), masked by TCP-level retries
  plus idempotent application-level handlers.

Byzantine failures (clients lying about timestamps, servers being
malicious) are **out of scope**. In a production system bidder-side
clock manipulation would need to be defended against by
server-stamping the bid on arrival &mdash; which is exactly what we do,
making the clock-sync question about *server* clocks rather than
bidder-side clocks.

---

## 4. Mechanisms

The poster's *Mechanisms* block presents each mechanism with a small
diagram and the key formula. This section is the longer version.

### 4.1 NTP &mdash; Network Time Protocol

NTP is the protocol most of the public Internet uses to keep wall
clocks within a few milliseconds of UTC.
[[2]](#ref-mills1991ntp)[[3]](#ref-rfc5905) It works in a hierarchy
of "strata": stratum 0 is an authoritative time source (atomic
clock, GPS, radio), stratum 1 servers are directly attached to one,
and each higher stratum *n* synchronises against stratum *n*&minus;1.

The core measurement is the **four-timestamp exchange** with a
reference server:

1. Client sends a request at time `t1` (client clock).
2. Server receives it at `t2` (server clock).
3. Server sends a reply at `t3` (server clock).
4. Client receives it at `t4` (client clock).

The client estimates the round-trip delay and the offset to the
server's clock as

$$
\delta = (t_4 - t_1) - (t_3 - t_2),
\qquad
\theta = \frac{(t_2 - t_1) + (t_3 - t_4)}{2}.
$$

The four-timestamp pair `(\delta, \theta)` is sampled repeatedly,
the eight most recent are buffered, and the minimum-`\delta` sample
is taken as the best estimate (because the least-delayed exchange
suffers the least asymmetric-path bias). The client then either
*slews* its clock (if `|\theta| < 125`&nbsp;ms) or *steps* it (larger
offsets), avoiding sudden backwards jumps where possible.

NTPv4 typically achieves ~10&nbsp;ms accuracy over the public Internet
and ~200&nbsp;µs over a LAN under good conditions.

**Strengths for TartuBid.** Available everywhere, zero marginal
cost (every cloud VM already runs `chronyd` or `ntpd`), aligns to
UTC so timestamps are externally meaningful.

**Weaknesses.** Asymmetric network paths bias `\theta`; the
protocol gives a point estimate, not an uncertainty bound, so it
cannot answer "is this bid definitely before the deadline?".

### 4.2 Berkeley algorithm

The Berkeley algorithm targets a different problem: synchronising a
**cluster of machines** that may not have access to an external UTC
source. [[4]](#ref-gusella1989berkeley) A designated time daemon

1. polls every machine in the cluster for its local clock value,
2. discards obvious outliers,
3. computes the **average** of the remaining clocks (including its
   own), and
4. sends each machine an individual adjustment `\Delta_i` that
   nudges its clock towards the consensus.

Formally, with `n` clocks `C_1, \ldots, C_n`:

$$
C_{\text{cons}} = \frac{1}{n}\sum_{i=1}^{n} C_i,
\qquad
\Delta_i = C_{\text{cons}} - C_i.
$$

The cluster converges on a common time, but that common time is **not
necessarily UTC** &mdash; it is just the average of the cluster's clocks.
If the cluster as a whole drifts away from UTC, Berkeley will not
notice.

**Strengths for TartuBid.** Works with no external reference (e.g.
in an air-gapped or unreliable-WAN environment), tolerates a slow
majority, computationally cheap.

**Weaknesses.** Bidder clients are **not** part of the cluster, so
client-side UI countdowns can disagree with the server's notion of
"the deadline". Also, the cluster's consensus time can quietly drift
from real UTC.

### 4.3 TrueTime (Google Spanner)

TrueTime is the timekeeping API that underpins Google's Spanner
globally-distributed database. [[5]](#ref-corbett2012spanner)
Unlike NTP and Berkeley, TrueTime does **not** return a point-valued
"now". Instead it returns an **uncertainty interval**:

$$
\mathrm{TT.now}() = [\, t - \varepsilon,\; t + \varepsilon \,]
$$

where `\varepsilon` is typically 1&ndash;7&nbsp;ms, kept tight by stacking
GPS receivers and atomic clocks in **every datacenter**. The system
is honest about what it does not know: if you ask "what time is it?"
just after a synchronization, `\varepsilon` is small; if synchronization
has been delayed, `\varepsilon` grows.

The pattern Spanner uses to take advantage of this honesty is
**commit-wait**: an operation assigned timestamp `s` does not commit
until `TT.now().earliest > s`. That guarantees external consistency
&mdash; once an operation is visible, real time has *definitely* moved
past its timestamp, so any later operation in real time will get a
later timestamp.

**Applied to TartuBid.** A bid whose adjusted timestamp interval
straddles the auction deadline is held until the uncertainty drains
(`~2\varepsilon`). The coordinator never has to guess; it simply waits
out the ambiguity and then resolves.

**Strengths.** Bounded uncertainty, refuses to commit ambiguous
orderings, exactly the semantic we want at an auction deadline.

**Weaknesses.** Requires GPS antennas + atomic clocks in every
datacenter; operationally expensive; overkill if your deadlines are
already coarse compared to typical NTP jitter.

---

## 5. Comparison and design choice

The poster's *Comparison and our choice* block contains a
colour-coded table and a framed conclusion. This section is the
longer justification.

### 5.1 Trade-off matrix

| | **NTP** | **Berkeley** | **TrueTime** |
|---|---|---|---|
| Typical accuracy | 1&ndash;10&nbsp;ms (WAN) | ms (internal only) | `\varepsilon \le 7`&nbsp;ms guaranteed |
| External UTC alignment | yes | no | yes |
| Extra hardware | none | none | GPS + atomic clocks per DC |
| Handles unknown delay | via filtering | via averaging | via `\varepsilon` bound |
| Refuses ambiguous order | no | no | **yes** (commit-wait) |
| Operational cost | low | very low | very high |
| Failure if reference down | degrades to free-run | still converges | widens `\varepsilon` |

### 5.2 Why Berkeley alone is not enough

Berkeley converges the **cluster** on some time, but bidder clients
are not part of that cluster. Two consequences:

1. The countdown timer the bidder sees in their UI is driven by the
   bidder's own clock, which may be tens of seconds off from the
   cluster consensus. A bid that the bidder *thinks* is on time can
   easily fail to arrive before the cluster-consensus deadline.
2. Berkeley provides no UTC alignment, so the published auction
   deadline ("closes at 18:00 EEST") has no canonical meaning.

### 5.3 Why full TrueTime is too much

Provisioning GPS antennas and atomic clocks in every cloud region
is operationally and financially prohibitive for a student project,
and TartuBid does not need nanosecond ordering across the globe.
Spanner needs TrueTime because it serialises transactions across
data centres; we just need to disambiguate the closing window of
each auction.

### 5.4 What we adopt

> **We adopt NTP as the everyday clock-synchronization mechanism,
> augmented with a TrueTime-inspired uncertainty band `\varepsilon = 50`&nbsp;ms
> around each auction's closing instant.**
>
> Bids whose NTP-adjusted timestamp falls inside
> `[t_{\text{close}} - \varepsilon,\, t_{\text{close}} + \varepsilon]`
> are neither auto-accepted nor auto-rejected; the coordinator
> *commit-waits* until `\varepsilon` drains, then resolves the winner
> with the deadline unambiguously in the past for every accepted
> bid.

This gives us NTP's cost profile with TrueTime's safety property
exactly where it matters &mdash; the closing window &mdash; and nowhere else.

We picked `\varepsilon = 50`&nbsp;ms as a defensible default: well above
typical NTP jitter (~10&nbsp;ms) and well below the human-perceptible
~250&nbsp;ms threshold for late-clicking. It can be raised dynamically
in degraded-network conditions, mirroring how TrueTime widens its
own `\varepsilon` when synchronization is stale.

---

## 6. Implementation

The prototype lives in [`tartubid/`](tartubid/) and is intentionally
small &mdash; it exists to back the *Prototype evidence* block of the
poster, not to be production-grade.

### 6.1 Project layout

```
tartubid/
+-- README.md            quick-start instructions
+-- clock_sync.py        Bid dataclass + four resolver strategies
+-- auction_server.py    FastAPI server holding bids for an auction
+-- bidder_client.py     CLI that submits a bid to a chosen server
+-- coordinator.py       pulls bids and resolves winner per strategy
+-- demo.py              scripted scenario, runs offline
+-- results.ipynb        Jupyter notebook reproducing the poster's
                         Prototype evidence block
```

### 6.2 `clock_sync.py` &mdash; the resolver implementations

This module is the heart of the project. It defines:

* `Bid` &mdash; an immutable dataclass holding `(bidder, amount,
  server_id, server_local_time)`. The crucial field is
  `server_local_time`, recorded on the **server's own clock** at the
  moment of acceptance.
* `Resolution` &mdash; a dataclass holding `(winner, strategy, note)`.
  `winner` is `None` when the resolver refuses to commit.

The four resolver classes share a `resolve(bids)` method:

#### `NaiveResolver`

No correction. Accepts every bid whose `server_local_time <=
deadline`, picks the highest. This is the baseline that fails under
clock skew.

#### `NTPResolver`

Takes a `{server_id: offset}` dict and rewrites every bid's
`server_local_time` by subtracting that server's offset, putting all
bids on a single reference timeline before applying the deadline
check.

In a real deployment the offsets would be measured periodically via
the four-timestamp exchange; for the demo we pass them in directly
because we want to compare strategies on the **same** scenario
deterministically.

#### `BerkeleyResolver`

Takes the cluster's clocks at sync time, averages them with the
coordinator's own clock, and derives a per-server adjustment
`\Delta_i = C_{\text{cons}} - C_i`. The adjustments are then applied
to bid timestamps the same way as NTP.

Notice that the resulting `C_{\text{cons}}` is just the cluster
average &mdash; not UTC. The resolver still works for the deadline
check because the deadline is also expressed on the same consensus
timeline.

#### `TrueTimeResolver`

Takes `\varepsilon` plus offsets, rewrites bid stamps onto the
reference timeline, and then applies the commit-wait check:

* If a bid's stamp is **definitely** before the deadline
  (`stamp + \varepsilon <= deadline`), it is accepted.
* If a bid's stamp is **inside** the
  `[deadline - \varepsilon, deadline + \varepsilon]` uncertainty
  window, the resolver refuses to commit (`winner = None`) and
  returns an explanatory note.
* Otherwise (definitely after deadline) the bid is rejected.

The "refuses to commit" branch is the one the prototype actually
exercises, because both bids in our scenario fall inside the 50&nbsp;ms
band.

### 6.3 The other files

| File | What it does |
|---|---|
| `auction_server.py` | A small FastAPI app exposing `GET /clock`, `POST /bid`, `GET /bids`. Configurable clock skew via `--skew`. |
| `bidder_client.py` | CLI that calls `POST /bid` on a chosen server. |
| `coordinator.py` | Pulls every server's clock and bids, then runs all four resolvers on the trace. |
| `demo.py` | Offline scenario &mdash; same bid trace as the notebook, no HTTP layer, fastest way to see the comparison. |

### 6.4 How to run

```bash
# in tartubid/
python -m venv .venv
. .venv/Scripts/activate           # PowerShell: . .venv\Scripts\Activate.ps1
pip install fastapi uvicorn httpx pandas matplotlib jupyter

# fastest: offline scripted scenario
python demo.py

# or open the notebook
jupyter notebook results.ipynb

# or run servers + coordinator end-to-end (two terminals):
python auction_server.py --id eu-west --port 8001 --skew  0.080 &
python auction_server.py --id us-east --port 8002 --skew -0.060 &
python bidder_client.py --server http://127.0.0.1:8001 --bidder Anup  --amount 100
python bidder_client.py --server http://127.0.0.1:8002 --bidder Mumin --amount 110
python -c "from coordinator import resolve_all; resolve_all(['http://127.0.0.1:8001','http://127.0.0.1:8002'], deadline_utc=<...>)"
```

---

## 7. Prototype evidence

### 7.1 Scenario

Same as the failure scenario in [&sect;2.2](#22-why-clock-synchronization-matters-here):

| | true UTC offset | server | server-local stamp |
|---|---|---|---|
| Anup (100&nbsp;EUR) | &minus;40&nbsp;ms (on time) | eu-west (+80&nbsp;ms fast) | +40&nbsp;ms (appears late) |
| Mumin (110&nbsp;EUR) | +30&nbsp;ms (late) | us-east (&minus;60&nbsp;ms slow) | &minus;30&nbsp;ms (appears on time) |

### 7.2 Results

Reproduced from `python demo.py` (also reproducible cell-by-cell
in [`results.ipynb`](tartubid/results.ipynb)):

| Strategy | Resolved winner | Outcome |
|---|---|---|
| Naive (no sync) | Mumin (110) | &#x2717; wrong winner |
| NTP | Anup (100) | &#x2713; correct |
| Berkeley | Anup (100) | &#x2713; correct |
| TrueTime | &mdash; commit-wait &mdash; | safe (no premature commit) |

### 7.3 Interpretation

* **Naive** picks Mumin because us-east's slow clock made the late
  bid look on-time &mdash; the unfair outcome the poster motivates.
* **NTP** and **Berkeley** rewrite the timestamps onto a consensus
  timeline before applying the deadline check, and both arrive at
  the correct winner (Anup).
* **TrueTime** refuses to commit while the deadline lies inside its
  50&nbsp;ms uncertainty window. The Spanner literature calls this
  pattern *commit-wait*: trade a tiny delay (~2`\varepsilon` ≈ 100&nbsp;ms)
  for a guarantee that the resolved winner is unambiguously
  correct.

The TrueTime outcome is what motivates our chosen design (NTP +
TrueTime-inspired uncertainty band): the **safety property** of
TrueTime, applied **only at the closing window**, costs us at most
a few hundred milliseconds of latency on every auction while
removing the entire class of clock-skew-induced wrong winners.

---

## 8. Conclusion and future work

The poster makes one main claim:

> For a distributed online auction, NTP plus a TrueTime-inspired
> 50&nbsp;ms uncertainty band at the closing window gives the cost
> profile of NTP and the safety property of TrueTime, exactly
> where it matters.

The prototype confirms the claim qualitatively: under deliberately
skewed clocks, NTP recovers the correct winner where Naive fails,
and TrueTime additionally avoids committing in the ambiguous case.

**Future work** we did not get to in the project:

* **Hybrid Logical Clocks (HLC)** [[6]](#ref-kulkarni2014hlc) as a
  drop-in replacement for the offset-rewriting step &mdash; HLC bridges
  physical and logical time and could simplify the
  cross-mechanism interface.
* **PTP (IEEE 1588)** [[7]](#ref-ieee1588) as a more accurate
  intra-datacentre option once we know the cluster is on
  hardware-supported NICs.
* **Empirical NTP jitter measurements** between real cloud regions,
  to calibrate `\varepsilon` from data rather than picking a defensible
  default.
* **A real HA coordinator**, since the current model still treats
  the coordinator as a single logical point.

---

## 9. References

<a id="ref-vansteen2017ds"></a>
[1] M. van Steen and A. S. Tanenbaum. *Distributed Systems*, 3rd
edition. Maarten van Steen, Leiden, 2017.

<a id="ref-mills1991ntp"></a>
[2] D. L. Mills. "Internet Time Synchronization: The Network Time
Protocol". *IEEE Transactions on Communications* 39(10):1482&ndash;1493,
1991. doi:[10.1109/26.103043](https://doi.org/10.1109/26.103043).

<a id="ref-rfc5905"></a>
[3] D. L. Mills, J. Martin, J. Burbank, W. Kasch. *Network Time
Protocol Version 4: Protocol and Algorithms Specification*. RFC 5905,
IETF, 2010. <https://www.rfc-editor.org/rfc/rfc5905>.

<a id="ref-gusella1989berkeley"></a>
[4] R. Gusella and S. Zatti. "The Accuracy of the Clock
Synchronization Achieved by TEMPO in Berkeley UNIX 4.3BSD". *IEEE
Transactions on Software Engineering* 15(7):847&ndash;853, 1989.
doi:[10.1109/32.29484](https://doi.org/10.1109/32.29484).

<a id="ref-corbett2012spanner"></a>
[5] J. C. Corbett *et al*. "Spanner: Google's Globally-Distributed
Database". *Proceedings of the 10th USENIX Symposium on Operating
Systems Design and Implementation (OSDI)*, pp. 251&ndash;264, 2012.

<a id="ref-kulkarni2014hlc"></a>
[6] S. S. Kulkarni, M. Demirbas, D. Madappa, B. Avva, M. Leone.
"Logical Physical Clocks". *Principles of Distributed Systems
(OPODIS)*, pp. 17&ndash;32, 2014.

<a id="ref-ieee1588"></a>
[7] J. C. Eidson, M. Fischer, J. White. "IEEE-1588 Standard for a
Precision Clock Synchronization Protocol for Networked Measurement
and Control Systems". *34th Annual Precise Time and Time Interval
Systems and Applications Meeting*, pp. 243&ndash;254, 2002.
