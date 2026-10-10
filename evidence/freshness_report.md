# Freshness evidence

Run: 2026-10-09T14:12:16 · 50 events against the live server · data: REAL GLIDs + simulated events (labelled)

Mechanism: event-driven rebuild (50 ms debounce) plus a scheduled sweep every 15 min. **Delay = time from an event being ingested to the rebuilt file being on disk.**

| metric | p50 | p95 | max |
|---|---|---|---|
| pipeline (ingest → file written) | 77.8 ms | 86.2 ms | 188.5 ms |
| observed by a reader (ingest → served file changed) | 80.7 ms | 90.7 ms | 190.5 ms |

Per event type (p50 pipeline ms):

- enquiry → seller file: 75.0 ms (n=10)
- buyer call → seller file: 79.2 ms (n=10)
- WhatsApp chatbot turn: 62.6 ms (n=10)
- VANI call outcome: 72.3 ms (n=10)
- requirement posted → buyer file: 79.8 ms (n=10)

Live Global Context API (pull-only, refreshed at session start / sweep / on demand):

| GLID refresh | generateContextUID | getContext | snapshot → file |
|---|---|---|---|
| 209139024 | 4219 ms | 174 ms | 67.4 ms |
| 239368219 | 118 ms | 167 ms | 100.4 ms |
| 42559301 | 127 ms | 116 ms | 62.0 ms |
| 5397256 | 331 ms | 130 ms | 73.4 ms |
| 12855767 | 113 ms | 212 ms | 61.4 ms |

Conversation write-back (end of call → summary by sarvam-105b-conversations → file rebuilt) is measured
separately in `evidence/demo_transcript.md`. It is dominated by the LLM summary (~0.5–1.5 s).
