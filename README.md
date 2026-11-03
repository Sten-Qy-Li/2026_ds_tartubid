# TartuBid — Clock Synchronization in a Distributed Online Auction

**Status:** Archived academic coursework — Spring 2026.

## Overview

This repository contains **TartuBid**, a group project prepared for the Distributed Systems course (LTAT.06.007) at the University of Tartu during the spring semester of 2026.

The project was developed for the course's poster session on 5 June 2026.

TartuBid explores the problem of clock synchronization in distributed online auctions, particularly how differences between server clocks can affect bid ordering and the fairness of auction outcomes.

## Project Scope

The project compares three approaches to clock synchronization:

- **Network Time Protocol (NTP)** — Clock synchronization using network time sources.
- **Berkeley Algorithm** — Coordinated clock adjustment across distributed nodes.
- **TrueTime-inspired approach** — Time uncertainty intervals and delayed decisions near auction deadlines.

A naive approach without clock synchronization is also included as a baseline.

The project combines an academic poster, supporting documentation, and a Python prototype demonstrating how different clock synchronization strategies can affect auction results.

## Repository Contents

| Path | Description |
|---|---|
| `main.tex` | LaTeX source of the academic poster |
| `refs.bib` | Bibliographic references |
| `unitartu-theme.sty` | University-themed LaTeX poster styling |
| `unitartu_compact.png` | University logo asset |
| `documentation.md` | Detailed project documentation |
| `tartubid/` | Python prototype and simulation notebook |
| `speaking-guide/` | Poster-session presentation guide |

## Running the Prototype

The scripted comparison can be run with Python 3.10 or newer:

```bash
python tartubid/demo.py
```

The script uses a predefined set of bids and artificial clock offsets to compare auction outcomes under different synchronization strategies.

This demonstration runs locally without starting the HTTP services. For additional components and instructions, see [`tartubid/README.md`](tartubid/README.md).

The prototype is intended for educational purposes and does not represent a production-ready distributed auction platform.

## Historical Note

This repository preserves the materials prepared for the University of Tartu's Distributed Systems poster project in spring 2026.

The project was developed collaboratively, and the original source code, documentation, and commit history have been retained for academic reference.

The repository is no longer actively maintained.
