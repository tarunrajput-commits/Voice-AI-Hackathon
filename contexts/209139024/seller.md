---
schema: seller.v2
glid: "209139024"
role: seller
generated_at: 2026-10-10T11:55:47.403Z
freshness_ms: 11.8
build_ms: 3.5
sources: {events_until: 2026-10-10, live_api: 2026-10-10T06:19:48.604Z, catalog_api: 2026-10-10T06:19:48.858Z}
pipeline: apis_first+csv (gc=cached, catalog=cached, csv_rows=557, live=9)
lookback_days: {enquiries: 90, pns_calls: 90, buyleads: 45, wa_chat: 60, vani_calls: 180, exec_calls: 60, whatsapp: 30, conversations: 30}
merge: {policy: catalog_api > gc_api > csv, fields: {catalog: 4, api: 9, dataset: 0}}
conflicts_resolved: [account_type: api=Paid over dataset=Free; products_listed: catalog=40 over api=1; products_without_price: catalog=0 over api=4]
cold_start: false
degraded: []
data: REAL (internal use only)
---
# Seller 209139024 — Shreeva Enterprises, Jaipur (contact: Anil)

## Snapshot
- status: active
- language: hi-IN (last conversation)
- account: Paid · TS Pro · Annual
- on_indiamart: 2 Y 9 M · listing TFL
- business: Proprietor · Trader - Retailer
- kyc: mobile ✓, email ✓, GST ✓, PAN ✓
- account_manager: Jyotsna

## Handle with care
- none

## Open threads (resume these first)
- [callback requested 2026-10-10, today] Seller wants to discuss missi… — preferred 2 to 3 PM today (not confirmed, ref CB-5264CC)
- [voice 2026-10-10, today] Anil to check IndiaMART app settings for voice options.
- [voice 2026-10-10, today] Transfer the call to an executive immediately.

## Known facts (do not re-ask)
- stock_status: in stock (was in stock (Door Guard (Heavy Quality); D…); updated 2026-10-10)
- location_preference: Local
- products_listed: 1 (was 40; updated 2026-10-10)
- preferred_call_time: 2 to 3 PM today
- price_quoted: 11 / piece; 13 / piece (was 11 / piece; 13 / piece (Door Guard (Heavy Quality); D…); updated 2026-10-10)

## Leads & enquiries (90d) — date | product | buyer | status
- received: 126 (30d: 100) (live) | history n=29: read 100%, replied 45% | unread>48h: 0
- buyleads_bought_45d: 57 (credits 11400) | top: Door Guards, Door Guard
- 2026-09-30 | Aluminium Door Seals | Jaipur | replied

## Buyer calls (90d)
- received: 22 | connected: 17 (77%) | avg_talk: 2.6m | live received_90d: 24, picked_4w: 10/14
- last: 2026-09-30 (10d ago) connected 8.4m from UP East

## Catalog & market
- top_categories: Door Seals, Drop Down Door Seal, PVC Strip Curtains (parent: Seals)
- products: 40 live | rejected 0 | out of stock 0 | hidden in directory 23
- missing: price 0, photo 0, specs 19, description 0 | low score 11 | price looks wrong 1 | CQS 28
- market (top categories, 4w): 262 buy-leads, 81 paid sellers, local 78

## Conversations (all channels, latest 1)
- 2026-10-10 (today) voice: Anil became upset during the call, prompting the bot to offer an exec…

## Engagement
- whatsapp_30d: 16 msgs (1 from seller) | read_rate: 100% | last: 2026-09-17
- vani_history: answered 3/4 | avg 24s | call_dropped (2); not_interested (1)
- executive_calls_60d: answered 9/22
- best_time: afternoon
- level: high
