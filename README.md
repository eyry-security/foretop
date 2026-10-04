# Foretop

A pluggable live feed of new hosts for your scope. The lookout aloft of the
[Eyry](https://eyry.io) recon suite.

Foretop watches a source, keeps only the hosts inside a scope you define, and
hands them off — to stdout, a file, or straight into a Redis queue for
[Vedette](https://github.com/eyry-security/vedette) to probe. The first source
is **certstream**: every TLS certificate issued by a public CA is published to
Certificate Transparency logs, so the moment someone gets a cert for
`new-thing.example.com` it shows up here — often before the service is fully
live.

Source-agnostic by design. certstream is the first feed; DNS, subdomain
enumeration, wordlists, and third-party APIs slot in behind the same interface.

MIT licensed. Watch only scopes you are authorized to test.

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

# Filter the firehose against a big list of scopes (e.g. bug-bounty wildcards)
foretop --scope-file scopes.txt --redis redis://127.0.0.1:6379 --queue purser:in
```

`--scope-file` is built for large sets — tens of thousands of `*.domain`
patterns are indexed by suffix, so each candidate is matched in O(labels), not
by scanning every pattern.

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
| `-s, --source <NAME>` | `certstream` | Feed to watch |
| `--scope <PATTERN>` | – | In-scope pattern; repeatable (required) |
| `--exclude <PATTERN>` | – | Out-of-scope pattern; repeatable |
| `--scope-file <FILE>` | – | File of in-scope patterns, one per line (# comments ok) |
| `--exclude-file <FILE>` | – | File of out-of-scope patterns, one per line |
| `-o, --output <FILE>` | – | Append JSONL records to a file |
| `--redis <URL>` | – | Push hostnames to a Redis list |
| `--queue <KEY>` | `vedette:hosts` | Redis list key to push to |
| `--no-redis-dedup` | – | Don't keep a Redis seen-set across restarts |
| `--max <N>` | – | Stop after N in-scope hosts |
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
{"host":"api.example.com","source":"certstream","scope":"*.example.com","seen_at":"2026-08-03T02:14:07Z","meta":{"issuer":"Let's Encrypt","ct_log":"Google 'Argon2026'"}}
```

Only `host` flows downstream to a prober — the Redis sink pushes the bare
hostname, which is exactly what Vedette's `BRPOP` reader expects. The JSON
record keeps the provenance for when the feed is useful on its own
(`foretop --json ... | jq`).

Wildcard certificate names (`*.example.com`) are flattened to their base domain
(`example.com`) by default, since that base is a real host worth probing. Use
`--no-wildcards` to drop them instead.

## Adding a source

Sources are plugins behind one small interface:

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

Register it in `foretop/sources/__init__.py` and it's available as
`--source mysource`. The runner handles scope filtering, dedup, and fan-out to
sinks for free.

## Where it fits

```
Foretop (new hosts) → Purser (queue) → Vedette (probe + fingerprint) → Aplomado (AI review)
```

Foretop is the top of the funnel: it decides *what to look at* by watching for
new hosts the moment they appear. See the suite at
[github.com/eyry-security](https://github.com/eyry-security).

## Roadmap

- More sources: passive DNS, subdomain enumeration, ASN/CIDR ranges, static lists
- Optional full-record push to Redis (JSON payload, not just the hostname)
- Persistent on-disk dedup for long-running standalone use

## License

MIT © Eyry
