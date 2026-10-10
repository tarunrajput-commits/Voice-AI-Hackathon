---
schema: seller.v2
glid: "42559301"
role: seller
generated_at: 2026-10-10T11:55:47.425Z
freshness_ms: 3.6
build_ms: 1.2
sources: {events_until: 2026-10-10, live_api: 2026-10-10T06:44:35.358Z, catalog_api: 2026-10-10T06:18:06.568Z}
pipeline: apis_first+csv (gc=cached, catalog=cached, csv_rows=145, live=1)
lookback_days: {enquiries: 90, pns_calls: 90, buyleads: 45, wa_chat: 60, vani_calls: 180, exec_calls: 60, whatsapp: 30, conversations: 30}
merge: {policy: catalog_api > gc_api > csv, fields: {catalog: 4, api: 8, dataset: 0}}
conflicts_resolved: [products_without_price: catalog=21 over api=18; cq_score: api=25 over dataset=23.0]
cold_start: false
degraded: []
data: REAL (internal use only)
---
# Seller 42559301 — Fairy Zari, Surat (contact: Jariwala)

## Snapshot
- status: active
- language: hi-IN (default)
- account: Free
- on_indiamart: 9 Y 4 M · listing LST
- business: Proprietor · Manufacturer · 0 - 40 L
- kyc: mobile ✓, email ✓, GST ✓, PAN ✓
- account_manager: Chimurkar

## Handle with care
- showed frustration on past VANI calls: apologise once, be brief, offer an executive
- past objections: Existing Engagement / Past Experience (1); Information / Trust / Privacy Concerns (1)
- past questions: Pricing Payment (3); Problem Complaint (3); Benefit Value (2)

## Open threads (resume these first)
- [executive 2026-09-28, 12d ago] Talk with the client will self contact when needed
- [system] 1 enquiries unread >48h (latest: Dapka Zari Thread)
- [catalog] products with no price: 21, no photo: 4, no specifications: 33

## Known facts (do not re-ask)
- gst_registered_since: 2025
- products_listed: 39
- location_preference: Local
- categories: Dapka Zari Thread, Gold Zari Thread, Imitation Zari

## Leads & enquiries (90d) — date | product | buyer | status
- received: 25 (30d: 5) (live) | history n=8: read 88%, replied 25% | unread>48h: 1
- 2026-09-16 | Nakshi Dapka Zari | Deepak, Surat | read
- 2026-09-11 | Dapka Zari Thread | Nahid, Surat | unread

## Buyer calls (90d)
- received: 17 | connected: 8 (47%) | avg_talk: 2.1m | live received_90d: 17, picked_4w: 5/13
- last: 2026-10-01 (9d ago) connected 3.1m from UP East

## Catalog & market
- top_categories: Dapka Zari Thread, Zari Thread, Plastic Thread (parent: Zari Thread)
- products: 39 live | rejected 0 | out of stock 0 | hidden in directory 2
- missing: price 21, photo 4, specs 33, description 37 | low score 36 | price looks wrong 0 | CQS 25
- groups: Zari Thread 18, Imitation Zari 7, Dapka Zari Threads 5, New Items 3
- recently updated: Jari (no price); Jari Latkan (no price); Zari Thread (no price)
- market (top categories, 4w): 183 buy-leads, 101 paid sellers, local 36

## Conversations (all channels, latest 3)
- 2026-06-07 (125d ago) vani call: General (talked): The agent from IndiaMART called the lead to reconnect regarding their previous ca…

## Engagement
- vani_history: answered 1/5 | avg 180s
- best_time: morning
- level: medium
