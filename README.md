# foretop

> Configurable producer of new hosts from pluggable feeds (Python).

Part of **[Eyry](https://eyry.io)** — open-source, agentic recon & offensive security tooling for
bug bounty hunters, red teamers, and pentesters. Foretop is the lookout: it watches for new hosts in your scope and feeds them into the pipeline.

## Status

🚧 **Early development.** Structure and APIs will change. Star/watch to follow along, and see
[eyry.io](https://eyry.io).

## What it does

- Source-agnostic producer with pluggable feeds
- First source: certstream (Certificate Transparency logs)
- Scope filtering; emit to a queue or stdout JSONL

## Install

_Coming soon._

## The Eyry suite

- **Vedette** — fast, multi-threaded HTTP prober (Rust)
- **Foretop** — configurable producer of new hosts from pluggable feeds (certstream first)
- **Purser** — Redis-backed priority queue & work distributor (hot/warm/cold/DLQ)
- **Pinnace** — general multi-turn agent runtime: compaction, tools, Docker sandbox
- **Aplomado** — AI security scanner/reviewer built on Pinnace
- **Quarterdeck** — agent control plane: scheduler, events, IRC-style chat + pipeline orchestration

## License

MIT © Eyry
