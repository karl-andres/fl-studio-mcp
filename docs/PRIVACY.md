# SongsFlow privacy notice — personal prototype

This notice describes this implementation. Before serving other people, the operator must publish their identity, privacy contact, hosting providers and processing locations here and in the app listing. These deployment-specific details are not yet configured; this is not a public-release compliance certification.

## Data and purposes

| Data | Where processed | Purpose and retention |
| --- | --- | --- |
| Lyrics, chords, arrangement, title, tempo | Embedded widget and ChatGPT widget state; app server during requested tool calls | Editing, validation, conversational revisions, preview and export. No app database. Widget-state retention is controlled by ChatGPT. |
| Conversation and songwriting requests | ChatGPT/OpenAI | Subject to OpenAI's applicable terms, privacy policy, user settings and account controls. The app does not independently train a model or call another AI provider. |
| Reference audio metadata and manual timing marks | Widget state/JSON backups; app server during requested tool operations | Filename, duration, size, SHA-256 and chord timestamps support reattachment and export. No audio bytes in draft state or backups. |
| Original reference audio | Browser memory while editing; app memory only on explicit audio export | Playback and byte-for-byte download. No transcription, chord detection, training or external audio-analysis provider. Server validation checks format/duration/size/hash in an isolated, time-bounded process. |
| MIDI, lyric text, original audio or requested JSON exports | App process memory | Download delivery. Access expires at 15 minutes; deletion within a further 30 seconds, on draft revocation, or process shutdown. No export files are written to disk. |
| Source IP and request timing | Server memory | Rate limiting. Buckets expire after one minute; active source entries are bounded. |
| Operational diagnostics | Hosting provider, if configured | Configure no lyric/body/token logging and a maximum retention of 14 days. Provider logs and backups must be evaluated before public launch. |
| Local backups and downloaded MIDI, lyric text and audio | User's device | Controlled by the user; not removed by clearing the app draft. |

Lyrics and chord data are sent to the app server only for requested tool operations. Original audio attached inside the widget stays in browser memory until **Export for FL Studio** is explicitly selected. That action uploads a temporary copy; downloads expire after 15 minutes and are removed within a further 30 seconds. Pending upload tickets contain metadata only and expire after 60 seconds (cleanup within a further 30 seconds). If you attach audio to ChatGPT itself, OpenAI handles that attachment under its own policies before the app accesses it; this is separate from the app’s temporary export storage. Clicking “Ask ChatGPT to help” sends the current song into the conversation. There is no public sharing catalog, advertising, third-party analytics, or permanent song library. The app does not request your OpenAI API key or FL Studio credentials.

## Choices and deletion

Use **Save backup** to retain a portable song file and **Import backup** to reopen it. **Clear draft** resets the current widget draft, releases its in-memory audio/object URL, and attempts to revoke retained active export links. If revocation fails, the app reports it and those links still expire on schedule. **Remove reference** removes the browser recording and its timing marks; it does not revoke previously exported copies. It does not delete existing ChatGPT conversation messages, other widget snapshots, OpenAI-held records, downloads, or backups. Use ChatGPT's own account/conversation controls for OpenAI-held data, and your device's controls for downloaded files.

Do not treat widget state as guaranteed permanent or synchronized storage. Temporary download URLs are bearer capabilities: anyone with the URL can use it until it expires. Do not share a URL unless you intend to share its contents.

## Rights and contact

Users retain their rights in submitted material. Import lyrics and recordings only when you have the necessary permission, including consent from other people captured in a recording. SongsFlow does not scrape lyrics websites or provide a licensed lyrics catalog.

For this personal prototype, privacy requests go to the person operating the app. A public version must name that operator and provide a working privacy contact, applicable rights-request procedures and regional disclosures before launch. Hosting contracts, legal bases, data-processing agreements and international transfer safeguards depend on the deployment and must be reviewed at that time.
