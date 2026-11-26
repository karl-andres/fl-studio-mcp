# SongsFlow ChatGPT app

SongsFlow is an OpenAI Apps SDK widget and a separate HTTP MCP server. It does not expose the FL Studio control tools. MIDI import is the first integration milestone; a Mac companion is future work.

## Run and connect

Use Python 3.12 (the app requires Python 3.11+), Node 24, uv, and npm. The former cryptography<49 compatibility cap was replaced with a patched >=50 constraint after security scanning. Intel Macs may need Rust and OpenSSL to build current cryptography releases; do not restore the vulnerable pin to avoid that build. The original FL Studio stdio server retains its Python 3.10 declaration; the app extra selects its newer dependencies on Python 3.11+.

```sh
# From the repository root
CC=gcc uv sync --extra app --dev --locked
cd web
npm ci
npm run build
cd ..
SONGSFLOW_PUBLIC_URL=http://localhost:8765 uv run --extra app songsflow-app
```

`GET /health` is the readiness check. The widget HTML is built into `src/songsflow/widget/index.html` and packaged with Python wheels; build the widget before `uv build`. Generated bundles are ignored by Git. The build also generates and packages third-party license notices for dependency code included in the widget. `docs/dependency-inventory.json` records the reviewed installed versions and license metadata. Rebuild after frontend changes. The repository is an isolated checkout; no worktree is needed.

For standalone layout/editing development: `cd web && npm exec vite -- --host 0.0.0.0`. Preview and MIDI generation require ChatGPT's host APIs. Standalone mode supports editing and local JSON backups, but does not pretend that a ChatGPT connection exists.

For ChatGPT, deploy the same server behind a trusted HTTPS ingress, set `SONGSFLOW_PUBLIC_URL=https://your-owned-domain` and `SONGSFLOW_PORT` if different from 8765, and connect its `/mcp` endpoint through ChatGPT's developer app settings. The HTTPS origin is configuration, never a tool argument. Do not expose the development Vite server publicly. Use a single process/worker: downloads are intentionally process-local. Configure ingress request limits and shared rate limiting when scaling, and replace memory downloads with an encrypted TTL store before using multiple workers.

The Apps SDK UI resource and tool metadata follow OpenAI's official `openai-apps-sdk-examples`. Current ChatGPT embedded rendering, host audio policy, external download behavior, and phone support still require an actual connected-app acceptance test; a browser host mock is not that test.

## Writing and music

Select a lyric position, choose a root and chord quality, and attach a chord. Chords display above words. Timeline order is independent of lyric position, and changing text never silently removes its chord events: anchors inside deleted text become “Reattach to lyrics.” Anchors count Unicode code points, including emoji.

Chords: major, minor, dominant seventh and minor seventh, with sharp/flat roots. Voicings use MIDI root notes 48–59. `Cmaj`/`Cmin` are accepted aliases for imported/generated songs. Preview uses a simple synthesized piano-like tone, not sampled instruments. Explicit durations are quarter-note beats, in half-beat increments. A 4/4 bar is 4 beats; 3/4 and 6/8 bars are 3 quarter-note beats. Tempo always counts quarter notes, including 6/8. Changing meter does not rewrite existing durations.

The arrangement repeats section IDs. Preview and export derive from the same server-generated progression. MIDI is type 0 at 480 ticks/quarter note, channel 1, program 0 (piano), velocity 80, with tempo, meter and UTF-8 section markers. FL Studio may use the project's tempo on import; verify the project's tempo against the exported song. Import the downloaded `.mid` into the intended Piano Roll/channel on the Mac, then confirm pitches, durations and repeats before treating the integration as validated.

Download a JSON backup to keep a song independently of ChatGPT. Imports replace the current draft only after confirmation. Widget state is a chat-scoped convenience, not durable storage or a cross-device song library. Separate rendered widgets are independent snapshots: continue in the newest editor. Ask ChatGPT to help using the editor's button so it receives the latest document. Song proposals carry a baseline revision and never apply without review and confirmation; stale proposals are rejected. New result widgets restore the supplied baseline when no widget draft exists.

## Tool contracts

- `open_song()`: opens the editor without replacing a saved widget draft.
- `validate_song(document)`: validates the versioned song and returns its canonical document plus preview events.
- `propose_song(document, base_revision, current_document)`: returns a reviewable proposal and unchanged baseline. Both documents must carry the supplied revision.
- `export_song(document, format="midi" | "json")`: returns a capability URL, expiry, filename and token. No server-side song ID or database is created.
- `revoke_exports(tokens)`: removes only downloads whose unguessable capabilities are supplied. The widget uses this when clearing its draft.

A version-1 song has `version`, `revision`, `title`, `tempo`, `meter`, `sections` and `arrangement`. Sections have `id`, `name`, `lyrics`, `chords`; chords have `id`, `symbol`, `anchor` (offset or null), `beats`. See `music.py` for authoritative limits. Lyrics and imported documents are untrusted data, never instructions or HTML.

## Validate

```sh
uv run --extra app pytest -q tests
uv run ruff check .
cd web
npm test
npm run test:e2e
npm run build
npm run format:check
npm audit
cd ..
uvx pip-audit --path .venv/lib/python3.12/site-packages
```

Playwright uses `/usr/bin/chromium` in this cloud environment; set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to use another installed Chromium, or install Playwright Chromium and omit the executable override. Browser tests use a mocked ChatGPT host; Python tests exercise real MCP discovery and tools. Production dependencies use patched lodash/KaTeX overrides because Apps SDK UI 0.2.2 otherwise brings known vulnerable versions. Keep the overrides until upstream releases patched constraints; rerun builds and interaction tests when changing them.

## Security, privacy and launch gates

See [PRIVACY.md](PRIVACY.md) for the notice and data inventory. The server does not require raw OpenAI or FL Studio credentials and makes no external AI calls. There are no analytics or tracking cookies. Frontend strings render through React text nodes, without HTML/Markdown interpretation. The bundled widget needs no external asset or connection domains; its CSP only permits the configured download redirect origin. DNS-rebinding/Host and Origin protections remain enabled.

The HTTP guard enforces a 1 MB body limit, a 15-second body-read deadline, and 120 requests per source IP per minute. It does not trust forwarded IP headers. Shared proxy clients therefore share a quota; configure ingress controls deliberately. Musical generation is bounded to 10,000 chord events. Download cache is capped at 128 items and 32 MB. The endpoint is an unauthenticated, stateless personal prototype; there is no account separation or permanent song library. Put OAuth and tenant-scoped storage in place before adding accounts or private persistent data.

Downloads use cryptographically random 256-bit capability tokens, `no-store`, `nosniff`, attachment filenames, and a no-referrer policy. Access expires after 15 minutes; a background sweep removes expired memory within 30 seconds. Process shutdown clears all exports. Anyone possessing the link can download until expiry. Clearing a draft revokes its retained export tokens; already-downloaded copies and ChatGPT messages remain outside that control. Export history retains at most 128 capabilities per widget; older links still expire on schedule.

Application access logging is disabled, and song validation errors omit submitted values. No lyrics or tokens should be sent to telemetry. At the hosting ingress, disable body/query/path logging for MCP and downloads or redact capability paths. Keep only minimal operational logs for at most 14 days. Use HTTPS, managed secrets, encryption for host disks/backups, and provider DPAs and regional settings appropriate to the eventual audience. The app itself writes no song/export files to disk.

Before public distribution: identify the operator and privacy contact; select and document hosting region/providers; publish the completed privacy notice; configure ingress retention and abuse controls; review current OpenAI app policies; review applicable privacy/consumer/copyright obligations; check dependency licenses and vulnerability reports. Do not advertise GDPR/CCPA certification. No deployment, legal review, ChatGPT connection, App Directory submission or live FL Studio validation is implied by local test success.
