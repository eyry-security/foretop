# Foretop

A pluggable live feed of new hosts for your scope. See them the moment they appear.

Part of [Eyry](https://eyry.io) — a *foretop* is the lookout platform high on
the mast, first to spot new arrivals.

## What it does

- Watches a source feed for new hosts — certstream (Certificate Transparency)
  first, more sources plug in behind the same interface.
- Keeps only hosts inside a scope you define: repeatable `--scope` patterns,
  `--exclude` wins over scope.
- Hands hosts off to stdout (bare, one per line — exactly what Vedette reads),
  a JSONL file, or straight into a Redis queue.
- Dedups across restarts with a Redis seen-set (`--no-redis-dedup` to skip it).
- `--scope-file` indexes tens of thousands of `*.domain` patterns by suffix —
  built for bug-bounty wildcard lists, matched in O(labels) per candidate.

MIT licensed. Use only against systems you are authorized to test.

## Install

```sh
git clone https://github.com/eyry-security/foretop
cd foretop
pip install -e .            # core (stdout / file output)
pip install -e '.[redis]'   # add the Redis sink
```

Requires Python 3.9+.

## The certstream feed

The certstream source is a thin websocket client. It doesn't parse CT logs
itself — it connects to a **certstream server** that does the heavy lifting and
streams the results as JSON. The old public Calidog firehose is effectively
dead, so run your own; it's a single binary or one `docker run`, and it's fast:

```sh
# certstream-server-rust (recommended) — serves ws://localhost:8080/
docker run -d -p 8080:8080 ghcr.io/reloading01/certstream-server-rust:latest

# or certstream-server-go
docker run -d -p 8080:8080 0rickyy0/certstream-server-go
```

Foretop defaults to `ws://localhost:8080/`. Point it anywhere else — a remote
server, a different port, the `/full-stream` endpoint — with `--certstream-url`.
Both servers speak the same `certificate_update` JSON format Foretop expects.

## Usage

```sh
# Stream in-scope hosts to your terminal, one per line, as they appear
foretop --scope '*.example.com'

# Multiple scopes at once, piped straight into Vedette for probing
foretop --scope example.com --scope example.org | vedette -o live.jsonl

# A whole apex plus its subdomains, minus a noisy dev wildcard, saved to a file
foretop --scope example.com --exclude '*.dev.example.com' -o hosts.jsonl

# Feed hosts straight into Vedette's Redis queue
foretop --scope tesla.com --redis redis://127.0.0.1:6379 --queue vedette:hosts

# Watch everything (firehose), stop after 500 hosts
foretop --scope '*' --max 500

# Watch a quiet scope for ten minutes, then exit cleanly
foretop --scope '*.example.com' --duration 600

# Filter the firehose against a big list of scopes (e.g. bug-bounty wildcards)
foretop --scope-file scopes.txt --redis redis://127.0.0.1:6379 --queue purser:in
```

Then, downstream:

```sh
vedette --redis redis://127.0.0.1:6379 --queue vedette:hosts -o live.jsonl
```

### Scope

`--scope` is repeatable and matches two ways:

- **domain** — `example.com` matches `example.com` and any subdomain
  (`api.example.com`, `a.b.example.com`). The usual bug-bounty scope.
- **glob** — anything with `*`, `?`, or `[` uses shell-style matching:
  `*.example.com` matches subdomains only, `*` matches everything.

`--exclude` uses the same rules and wins over `--scope`.

### Options

| Flag | Default | Description |
| --- | --- | --- |
| `-s, --source <NAME>` | `certstream` | Feed to watch (only `certstream` for now) |
| `--scope <PATTERN>` | – | In-scope pattern; repeatable (required) |
| `--exclude <PATTERN>` | – | Out-of-scope pattern; repeatable |
| `--scope-file <FILE>` | – | File of in-scope patterns, one per line (# comments ok) |
| `--exclude-file <FILE>` | – | File of out-of-scope patterns, one per line |
| `-o, --output <FILE>` | – | Append JSONL records to a file |
| `--redis <URL>` | – | Push hostnames to a Redis list |
| `--queue <KEY>` | `vedette:hosts` | Redis list key to push to |
| `--no-redis-dedup` | – | Don't keep a Redis seen-set across restarts |
| `--max <N>` | – | Stop after N in-scope hosts |
| `--duration <SECONDS>` | – | Stop cleanly after this many seconds, even if no hosts match |
| `--json` | – | Print full JSONL records to stdout instead of bare hostnames |
| `--no-wildcards` | – | Drop wildcard cert names instead of flattening them |
| `--certstream-url <URL>` | `ws://localhost:8080/` | Certstream server websocket URL |
| `-q, --quiet` | – | Suppress stderr progress logs |

If neither `--redis` nor `-o` is given, bare hostnames go to stdout — one per
line, exactly what `vedette` expects on stdin, so
`foretop --scope example.com | vedette` just works.

## Output

Stdout prints the bare hostname, one per line:

```
api.example.com
cdn.example.com
```

Pass `--json` for the full record (JSONL) with provenance:

```json
{"host":"api.example.com","source":"certstream","scope":"*.example.com","seen_at":"2026-10-04T07:44:12Z","meta":{"issuer":"Let's Encrypt","ct_log":"Google 'Argon2026'"}}
```

Only `host` flows downstream to a prober — the Redis sink pushes the bare
hostname, which is exactly what Vedette's `BRPOP` reader expects. The JSON
record keeps the provenance for when the feed is useful on its own
(`foretop --json ... | jq`).

Wildcard certificate names (`*.example.com`) are flattened to their base domain
(`example.com`) by default, since that base is a real host worth probing. Use
`--no-wildcards` to drop them instead.

## Adding a source

Sources are plugins behind one small interface. Drop a module beside the others
and register it in the `_REGISTRY` dict in `foretop/sources/__init__.py`:

```python
from foretop.sources.base import Source
from foretop.models import Host

class MySource(Source):
    name = "mysource"

    async def candidates(self):
        while True:
            host = await get_next_host_somehow()
            yield Host(host=host, source=self.name)
```

It's then available as `--source mysource`. The runner handles scope filtering,
dedup, and fan-out to sinks for free.

## Where it fits

```
Foretop (new hosts) → Purser (queue) → Vedette (probe) → Rutt (store) → Aplomado (AI review)
```

Foretop is the top of the funnel: it decides *what to look at* by watching for
new hosts the moment they appear.

## The Eyry suite

- **eyry**: one CLI that wires the data plane together — discover → queue → probe → store
- **vedette**: fast, multi-threaded HTTP prober (Rust) — confirms what is live and fingerprints it
- **foretop**: pluggable live feed of new hosts, starting with Certificate Transparency logs
- **purser**: Redis-backed priority work queue — hot/warm/cold lanes, retries, dead-letter queue
- **rutt**: Postgres store for the host lifecycle (discovered → probed → reviewed) with an append-only scan log
- **pinnace**: general multi-turn agent runtime — compaction, tools, Docker sandbox, resumable sessions
- **aplomado**: AI security reviewer built on Pinnace — target in, structured findings out
- **quarterdeck**: agent control plane — scheduler, wake/sleep, identity and memory, IRC-style chat, ChatOps, pipeline orchestration
## Roadmap

- More sources: passive DNS, subdomain enumeration, ASN/CIDR ranges, static lists
- Optional full-record push to Redis (JSON payload, not just the hostname)
- Persistent on-disk dedup for long-running standalone use

## License

MIT © Eyry

---

Use only against systems you are authorized to test.
