\---

name: indiamart-context-layer
description: Build an always-fresh, compact context file (seller.md / buyer.md) for any IndiaMART GLID by first calling the live APIs (Global Context generateContextUID → getContext, and the seller products-listing API), then reading that GLID's rows from the CSV dump, merging field by field with live data winning, and rendering a fixed-format Markdown file the voice/WhatsApp bot loads before it speaks.
version: 1.0
owner: Global Context hackathon team
---

# Skill: build the context layer for a GLID, ground IndiaMART terminology in the domain knowledge document, and provide runtime voice-action guardrails

Use this skill whenever a conversation is about to start (an incoming call, outbound VANI call, WhatsApp or chat session), or whenever someone asks for the current `seller.md` / `buyer.md` of a GLID. The output is one file: `contexts/<GLID>/seller.md` or `contexts/<GLID>/buyer.md`.

**Golden rules**

1. **APIs first, CSV second.** Live APIs describe the user *now*. The CSV dump is history up to its export date (2 Oct 2026).
2. **Live data wins every conflict.** For catalogue fields: products-listing API > Global Context API > CSV. For all other fields: Global Context API > CSV. Every override is recorded in the file.
3. **Never block a conversation. The APIs have a time budget (default 3s, running in parallel). If one fails or is slow, use its last saved snapshot, mark the file `degraded`, and carry on. Do not expose internal fetch failures to the customer or say that a technical issue is preventing retrieval; use a neutral, truthful response and offer another route only after trying to resolve the concern in-call.**
4. **Deterministic rendering, no LLM.** The same inputs always produce the same file. The only LLM-written text allowed is quoted from upstream summaries (VANI, executive notes) or from the bot's own end-of-conversation write-back.
5. **Compact and private.** The whole file (front matter included) is at most 3,000 characters. It must never contain phone numbers, emails, addresses, ID numbers or another party's private data.

\---

## 0\. Inputs

|Input|Where it comes from|
|-|-|
|`glid`|Identity resolution: caller number → GLID (identity table / IndiaMART lookup API). Never assume a phone number uniquely identifies an account|
|`role`|`seller` or `buyer`, from the line dialled or the channel's purpose. A GLID can be both; build the file for the role of *this* conversation|
|Credentials (env vars, never hard-coded)|`GC\_API\_BASE`, `GC\_API\_EMPID`, `GC\_API\_AK` (employee JWT, **expires every 24h**), `GC\_API\_XFF`, `CATALOG\_API\_URL`, `CATALOG\_API\_TOKEN`, `CATALOG\_API\_MODID` (default `ANDWEB`), `CATALOG\_API\_AK` (defaults to `GC\_API\_AK`)|

Unknown GLID or no caller match: produce a **cold-start** file (all sections `- none`) and never invent history.

\---

## 1\. Call the live APIs (in parallel, time-boxed)

Start both calls at the same time and wait at most `api\_budget\_s` (3s) in total. At ring time, start them **on the ring**, not on answer.

### 1a. Global Context API: two steps

**Step 1: get a mapping id**

```
POST {GC\_API\_BASE}/generateContextUID
Headers: content-type: application/json, X-Forwarded-For: {GC\_API\_XFF}
Body:    {"mapping\_type": 1, "mapping\_value": "<GLID>", "source\_id": 1, "empid": {GC\_API\_EMPID}, "ak": "{GC\_API\_AK}"}
→ {"code":200, "data":{"mapping\_id":"<uuid>"}, "message":"Success"}
```

**Step 2: fetch the context**

```
GET {GC\_API\_BASE}/x/getContext?mapping\_id=<uuid>
Headers: X-Forwarded-For: {GC\_API\_XFF}
→ {"code":200, "data":{ kycdetails, activitydetails, ticketsdetails, connectdetails, BLdetails, … }}
```

* A `mapping\_id` can be **reused for about 10 minutes**, which skips step 1. If `getContext` returns `"Mapping Not Found"`, generate a new one once and retry. Old IDs expire.
* `"Token Expired"` from step 1 means `GC\_API\_AK` needs replacing. Fall back to the last snapshot.
* An unknown GLID returns an empty shell (no company, no name). Treat that as *no live data*.
* Use only these fields (all others, including email, address, phone, account-manager email/empid and raw ticket text, are **never** copied):

|Section|Fields used|
|-|-|
|`kycdetails`|first\_name, company\_name, city, company\_type, customer\_type (Paid/Free), highest\_service, payment\_plan, renewal\_date, `nach\_status\[0].DIS\_TEXT` (auto-debit), SERVICE\_VINTAGE, registered\_since\_with\_indiamart, glusr\_usr\_listing\_status, input\_email\_verification\_status, address\_verification\_status, high\_churn, account\_manager\_bd.name (first name only), approved\_product\_count, WIP\_TICKET\_BUCKET (type + date), last\_call\_details\[0] (executive note + date)|
|`ticketsdetails`|WIP\_OPS\_TICKETS (type + date), negative\_feedback\_count, irate\_complaint\_count|
|`activitydetails`|enq\_last\_30/90\_days, pns\_received\_30/90\_days, last\_4\_week (pns picked/received, bl\_cons, bl\_credits\_alctd), last\_month (prd\_without\_price/photo, cq\_score, location\_preference), top3mcat\_data (market buy-leads, paid sellers), LAST\_ENQUIRY.PRODUCT\_NAME, **BUYER\_ACTIVITY** (Search / Browse / ENQ / C2C / BL with time, category, keyword and seller id, used for `buyer.md`)|
|`connectdetails`|connect\_30D: date, call\_sts\_update, call\_answered\_summary, meet\_sts\_update (executive touchpoints)|

### 1b. Seller products-listing API (sellers only)

```
GET {CATALOG\_API\_URL}
Query: token={CATALOG\_API\_TOKEN}  mod\_id={CATALOG\_API\_MODID}  gluserid=<GLID>  AK={CATALOG\_API\_AK}
       product\_filter=ALL  pg\_type=1  ordering=4        (4 = recently modified first)
→ {"Response":{"Code":"200","Status":"Success","Pagination":{"CurrentPage":1,"HasNextPage":true},
               "Data":{"PRODUCTS\_DATA":\[…20…], "PRODUCT\_FILTER\_COUNTS":{…}, "CATEGORY":{…}, "MAP\_DATA":{…}}}}
```

* **Fixed page size of 20.** Loop `pg\_type = 1, 2, …` while `Pagination.HasNextPage` is true. Never compute pages from counts, and ignore `PAGINATION\_REQUEST\_COUNT`.
* **Runtime fetches page 1 only.** That's about 0.4–1.3s and gives catalogue-wide counts plus the 20 most recently modified products. Crawl all pages only for offline jobs.
* `PRODUCT\_FILTER\_COUNTS`, `CATEGORY` and `MAP\_DATA` are **page-1-only**. Empty blocks on page 2+ are normal.
* **Observed in the live API** (this differs from the reference description): `CATEGORY` = the seller's own **product groups** (e.g. "New Items", "Door Guard"), and `MAP\_DATA` = **IndiaMART categories (mcats)** (e.g. "Door Seals"). Both have the shape `{id: \[product\_count, name]}`.
* `PRODUCT\_FILTER\_COUNTS.CQS = 0` means *not computed*. Don't treat it as a score; fall back to the next source.
* `extra\_detail=isq,multi\_img` adds ISQ and multi-image blocks. They're not needed for context files, so leave it off to keep the call light.
* `Code 204 "Data Not found"` means the GLID has **no catalogue**. That's a valid state, not an error.
* Fields used: counts (`PRODUCT\_COUNT`, `REJECTED\_COUNT`, `OUT\_OF\_STOCK\_COUNT`, `PRODUCT\_COUNT\_WITHOUT\_PRICE/\_PHOTO/\_SPECIFICATION/\_DESCRIPTION`, `PRODUCT\_COUNT\_WITH\_LOW\_SCORE`, `PRODUCT\_COUNT\_WITH\_INCORRECT\_PRICE`, `PRODUCT\_COUNT\_INVISIBLE\_ON\_DIR`, `CQS`). Per product: `ITEM\_NAME`, `PC\_ITEM\_FOB\_PRICE\_FORMATTED`, `PC\_ITEM\_MOQ\_UNIT\_TYPE`, `PC\_ITEM\_MIN\_ORDER\_QUANTITY`, `ITEM\_QLTY\_SCORE`, `MCAT\_NAME\_LIST`, `PCAT\_NAME`, `PC\_ITEM\_MODBYUSRDATE\_FORMATED`, `PC\_ITEM\_FOB\_PRICE\_ABSURD\_FLAG`, `PC\_ITEM\_REJECTION\_CODE/REASON`. **Never** copy image URLs, PDF/video links or internal ids into the file. There is no currency field, so don't invent one.

Cache each successful response per GLID (`data/gc\_cache/`, `data/catalog\_cache/`). The cache is the fallback when a later call fails.

\---

## 2\. Read the CSV dump for this GLID

Folder: `Global Context - Seller Dataset/` (1 Apr – 2 Oct 2026, one row per event). Read **only this GLID's rows**, using the byte-offset index (`data/csv\_index.pkl`, built once in about 1.5s and rebuilt automatically when a CSV changes). Never scan the whole files per request.

|CSV|GLID column(s)|Becomes|Feeds|
|-|-|-|-|
|gc\_seller\_profile|fk\_glusr\_usr\_id|`seller\_profile` (state)|snapshot, KYC flags, Handle with care (do\_not\_call\_requested, showed\_frustration, asked\_if\_talking\_to\_bot, already\_in\_touch\_with\_executive, past\_objections, past\_questions\_asked), VANI history|
|gc\_enquiries\_received|seller\_glid, buyer\_glid|`enquiry` (buyer → seller)|seller leads; buyer's enquiries sent|
|gc\_enquiry\_messages|seller\_glid|`enquiry\_message`|reply rate (any seller message in the thread = replied)|
|gc\_buyer\_calls\_received|seller\_glid, buyer\_glid|`pns\_call`|buyer calls: connected %, talk time, missed|
|gc\_buyleads\_bought|seller\_glid|`buylead\_bought`|buy-lead usage and keywords (keyword text before `\_p`)|
|gc\_whatsapp\_messages|glid|`wa\_message`|WhatsApp engagement and read rate|
|gc\_whatsapp\_chatbot\_conversations|glid|`wa\_chat`|`Msite\_BL\*` / buy intents go to **buyer** (requirements posted); the rest to seller threads|
|gc\_buyer\_call\_extractions|glid|`call\_extraction`|`seller\_role\_on\_call=BUYER` goes to buyer (products, specs, prices); SELLER gives stock and price facts|
|gc\_bot\_calls / gc\_bot\_call\_turns|fk\_glusr\_usr\_id|`vani\_call` / `vani\_turns`|past VANI calls (disposition, summary), language detection|
|gc\_executive\_calls|fk\_glusr\_usr\_id|`exec\_call`|executive touchpoints|

Dataset timestamps are IST wall-clock; convert them to UTC. Messages contain real names and must be scrubbed (§5).

**Lookback windows** (the event's own timestamp vs now):

|Source|Window|Why|
|-|-|-|
|enquiries, enquiry messages, buyer calls|90d|lead lifecycle; matches the API's 90d counters|
|buy-leads bought|45d|the warehouse keeps about 45d|
|VANI calls and transcripts|180d|sparse (about 2 per seller in 6 months); never repeat a pitch|
|WhatsApp chatbot, executive calls|60d|resumable threads, relationship context|
|call extractions|90d|specs and prices stay relevant for a quote cycle|
|WhatsApp delivery, buyer activity (searches)|30d|engagement and intent decay fast|
|bot conversation write-backs|30d|resumable conversation threads|
|profile, KYC, account, tickets, catalogue|latest|state, not activity|

## 3\. Add live events not in the CSV

Include events from the event store whose source is **not** `dataset.\*`: the bot's own end-of-conversation write-backs (`conversation`: summary, open\_items, resolved\_items, facts, intents) and activity POSTed after the export. Write-backs are role-scoped: a buyer's conversation never feeds a seller's file.

## 4\. Merge: live data wins

Resolve every field both sources can provide in priority order. The first source with a value wins:

|Field|Priority|
|-|-|
|products listed, products without price / photo, CQS (non-zero), categories|**catalog API > GC API > CSV**|
|company, city, first name, account type (Paid/Free), service, listing status, email verified, business type|**GC API > CSV**|
|enquiries / buyer calls in 30d / 90d (counters)|**GC API** (live). CSV rows provide the detail lines and reply rate, labelled "history"|
|everything only one source has|that source|

* When a lower-priority source has a **different** value, record it: `conflicts\_resolved: \[products\_listed: catalog=40 over api=1; account\_type: api=Paid over dataset=Free]`.
* For each material fact included in the context file, record its source using `field\_sources` (and, where practical, a compact source tag beside the fact). Use exact labels: `CATALOG\_API`, `GLOBAL\_CONTEXT\_API`, `CSV`, `EVENT\_WRITEBACK`, `DOMAIN\_KNOWLEDGE`, or `DERIVED`. If a value is merged, use the source that won the merge; if derived, name the input sources briefly. Do not claim a source was checked unless it actually was.
* **Known facts:** newest value wins. If a value changed, keep the old one visible as `(was X; updated <date>)`.
* Different products bought on different calls are *not* conflicts. Use only the latest sourcing call for buyer facts.

## 5\. Render the file (fixed sections, fixed order)

Front matter first, then `## ` sections in this exact order. An empty section is written as `- none`. Key/value lines use `- key: value`, and list rows use `|`.

```
---
schema: seller.v2 | buyer.v2
glid, role, generated\_at, freshness\_ms, build\_ms
sources: {events\_until, live\_api, catalog\_api}       ← when each source was last current

field\_sources: {field: CATALOG\_API|GLOBAL\_CONTEXT\_API|CSV|EVENT\_WRITEBACK|DOMAIN\_KNOWLEDGE|DERIVED}  ← source of each material context fact; use compact labels
pipeline: apis\_first+csv (gc=live|cached|failed, catalog=live|no catalogue|failed, csv\_rows=N, live=N)
lookback\_days: {…}
merge: {policy: catalog\_api > gc\_api > csv, fields: {catalog: n, api: n, dataset: n}}
conflicts\_resolved: \[...]                            ← top 3
cold\_start: true|false
degraded: \[gc\_api, catalog\_api, …]                   ← sources that failed this run
data: REAL (internal use only)
---
```

**seller.md**

1. `# Seller <GLID> — <Company>, <City> (contact: <FirstName>)`
2. **Snapshot:** status, language (and its source), account (Paid · service · plan · renewal · auto-debit), vintage and listing, business, KYC ✓ list, account manager first name.
3. **Handle with care:** DO-NOT-CALL; open service tickets; churn risk (auto-debit stopped or cancelled, high-churn); showed frustration; asked if talking to a bot; already with an executive; past objections and questions; complaints. *These become hard rules for the bot.*
4. **Open threads (resume these first):** unresolved bot write-backs → latest meaningful executive status or note (at least 4 words; skip codes like "Nr") → VANI "call later" / "meeting fixed" → unread enquiries older than 48h → catalogue issues from the products API (rejected with reason, missing price/photo/specs, price looks wrong). At most 4.
5. **Known facts (do not re-ask):** categories, location preference, products listed, stock and price quoted, write-back facts.
6. **Leads \& enquiries:** live received count (30d) plus history read/replied % and unread >48h; buy-leads; latest rows `date | product | Buyer FirstName, City | replied/read/unread`.
7. **Buyer calls:** received / connected %, average talk time, last call, missed in the last 7 days.
8. **Catalog \& market:** live product count, rejected, out of stock, hidden in directory; missing price/photo/specs/description, low score, price looks wrong, CQS; seller groups; 3 recently updated products with price/unit/MOQ; market size.
9. **Conversations (all channels):** bot, VANI, WhatsApp bot, executive. Newest first, with relative age.
10. **Engagement:** WhatsApp read rate, VANI answer history, executive calls answered, best time, level.

**buyer.md**

1. `# Buyer <GLID> — <FirstName|Company>, <City>`
2. Snapshot · 3. Open threads (latest requirement posted, last seller contacted, last sourcing call, write-backs) · 4. Known facts (specs and price from the latest sourcing call, write-backs) · 5. Requirements posted · 6. Searches \& browsing (categories ×count, recent keywords URL-decoded) · 7. Sellers contacted (named when the seller is known, otherwise a total by channel; never the buyer's own listing) · 8. Sourcing calls · 9. Conversations · 10. Engagement.

**Formatting rules: add relative ages ("yesterday", "3d ago") so the bot never does date arithmetic. Use IST dates. Clip long text with "…". Never use internal codes as the only explanation where a plain label exists (say "auto-debit", not NACH). Preserve source attribution for material facts using the compact `field\_sources` metadata; never present inferred or historical data as a verified live fact.**

## 6\. Enforce size, then write atomically

* The whole file must be **≤ 3,000 characters**, about 750–850 tokens. If it's over, re-render with the next tighter layout: fewer rows, shorter clips, catalogue detail lines dropped first. Repeat until it fits.
* Write to `<file>.md.tmp`, then rename over the old file, so readers never see a half-written file.
* Log `{glid, role, chars, build\_ms, freshness\_ms}` to `data/freshness.jsonl`.

## 7\. Privacy checklist (must pass before writing)

* \[ ] No phone numbers, emails, addresses, GSTIN/PAN/Aadhaar or bank numbers. Free text is scrubbed, and fact keys like `phone`, `email`, `gst\_number` and `account` are dropped.
* \[ ] People appear by **first name only**. KYC appears as ✓ flags, never as document numbers.
* \[ ] In `seller.md`, a buyer appears only as "FirstName, City | product | status": never the buyer's budget, other enquiries or conversations.
* \[ ] No image, PDF or video URLs, internal ids, or raw API payloads.
* \[ ] Material customer facts have compact source attribution in `field\_sources`; definitions sourced from the IndiaMART knowledge document are labelled `DOMAIN\_KNOWLEDGE`. Do not expose internal source labels to customers unless specifically useful and approved.
* \[ ] Raw API responses stay in `data/\*\_cache/` (gitignored) and never reach a `.md`.

## 8\. Failure handling

|Situation|Do this|File shows|
|-|-|-|
|GC token expired or API down or slow|use the last GC snapshot, or CSV only|`degraded: \[gc\_api]`, `pipeline: … gc=failed`|
|`getContext` says Mapping Not Found|regenerate the mapping\_id once and retry|normal|
|Catalogue API 204|no catalogue (valid)|`catalog=no catalogue`|
|Catalogue API error or timeout|last catalogue snapshot, or GC/CSV catalogue fields|`degraded: \[catalog\_api]`|
|CSV index missing or stale|rebuild it automatically (about 1.5s)|normal|
|GLID unknown everywhere|cold-start file; the bot uses a neutral greeting|`cold\_start: true`|

## 9\. Freshness

* **Before every conversation**, run the full pipeline (APIs → CSV → merge → render). Measured at 0.4–1.1s, almost all of it API time; CSV read 18–150ms, render 1–7ms.
* **New activity** (`POST /api/events`) rebuilds only the affected files, in about 80ms.
* **Every 15 minutes**, rebuild all files from stored data (about 6s for 8k files) so windows and relative ages stay correct.
* **After every conversation**, the write-back is saved as an event, the file is rebuilt, and the next channel resumes from it.

## 10\. How the bot uses the result

The pipeline builds the context; the bot never calls these APIs itself. For each turn, the bot receives:

1. the caller's file (`seller.md` **or** `buyer.md`, in full),
2. matching sections of `contexts/indiamart\_domain\_knowledge.md` (a core set plus intent-matched sections, ≤7,600 chars),
3. its conversation rules ("Handle with care" as hard instructions, never re-ask Known facts, privacy, end the call when asked).
4. IndiaMART terminology and domain knowledge
5. Use `contexts/indiamart\_domain\_knowledge.md` (the IndiaMART knowledge document) as the authoritative reference for IndiaMART-specific keywords, acronyms, product names, process definitions, service terminology, and business rules whenever a term or definition is unclear. Search the relevant section before answering or interpreting the term. Prefer the knowledge document over guessing from general-world meanings. If the document does not define the term, say that you cannot verify the specific meaning yet and continue with an authorised retrieval or human-help path; do not invent a definition. Keep domain knowledge distinct from customer-specific context: label `DOMAIN\_KNOWLEDGE` as the source for definitions and `GLOBAL\_CONTEXT\_API`, `CATALOG\_API`, `CSV`, or `EVENT\_WRITEBACK` for customer facts.

## 11\. Runtime voice actions: answer, transfer, callback, or meeting

This section governs how the voice bot acts on the context file. It does not change the context-building pipeline. The voice runtime must use only configured, authorised tools for transfers and request creation.

1. Natural conversation and name use: if the customer name is known and appropriate, use it once in the opening greeting. Do not repeat the name in every turn or sentence. Use it again only when it sounds natural and helps with clarity, reassurance, disambiguation, or a sensitive handoff. Never force a name into routine responses.
2. Primary objective: resolve the customer's concern during the current call whenever reasonably possible. Callback and meeting requests are fallback options, not the default outcome. Do not prematurely transfer or offer follow-up when the bot can safely answer or complete the request in-call.
3. Decision order for every request:
4. Understand the concern and check the caller's context plus the relevant `contexts/indiamart\_domain\_knowledge.md` sections for IndiaMART terminology, policies and processes.
5. Answer or complete the request during this call when supported by authoritative information and authorised tools. Explain the next step clearly and verify whether it resolved the concern.
6. Ask one focused clarification question if intent or a required detail is unclear; do not re-ask details already reliably available in context.
7. If a fact or action is missing, make a reasonable authorised retrieval/action attempt. Do not mention internal technical issues or describe API/tool failures to the customer. Use neutral wording about what can or cannot currently be verified.
8. If still unresolved, offer a live executive transfer when appropriate and available, with the caller's consent. Explain why escalation may help.
9. Offer a callback or meeting only if live resolution and suitable transfer are unavailable, unsuccessful, inappropriate, or the customer prefers follow-up. Callback/meeting is a fallback, not the first response.
10. If the caller declines the available options, state the verified next step and end politely without repeatedly pushing.

Escalate instead of guessing when:

* The required fact is missing from the context and cannot be retrieved from an authorised source.
* Sources conflict and the conflict cannot be resolved using the source-priority and freshness rules.
* The question requires an exception, commercial commitment, negotiation, discretionary decision, or policy interpretation not explicitly approved for the bot.
* The caller disputes a recorded status, raises a serious complaint, reports suspected fraud/account compromise, or requests a human.
* An action fails, its status is ambiguous, or the bot cannot verify completion.
* The caller is frustrated or repeatedly says the bot is not helping. Acknowledge this and offer human assistance without forcing the caller through repeated troubleshooting.

Executive working hours:

* Treat 09:00–19:00 India Standard Time (IST) as the proposed executive-transfer and meeting-handling window, subject to the production configuration.
* Check the configured working calendar, holidays, queue availability and actual agent availability; time of day alone does not prove an executive is available.
* Within working hours: attempt a live transfer only after the caller agrees and the transfer system confirms an eligible destination.
* Outside working hours, on a holiday, or when the queue has no available executive: do not attempt a normal live transfer. Offer a callback request or meeting request for a configured eligible slot.
* Never promise that an executive will call at a particular time unless the scheduling system confirms that slot and creates the request.
* If the caller asks for an exact time that is unavailable, offer the next available configured slot or capture a preferred time as a preference, clearly stating that it is not yet confirmed.

Live transfer procedure:

1. Briefly explain why a human executive may be better placed to help and ask whether the caller would like to be connected now.
2. Before transfer, prepare a concise handoff summary: resolved caller role, stated intent, relevant verified facts, actions already attempted, unresolved question, caller preference and any open thread. Include only information authorised for the receiving team.
3. Invoke the authorised transfer tool/queue. Do not expose internal GLIDs, API errors, raw context, or internal notes to the caller.
4. Treat the transfer as successful only when the transfer system confirms connection/acceptance. A transfer attempt is not a completed transfer.
5. If transfer fails, the queue rejects it, or no eligible executive is available, apologise briefly and offer a callback or meeting request. Do not loop or retry indefinitely.
6. If the caller does not consent to transfer, do not transfer them; offer the alternatives.

Callback request procedure:

1. Confirm that the caller wants a callback and identify the reason in their own words.
2. Resolve the caller identity through the approved process. Do not assume the incoming phone number uniquely identifies an account.
3. Collect only fields required by the callback workflow: caller/account reference already resolved by the system, reason, preferred callback date/time or time window, language/channel preference if supported, and any concise context needed by the executive.
4. Use the approved callback-request tool. If a required field is missing, ask only for that field.
5. Confirm the request only after the tool returns success and a request/reference ID or confirmed status. State the confirmed callback window if one is returned. If the tool only records a preference, explicitly say the time is a preference and not a confirmed appointment.
6. If request creation fails, do not claim it was raised. Apologise, explain that the request could not be submitted, and follow the configured fallback (retry once if safe, transfer if available, or provide an approved support route).

Meeting request procedure:

1. Establish the purpose of the meeting and whether the caller specifically wants a meeting rather than a callback.
2. Capture the preferred date/time window, topic, language/channel preference if supported, and any minimum required details.
3. Check the configured meeting calendar/availability before offering a confirmed slot.
4. Create the request through the authorised scheduling tool.
5. Say a meeting is confirmed only if the scheduling tool confirms the slot and successful creation. Otherwise describe it as a meeting request or preferred slot awaiting confirmation.
6. If no calendar integration exists, record a request for scheduling only if an approved request-creation workflow exists. Do not imply that a meeting has been booked.

Voice wording examples:

* Missing/out-of-context information: "I don't have a verified answer to that right now. I can try to connect you with an executive, or arrange a callback. Which would you prefer?"
* Data cannot be retrieved: Do not say or imply "we are having a technical issue fetching your details", "the system is down", or similar internal-system explanations. Use a calm, customer-centred explanation such as: "I'm unable to verify that information right now. I can connect you with an executive or arrange a callback. Which would work better for you?" Only mention a service disruption if an approved customer-facing message explicitly authorises it and the status is verified.
* Transfer unavailable after 7 PM IST: "Our executive team is outside its usual working hours right now. I can help arrange a callback or a meeting request instead."
* Ask for callback time: "What date and time would be convenient for our team to call you back?"
* Confirm callback preference before submitting: "Just to confirm, you'd prefer a callback on \[date] at \[time/time window]. Is that correct?"
* Callback successfully scheduled for a confirmed slot: "Your callback is scheduled for \[confirmed date and time]."
* Preferred time recorded but not confirmed: "I've recorded your preferred callback time as \[date/time]. The team will need to confirm the actual slot."
* Tool failure: "I couldn't complete that request just now, so I don't want to tell you it has been booked. Would you like me to try the available alternative?"
* Before ending any call: "Is there anything else I can help you with today?" If the caller raises another need, address it or follow the escalation flow before closing. If not, summarise the agreed next step and close politely.

Hard guardrails:

* Never fabricate answers, executive availability, callback commitments, meeting slots, ticket numbers, or successful actions.
* Never say "transferred", "callback booked", "meeting fixed", or "request raised" without a positive tool result for that specific action.
* Never expose one buyer's private details, requirements, communications or contact data to a seller, or vice versa, unless an approved policy explicitly permits it.
* Never read internal notes, internal identifiers, raw API errors, confidence scores or private context-file content aloud. Never tell the customer "we are having a technical issue fetching your details", "the API is down", or similar internal-system explanations. If a retrieval attempt does not provide an answer, say neutrally that you cannot verify that specific information right now, then continue trying an authorised route or resolve what you can in the current call.
* Respect "do not call" preferences and any applicable contact restrictions. Do not initiate an outbound callback or meeting communication when the context or authoritative system indicates contact is prohibited. If the caller is currently calling inbound and requests follow-up, apply the approved policy for recording that request rather than assuming the preference can be overridden.
* Ask for confirmation before submitting a callback or meeting request, and before transferring the call.
* Do not ask for passwords, OTPs, full payment-card details or unnecessary sensitive information.
* If the caller asks to stop or end the conversation, comply promptly.
* Before ending a call, always ask whether the caller needs any further help, unless the caller has explicitly asked to end immediately or an urgent safety/operational condition requires immediate closure. If the caller has no further need, briefly recap the verified outcome and agreed next step before saying goodbye.
* Do not create duplicate callback/meeting requests on repeated tool calls. Check for an existing open request when the workflow supports it.
* Preserve the unresolved intent and agreed next step in the end-of-conversation write-back so the next channel can resume accurately.

Required write-back after transfer, callback or meeting flow:

* intent and short summary;
* verified facts used and relevant source/freshness caveat;
* unresolved question or reason for escalation;
* action attempted and final tool outcome (success/failure/not attempted);
* request/booking reference and confirmed slot only when returned by the tool;
* caller's stated preference and consent;
* next step and relative/date-time context in IST.
Do not write credentials, raw API responses, unnecessary personal data, or another party's confidential information into the context file.

\---

12. Production configuration and open decisions
The following values must be supplied by the product/operations owner or the live workflow configuration; this skill must not invent them:
* Executive operating calendar: confirm whether 09:00–19:00 IST applies every day, and define weekly offs, public holidays, regional calendars and any special-day exceptions.
* Transfer eligibility: queues/teams to use by buyer vs seller, issue type, language, paid/free account if relevant, priority and escalation severity.
* Availability source: the authoritative real-time signal for agent presence, queue capacity and successful connection; define transfer timeout and maximum safe retry count.
* Callback SLA: eligible windows, maximum lead time, cutoff rules, after-hours handling, duplicate detection, cancellation/rescheduling and escalation for overdue callbacks.
* Meeting rules: which roles/issues qualify, calendar source, slot duration, buffer times, booking horizon, timezone, confirmation and cancellation/rescheduling policy.
* Required request fields: minimum fields for callback/meeting creation, caller identity/verification requirements and what to do when identity is unresolved.
* Consent and contact policy: how consent is recorded, how DO-NOT-CALL preferences interact with an inbound caller's explicit callback request, and which outbound channels are permitted.
* Fallback route: approved help/support route when transfer and request-creation tools are unavailable.
* Urgent/sensitive issues: routing and handling rules for fraud, account compromise, threats, legal matters, serious complaints and other high-priority cases.
* Language and accessibility: supported languages, interpreter/agent routing, and handling when the caller's preferred language is unavailable.
* Monitoring: logs/metrics for transfer offered/accepted/failed, callback/meeting created, tool errors, duplicate requests, after-hours requests and unresolved intents. Keep logs privacy-minimised.
* Ownership: named operational owner and review cadence for the above policies.

Do not treat these configuration items as implemented merely because they are documented here. Until the corresponding tools and policies exist, the bot may explain the available options but must not claim it can execute them.



\---

## Reference implementation (this repo)

|Step|Code|
|-|-|
|Orchestrator|`context\_layer/pipeline.py` → `run(glid, role)` / `prewarm()`|
|GC API (two-step, mapping reuse)|`context\_layer/gc\_api.py`|
|Products-listing API|`context\_layer/catalog\_api.py`|
|CSV converters and per-GLID reader|`context\_layer/dataset.py`, `context\_layer/csv\_index.py`|
|Merge and conflicts|`context\_layer/merge.py`|
|Render (sections)|`context\_layer/render.py`|
|Size cap, front matter, atomic write|`context\_layer/builder.py`|
|Endpoint|`GET /api/context/runtime/<glid>?role=seller\|buyer` returns the file, per-step timings, conflicts and field sources|

**Verify a build:**

```bash
curl "localhost:8000/api/context/runtime/209139024?role=seller"
#  → "api":"live", "catalog\_api":"live", timings{apis\_ms, csv\_ms, merge\_build\_ms, total\_ms},
#    conflicts\_resolved:\[{field:"products\_listed", used:"catalog=40", overridden:"api=1"}, …]
```

