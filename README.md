# Global Context: Memory Across Channels (Voice AI Hackathon 2.0, PS-02)

This builds a context layer keyed by **GLID** from **real IndiaMART data**: the 11-feed Global Context seller dataset plus the **live Global Context API**. It produces `seller.md` for every seller and `buyer.md` for every GLID with buying activity. A **voice and WhatsApp bot** (built on Sarvam AI) loads the right file before every call or chat. It obeys "Handle with care" constraints, opens with a personalised line, continues the conversation across channels without re-asking, and writes each finished conversation back into the file.

> **Data is REAL and internal-use-only.** The dataset is not masked: messages and summaries contain real names. `contexts/`, `data/`, `evidence/` and the dataset folder are gitignored. Events created by the benchmark scripts are labelled `simulated.*`. See [Privacy](#privacy-and-safety). Before using the bot on real GLIDs, confirm that sending file contents to Sarvam's API is allowed for this data.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# .env  needs: SARVAM_API_KEY, GC_API_AK (employee token, expires every 24h), GC_API_EMPID, GC_API_XFF, GC_API_BASE
.venv/bin/python scripts/build_all.py        # CSV index (~1.5 s) + live-API snapshots for the featured GLIDs. No files are pre-built
.venv/bin/uvicorn app:app --port 8000
```

| URL | What |
|---|---|
| http://localhost:8000/ | **Bot console**: 8 featured real GLIDs, or search any GLID or company. 📞 voice (outbound or inbound) or 💬 WhatsApp. The live file is shown on the right. ⚡ simulate activity · ↻ live API refresh |
| `GET /context/<glid>/<seller\|buyer>.md` | The raw file, the shared asset |
| `POST /api/events` | Ingest new activity. Affected files are rebuilt in about 80ms |
| `POST /api/gc/refresh/<glid>` | Pull the live Global Context API now and rebuild |

## Data sources

### 1. Global Context seller dataset (`Global Context - Seller Dataset/`, 1 Apr – 2 Oct 2026)

These CSVs stand in for the source-system APIs. `context_layer/dataset.py` loads them into one event store (SQLite): 322,024 events in about 10s.

| File | Event type | Feeds |
|---|---|---|
| `gc_seller_profile.csv` | `seller_profile` (state) | snapshot, KYC, **Handle with care** (do-not-call, frustration, asked-if-bot, objections, already with an executive), VANI history |
| `gc_enquiries_received.csv` | `enquiry` (buyer → seller) | leads: read/unread, latest rows |
| `gc_enquiry_messages.csv` | `enquiry_message` | reply rate (any seller message in the thread) |
| `gc_buyer_calls_received.csv` | `pns_call` | buyer calls: connected rate, talk time, missed |
| `gc_buyleads_bought.csv` | `buylead_bought` | buy-lead consumption and top keywords |
| `gc_whatsapp_messages.csv` | `wa_message` | WhatsApp engagement and read rate |
| `gc_whatsapp_chatbot_conversations.csv` | `wa_chat` | seller threads (photo uploads, feedback, callbacks). `Msite_BL*` / buy intents go to **buyer.md** as requirements posted |
| `gc_buyer_call_extractions.csv` | `call_extraction` | `seller_role_on_call=BUYER` goes to buyer.md (products, specs, prices). SELLER rows give stock and price facts |
| `gc_bot_calls.csv` / `gc_bot_call_turns.csv` | `vani_call` / `vani_turns` | past VANI calls (disposition and summary) and language detection |
| `gc_executive_calls.csv` | `exec_call` | executive touchpoints |

### 2. Live Global Context API (`context_layer/gc_api.py`)

The API works in two steps: `POST generateContextUID {mapping_type:1, mapping_value:<GLID>, source_id, empid, ak}` returns a `mapping_id`, and `GET x/getContext?mapping_id=…` returns the snapshot. A `mapping_id` is short-lived, so the client asks for a new one on every refresh.

| API section | Used for |
|---|---|
| `kycdetails` | first name, company, city, plan (Paid / TS Pro …), **auto-debit (NACH) status**, renewal, vintage, KYC, account manager (first name only), **open tickets**, last executive note |
| `ticketsdetails` | open ops tickets, negative or irate feedback |
| `activitydetails` | live enquiry and buyer-call counters, catalog gaps (no price or photo), CQS, market size and competitors, **`BUYER_ACTIVITY`** (searches, browsing, C2C, enquiries, buy-leads) for buyer.md |
| `connectdetails` | executive call status, meeting notes and summaries (30d) |

**Precedence:** live API state beats the dataset. For example, the dataset says GLID 209139024 is unpaid, while the API says `Paid · TS Pro`.

**Refresh:** the API is pull-only. It's refreshed (a) at session start if the cached snapshot is older than `GC_API_TTL_S` (1h), (b) by the sweep for the featured set, and (c) on demand. Measured latency: `generateContextUID` 80–330ms (occasionally about 5s cold) plus `getContext` 90–400ms, then **snapshot → file in 60–100ms**. If the API is down or the token has expired, the bot uses the last file and says so in the session log.

## Runtime context pipeline: API first, then CSV, API wins (`context_layer/pipeline.py`)

This is the pipeline for building any GLID's file **on demand**: incoming calls, session start, or `GET /api/context/runtime/<glid>?role=seller|buyer`.

```
1. API    POST generateContextUID {mapping_type:1, mapping_value:<glid>, source_id:1, empid, ak} → mapping_id
          GET  x/getContext?mapping_id=<uuid>                                                 → live account state
          (mapping_id reused for 10 min; regenerated automatically if getContext says "Mapping Not Found")
2. CSV    that GLID's rows read straight from the 11 CSV files via a byte-offset index (data/csv_index.pkl)
3. LIVE   events not in the CSVs: bot write-backs, activity POSTed to /api/events
4. MERGE  field by field (context_layer/merge.py): if API and CSV both have a value and differ → API value.
          CSV fills what the API lacks. Live API counters (enquiries/calls 30/90d) replace CSV counts; CSV rows give the detail.
5. BUILD  deterministic render → 3,000-char cap → atomic write → front matter records pipeline, conflicts_resolved, degraded
```

Measured on real GLIDs:

| Case | Example | Total |
|---|---|---|
| API + CSV, first call | 209139024 (557 CSV rows; account_type Paid from API over Free in CSV) | ~0.45–1.0s |
| API + CSV, `mapping_id` reused | same GLID, second call | **~0.2s** |
| API only (not in the dataset) | 441 | ~0.3s |
| Neither (cold start) | 999999997 | ~0.3s |
| API down or token expired | falls back to last snapshot + CSV, `degraded: [gc_api]` | ~0.3s |

The step breakdown is API 70–900ms, CSV read 18–150ms, merge and build 1–7ms. The response lists the timing of every step, each conflict that was resolved, and the source of each field.

## IndiaMART domain knowledge (`contexts/indiamart_domain_knowledge.md`)

This is the shared glossary and playbook: buyer and seller terms, how to map what a caller says to an IndiaMART concept, troubleshooting flows, conflict and stale-data rules, privacy, and voice style. The bot reads it **alongside** the caller's `buyer.md` or `seller.md`, as Appendix A of the file describes. The file describes IndiaMART, `seller.md` describes the caller, and the conversation shows what the caller needs right now.

As the file's own implementation note asks, it is **not injected whole** (36 KB). `context_layer/domain.py` loads:
* **Every prompt:** a core set (operating principles, privacy and authorised actions, voice style, missing/conflicting/stale/no-history rules), about 4k characters.
* **Opening:** the buyer or seller opening-line examples and "identify the latest relevant activity".
* **Each turn:** sections matched to the caller's intent by English and Hinglish keywords (from Appendix B and the Section 7 table). The intents are lead generation, lead quality, contact outcome, listing/visibility, service/payment, KYC, buyer enquiry, purchase, cross-channel and escalation. Intents stay "sticky" for follow-up turns. If nothing matches, the statement → concept table is loaded instead.
* **Budget:** 7,600 characters (about 1.9k tokens). The full system prompt is about 3.4k tokens.
* **Updates:** the file is re-read when it changes, so the domain team can edit it without a restart. Each conversation write-back records the intents covered (`intents: [...]`).
* **Endpoints:** `GET /context/indiamart_domain_knowledge.md` serves the file. `GET /api/domain/select?text=…&role=seller` shows which sections a given utterance would load.

## File contract (`seller.v2` / `buyer.v2`)

* YAML front matter: `schema, glid, role, generated_at, freshness_ms, build_ms, sources {events_until, live_api}, lookback_days, cold_start, degraded, data`
* The same `## ` sections always appear in the same order. An empty section renders `- none`. Key/value sections use `- key: value`, and lists use `|`-separated rows.

| seller.md | buyer.md |
|---|---|
| Snapshot (language + source, account/plan/auto-debit, vintage, business, KYC, account manager) | Snapshot (language, business buyer, KYC) |
| **Handle with care** (do-not-call, open tickets, churn, frustration, asked-if-bot, already with exec, objections) | **Open threads** (bot write-backs, latest requirement posted, last seller contacted, last sourcing call) |
| **Open threads** (bot write-backs, executive status and notes, VANI call-later or meeting, unread enquiries, catalog gaps) | **Known facts (do not re-ask)** (specs and price from the latest sourcing call, plus bot write-backs) |
| **Known facts (do not re-ask)** (categories, location preference, stock and price quoted, bot write-backs; newest wins, conflicts shown as `(was …)`) | Requirements posted (60d) |
| Leads & enquiries (90d): received / read / replied / unread>48h, buy-leads, latest rows | Searches & browsing (30d) |
| Buyer calls (90d) | Sellers contacted (90d, named when known) |
| Catalog & market | Sourcing calls (90d): product, specs, price |
| Conversations (all channels: bot, VANI, WhatsApp bot, executive) | Conversations (all channels) |
| Engagement (WhatsApp read rate, VANI history, exec calls, best time, level) | Engagement |

**Size:** capped at **3,000 characters (about 750–850 tokens)**, enforced by stepping down through tighter layouts. On real data the seller median is **1,692 characters** (p95 2,329, max 2,849) and the buyer median is 1,173. That is under 1% of a 128K context, cheap to resend on every voice turn, and readable by a person in about 30 seconds. Real sellers have 11 source families plus live account state, which is why the cap went up from the synthetic version's 2,400.

### Lookback windows (`config.py`)

| Source | Window | Why |
|---|---|---|
| Enquiries, enquiry messages, buyer calls | 90d | Lead lifecycle. Matches the API's own `enq_last_90_days` / `pns_received_90_days` |
| Buy-leads bought | 45d | The warehouse keeps only about 45 days |
| VANI bot calls and transcripts | **180d** | Sparse (about 2 calls per seller in 6 months). The bot must remember every past call, objection and outcome so it never repeats a pitch |
| WhatsApp chatbot | 60d | Requirement, photo-upload and feedback threads stay resumable for about 2 months |
| Executive calls | 60d | Recent relationship context |
| Call extractions | 90d | Products, specs and prices stay relevant for a quote cycle |
| WhatsApp delivery/read, buyer activity (searches, browsing) | 30d | Engagement and intent decay fast |
| Bot write-backs | 30d | Resumable conversation threads |
| Account, KYC, tickets, catalog, market | latest | Live API state |

## Freshness

Freshness uses a **hybrid** design.
* **Event-driven:** an ingested event rebuilds every affected file (an enquiry touches the buyer's *and* the seller's file) after a 50ms debounce. The renderer is deterministic, with no LLM in the loop.
* **Pull:** the live API is refreshed at session start (when stale), by the sweep, and on demand.
* **Scheduled sweep (15 min):** re-renders, offline, only the files that exist (GLIDs that have been used). It ages out lookback windows and relative dates ("yesterday", "3d ago").

Measured on real files (`scripts/measure_freshness.py`, 50 events against the live server):

| | p50 | p95 |
|---|---|---|
| event ingested → file written | **78ms** | 86ms |
| event ingested → reader sees the new file | 81ms | 91ms |
| live API snapshot landed → file written | 60–100ms | |
| end of conversation → file updated (LLM summary + rebuild) | about 0.5s | |

## Bot integration

* **Load:** the bot reads the role-specific file, after refreshing a stale API snapshot. An unknown GLID gets a clean cold-start file and a generic opening.
* **Handle with care becomes hard rules.** `care_directives()` turns the flags into explicit instructions:
  * **Do-not-call:** an outbound voice call is **refused by the API** (HTTP 409). Inbound calls are allowed, with no pitching.
  * **Frustration:** the bot opens with one apology and keeps it short.
  * **Asked if it's a bot:** it discloses that it's an AI in the first sentence.
  * **Churn signal or cancelled auto-debit:** empathy first, no upsell.
  * **Already with an executive:** the bot names them and doesn't re-pitch.
  * **Open ticket:** the bot acknowledges it.
* **Direction:** voice defaults to outbound (VANI calls the seller), and chat or WhatsApp to inbound. Inbound openings thank the user and offer help before raising open threads.
* **No re-asking:** a "Known facts" section, an explicit list of known keys, and a re-confirm guard that regenerates the reply once.
* **Write-back:** when a session ends, the LLM summarises it into `summary`, `open_items`, `resolved_items` and `facts`. That becomes a `conversation` event, the file is rebuilt, and the next channel resumes from it.
* **Channels:** voice (browser mic → Saaras STT → `sarvam-105b-conversations` → Bulbul TTS) and WhatsApp (chat UI, plus a Cloud-API-shaped webhook). App and web chat use the same session API.

Openings on real GLIDs (from `evidence/demo_transcript.md` and live tests):
* **Fairy Zari (frustrated before):** "Jariwala ji, pehle ke calls ke liye maafi chahti hoon… 16 September wali Nakshi Dapka Zari lead par reply karna hai."
* **Siddhi Enterprises (auto-debit cancelled, told the executive "no results in 3 months"):** "Mukesh ji… auto-debit बंद होने की परेशानी समझ सकती हूँ, कल Tanisha जी से आपकी बात हुई थी…"
* **Wicks N More (do-not-call):** the outbound call is blocked.
* **Anil (Shreeva Enterprises) as a buyer:** "…2 din pehle aapne EPE Becker Rod post kiya tha, main abhi matching sellers dhoondh rahi hoon."

**Known issue:** during the real-data demo run, some replies fell back to the canned "technical dikkat" error message, because `sarvam-105b-conversations` returned empty text. The cause isn't confirmed yet. `bot/sarvam.py` now logs the finish reason when this happens. Re-run `scripts/demo.py` once real-data LLM use is cleared, to diagnose it and regenerate the evidence.

## Privacy and safety

* **Kept out of the files:** emails, addresses, phone numbers (also scrubbed from free text), GST/PAN numbers, account-manager email and employee ID, and raw ticket text. People appear by first name. KYC appears as flags only. The API's raw responses stay in `data/gc_cache/` (gitignored) and never reach a `.md` file.
* **Isolation between parties:** a seller's file shows each enquiry as "FirstName, City | product | status". It never shows the buyer's other activity. Bot conversations are role-scoped. The bot loads only the caller's own file and is told to refuse other parties' data. On real data it refused a request for "other sellers' plans and prices" and for a buyer's phone number.
* **No collecting:** a guard stops the bot from asking for phone numbers, emails or IDs.
* **External LLM:** the bot sends the caller's file (about 2–3k characters, with the PII above already removed, but still containing real first names, company names and executive notes) to **Sarvam's API**. Make sure this is allowed under IndiaMART's data agreement before using real GLIDs. Otherwise, pseudonymise names before the LLM call.
* **Do-not-call** is enforced in the API: outbound calls to those sellers are refused.

## Files are runtime-only

Nothing is pre-built. A GLID's `contexts/<GLID>/seller.md` or `buyer.md` is created the first time it is used: a call or chat starts, the console shows it, or someone requests `GET /context/<glid>/<role>.md`, `/api/context/<glid>/<role>` or `/api/context/runtime/<glid>`. After that, new activity and the 15-minute sweep keep it fresh offline (no API calls), and every new conversation rebuilds it live (APIs first, then CSV). Any team can still read a file through `GET /context/<glid>/<role>.md`, which builds it on first request.

The CSV dump is never copied into the database. The pipeline reads one GLID's rows straight from the files through a byte-offset index. `data/events.db` holds only live events: conversation write-backs, callback/meeting requests and POSTed activity.

## Featured demo GLIDs (`config.FEATURED`)

| GLID | Situation |
|---|---|
| 209139024 | Shreeva Enterprises: executive meeting fixed, keyword-mapping note. Also sourcing as a buyer (EPE backer rod) |
| 239368219 | Siddhi Enterprises: churn risk (auto-debit cancelled, prefers Amazon), already with an executive |
| 42559301 | Fairy Zari: showed frustration on VANI calls, trust objection |
| 7444262 | Wicks N More: **do-not-call**, 61 unread enquiries |
| 5397256 | MS Enterprises: last VANI call was "meeting fixed" |
| 83127677 | Atif Communication: last VANI call was "call back later" |
| 47648617 | Sunflash Tetratech: asked if talking to a bot, auto-debit cancelled |
| 12855767 | Live WhatsApp chats in the API, high enquiry volume |

## Layout

```
config.py                 lookbacks, size cap, refresh timing, models, FEATURED
context_layer/            dataset (CSV loader) · gc_api (live API) · store · sources · render · builder · refresher · parser · privacy
bot/                      sarvam (SDK wrappers) · agent (sessions, care directives, guards, write-back)
app.py                    FastAPI: channels, events, runtime context files, freshness, voice picker, webhook
web/                      index.html (console) · voices.html (voice picker)
scripts/                  build_all.py · demo.py · measure_freshness.py
```
