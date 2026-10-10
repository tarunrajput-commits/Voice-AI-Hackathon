---
schema: seller.v2
glid: "83127677"
role: seller
generated_at: 2026-10-10T11:55:47.446Z
freshness_ms: 4.7
build_ms: 1.8
sources: {events_until: 2026-10-10, live_api: 2026-10-10T06:59:23.459Z, catalog_api: 2026-10-10T06:18:08.312Z}
pipeline: apis_first+csv (gc=cached, catalog=cached, csv_rows=150, live=2)
lookback_days: {enquiries: 90, pns_calls: 90, buyleads: 45, wa_chat: 60, vani_calls: 180, exec_calls: 60, whatsapp: 30, conversations: 30}
merge: {policy: catalog_api > gc_api > csv, fields: {catalog: 4, api: 8, dataset: 0}}
conflicts_resolved: [products_listed: catalog=36 over api=35; products_listed: catalog=36 over dataset=57; products_without_price: catalog=20 over api=19]
cold_start: false
degraded: []
data: REAL (internal use only)
---
# Seller 83127677 — Atif Communication, Kolkata (contact: Md.)

## Snapshot
- status: active
- language: hi-IN (last conversation)
- account: Free
- on_indiamart: 7 Y 6 M · listing LST
- business: Proprietor
- kyc: mobile ✓, email ✓, GST ✓, PAN ✓
- account_manager: Shashi

## Handle with care
- none

## Open threads (resume these first)
- [voice 2026-10-10, today] Md. must check the six pending BoAt Bassheads enquiries.
- [voice 2026-10-10, today] Md. needs to address the 6 unread enquiries.
- [executive 2026-09-28, 12d ago] Need to follow up with the client for GST issue...

## Known facts (do not re-ask)
- products_listed: 36
- location_preference: Local
- categories: Babywear Set, Bluetooth Headset, Bluetooth Speaker

## Leads & enquiries (90d) — date | product | buyer | status
- received: 58 (30d: 20) (live) | history n=50: read 88%, replied 34% | unread>48h: 6
- 2026-09-26 | Nothing Neck Band | Bokaro Steel City | read
- 2026-09-26 | CMF BY NOTHING NECK BAND | Nitin, Bokaro Steel City | read

## Buyer calls (90d)
- received: 5 | connected: 2 (40%) | avg_talk: 0.8m | live received_90d: 6, picked_4w: 1/3
- last: 2026-09-26 (14d ago) not connected 1.9m from Bihar and Jharkhand

## Catalog & market
- top_categories: OTG Cable, Winter Wear, Mobile Phone Charger (parent: Baby Garment)
- products: 36 live | rejected 3 | out of stock 18 | hidden in directory 4
- missing: price 20, photo 4, specs 17, description 21 | low score 26 | price looks wrong 0 | CQS 35
- market (top categories, 4w): 414 buy-leads, 12 paid sellers, local 25

## Conversations (all channels, latest 2)
- 2026-10-10 (today) voice: Md. was reminded about six unread BoAt Bassheads headset enquiries and asked to…
- 2026-08-12 (59d ago) vani call: Call Later / Busy: The agent called the lead from IndiaMART. The lead asked the…

## Engagement
- vani_history: answered 2/5 | avg 45s | callback_requested (2)
- best_time: afternoon
- level: high
