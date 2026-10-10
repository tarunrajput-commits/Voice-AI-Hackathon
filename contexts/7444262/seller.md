---
schema: seller.v2
glid: "7444262"
role: seller
generated_at: 2026-10-10T12:31:04.107Z
freshness_ms: 18.9
build_ms: 5.2
sources: {events_until: 2026-10-02, live_api: 2026-10-10T06:59:14.599Z, catalog_api: 2026-10-10T06:59:14.602Z}
pipeline: apis_first+csv (gc=cached, catalog=cached, csv_rows=612, live=0)
lookback_days: {enquiries: 90, pns_calls: 90, buyleads: 45, wa_chat: 60, vani_calls: 180, exec_calls: 60, whatsapp: 30, conversations: 30}
merge: {policy: catalog_api > gc_api > csv, fields: {catalog: 4, api: 8, dataset: 0}}
conflicts_resolved: [products_listed: catalog=49 over api=48; products_listed: catalog=49 over dataset=48; cq_score: api=55 over dataset=65.0]
cold_start: false
degraded: []
data: REAL (internal use only)
---
# Seller 7444262 — Wicks N More By Chandrani, Kolkata (contact: Sudarsan)

## Snapshot
- status: active
- language: hi-IN (VANI transcript)
- account: Free
- on_indiamart: 13 Y 5 M · listing LST
- business: Proprietor · Manufacturer · 0 - 40 L
- kyc: mobile ✓, email ✓, GST ✓, PAN ✓
- account_manager: Aman

## Handle with care
- DO-NOT-CALL requested: no outbound pitch; inbound help only, keep it short

## Open threads (resume these first)
- [executive 2026-10-08, 2d ago] Client did not responded to the call.
- [system] 61 enquiries unread >48h (latest: Meesho Poly Courier Bag 10 x 14 inch)

## Known facts (do not re-ask)
- gst_registered_since: 2025
- products_listed: 49
- location_preference: Local
- categories: Tamper Proof Courier Bags, Direct Thermal Labels, Jewelry Gift Box

## Leads & enquiries (90d) — date | product | buyer | status
- received: 293 (30d: 111) (live) | history n=153: read 60%, replied 35% | unread>48h: 61
- 2026-10-01 | Meesho Poly Courier Bag 10 x 14 inch | Anish, Rajarhat | unread
- 2026-10-01 | Meesho Poly Courier Bag 6 x 8 inch | Suraj, Patna | unread

## Buyer calls (90d)
- received: 103 | connected: 55 (53%) | avg_talk: 1.7m | live received_90d: 119, picked_4w: 21/53
- last: 2026-10-01 (9d ago) connected 0.8m from Kolkata

## Catalog & market
- top_categories: Tamper Proof Courier Bags, Printed Courier Bag, Pearl Earrings (parent: Packaging Envelopes)
- products: 49 live | rejected 0 | out of stock 0 | hidden in directory 1
- missing: price 0, photo 0, specs 0, description 8 | low score 9 | price looks wrong 0 | CQS 55
- market (top categories, 4w): 4343 buy-leads, 20 paid sellers, local 343

## Conversations (all channels, latest 2)
- 2026-09-06 (34d ago) whatsapp bot: call feedback, callback request
- 2026-08-10 (61d ago) vani call: General (talked): The agent initiated the call by asking if the lead was from '…

## Engagement
- vani_history: answered 11/11 | avg 28s | call_dropped (6); not_interested (1); do_not_call (1)
- best_time: afternoon
- level: high
