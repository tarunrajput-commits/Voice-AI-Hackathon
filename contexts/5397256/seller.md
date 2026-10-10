---
schema: seller.v2
glid: "5397256"
role: seller
generated_at: 2026-10-10T11:55:47.441Z
freshness_ms: 12.2
build_ms: 1.3
sources: {events_until: 2026-10-09, live_api: 2026-10-10T06:18:07.578Z, catalog_api: 2026-10-10T06:18:07.871Z}
pipeline: apis_first+csv (gc=cached, catalog=cached, csv_rows=718, live=3)
lookback_days: {enquiries: 90, pns_calls: 90, buyleads: 45, wa_chat: 60, vani_calls: 180, exec_calls: 60, whatsapp: 30, conversations: 30}
merge: {policy: catalog_api > gc_api > csv, fields: {catalog: 4, api: 9, dataset: 0}}
conflicts_resolved: [account_type: api=Paid over dataset=Free; products_without_price: catalog=0 over api=3]
cold_start: false
degraded: []
data: REAL (internal use only)
---
# Seller 5397256 — MS Enterprises India, Mumbai (contact: Arif)

## Snapshot
- status: active
- language: hi-IN (call extractions)
- account: Paid · MDC. · Annual
- on_indiamart: 14 Y 3 M · listing LST
- business: Proprietor · Manufacturer · 0 - 40 L
- kyc: mobile ✓, email ✓, GST ✓, PAN ✓
- account_manager: Shubham

## Handle with care
- complaints 90d: negative feedback 0, irate 1

## Open threads (resume these first)
- [system] 1 enquiries unread >48h (latest: 12cm Miswak Stick)

## Known facts (do not re-ask)
- price_quoted: 112 / piece; 72 / piece (SF-400; Gas Lighter; Temperat…)
- stock_status: in stock; out of stock (SF-400; Gas Lighter; Temperat…) (was in stock (150 Piece Color Set); updated 2026-09-19)
- gst_registered_since: 2026
- products_listed: 32
- location_preference: Local
- categories: Backpack Cover, Digital Kitchen Scale, Miswak Stick

## Leads & enquiries (90d) — date | product | buyer | status
- received: 298 (30d: 73) (live) | history n=108: read 99%, replied 67% | unread>48h: 1
- buyleads_bought_45d: 57 (credits 17800) | top: sf400 weighing scale, Kitchen Weighing Scale
- 2026-10-01 | 12cm Miswak Stick | Sunny, Thrissur | unread
- 2026-10-01 | Silicone Water Bottle | Panvel | replied
- 2026-09-30 | Miswak Stick Holder | Abduomar, Kozhikode | replied
- 2026-09-29 | Silicone Water Bottle | Thane | read

## Buyer calls (90d)
- received: 87 | connected: 65 (75%) | avg_talk: 2.4m | live received_90d: 94, picked_4w: 26/38
- last: 2026-10-01 (9d ago) connected 3.0m from 

## Catalog & market
- top_categories: Hot Water Bags, DIY Art Set, Stainless Steel Kitchenware (parent: Backpacks)
- products: 32 live | rejected 0 | out of stock 16 | hidden in directory 2
- missing: price 0, photo 0, specs 0, description 0 | low score 0 | price looks wrong 0 | CQS 49
- groups: Water Bottle 3, New Items 3, Miswak Sticks 2, Cleaning Cloth 2
- recently updated: 40 Oz Stainless Steel Vacuum In… ₹300/Piece MOQ 40; Miswak Stick Holder ₹16/Piece MOQ 1000; Stainless Steel Garlic Press ₹110/Piece MOQ 50
- market (top categories, 4w): 1096 buy-leads, 542 paid sellers, local 162

## Conversations (all channels, latest 4)
- none

## Engagement
- vani_history: answered 1/1 | avg 138s
- executive_calls_60d: answered 2/5
- best_time: afternoon
- level: high
