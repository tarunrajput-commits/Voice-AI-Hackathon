---
schema: seller.v2
glid: "239368219"
role: seller
generated_at: 2026-10-10T11:55:47.421Z
freshness_ms: 18.2
build_ms: 4.9
sources: {events_until: 2026-10-10, live_api: 2026-10-10T06:18:05.929Z, catalog_api: 2026-10-10T06:18:06.019Z}
pipeline: apis_first+csv (gc=cached, catalog=cached, csv_rows=1003, live=3)
lookback_days: {enquiries: 90, pns_calls: 90, buyleads: 45, wa_chat: 60, vani_calls: 180, exec_calls: 60, whatsapp: 30, conversations: 30}
merge: {policy: catalog_api > gc_api > csv, fields: {catalog: 4, api: 9, dataset: 0}}
conflicts_resolved: [account_type: api=Paid over dataset=Free; products_listed: catalog=52 over api=30; products_without_price: catalog=21 over api=0]
cold_start: false
degraded: []
data: REAL (internal use only)
---
# Seller 239368219 — Siddhi Enterprises, Gwalior (contact: Mukesh)

## Snapshot
- status: active
- language: hi-IN (last conversation)
- account: Paid · MDC Pro · Monthly · auto-debit: Stopped - Deal Cancelled
- on_indiamart: 1 Y 8 M · listing TFL
- business: Proprietor · Trader - Retailer · 0 - 40 L
- kyc: mobile ✓, email ✓, GST ✓, PAN ✓, address ✓
- account_manager: Tanisha

## Handle with care
- churn risk: auto-debit Stopped - Deal Cancelled
- already in touch with an executive (Tanisha): don't re-pitch

## Open threads (resume these first)
- [meeting requested 2026-10-10, today] Discuss lead generation conce… (not confirmed, ref MT-DE3770)
- [voice 2026-10-10, today] Bot to schedule a meeting with Tanisha for lead generation.
- [voice 2026-10-10, today] Mukesh to decide on preferred meeting time.

## Known facts (do not re-ask)
- lead_preference: facing lead generation issues
- gst_registered_since: 2025
- products_listed: 52
- categories: Bella Vita Perfume, Crystal Ball Night Lamp, Flask Gift Sets

## Leads & enquiries (90d) — date | product | buyer | status
- received: 203 (30d: 81) (live) | history n=46: read 100%, replied 41% | unread>48h: 0
- buyleads_bought_45d: 65 (credits 14200) | top: Crystal Ball Night Lamp, vacuum flask set
- 2026-09-29 | Vintage T9 Hair Trimmer | Anil, Chhibramau | read

## Buyer calls (90d)
- received: 44 | connected: 34 (77%) | avg_talk: 2.1m | live received_90d: 53, picked_4w: 25/30
- last: 2026-09-29 (11d ago) connected 1.0m from UP East

## Catalog & market
- top_categories: Garbage and Waste Bags, Electric Kettle, Men Leather Belt (parent: Perfumes)
- products: 52 live | rejected 0 | out of stock 10 | hidden in directory 1
- missing: price 21, photo 21, specs 21, description 44 | low score 21 | price looks wrong 0
- market (top categories, 4w): 824 buy-leads, 8 paid sellers, local 40

## Conversations (all channels, latest 1)
- 2026-10-10 (today) voice: Mukesh confirmed lead generation issues and asked to schedule a meeti…

## Engagement
- whatsapp_30d: 137 msgs (27 from seller) | read_rate: 82% | last: 2026-10-01
- vani_history: answered 1/1 | avg 39s | already_in_touch_with_im (1)
- best_time: afternoon
- level: high
