---
schema: seller.v2
glid: "47648617"
role: seller
generated_at: 2026-10-10T12:31:04.062Z
freshness_ms: 3.3
build_ms: 1.9
sources: {events_until: 2026-10-10, live_api: 2026-10-10T06:18:08.718Z, catalog_api: 2026-10-10T06:18:08.919Z}
pipeline: apis_first+csv (gc=cached, catalog=cached, csv_rows=25, live=2)
lookback_days: {enquiries: 90, pns_calls: 90, buyleads: 45, wa_chat: 60, vani_calls: 180, exec_calls: 60, whatsapp: 30, conversations: 30}
merge: {policy: catalog_api > gc_api > csv, fields: {catalog: 4, api: 8, dataset: 0}}
conflicts_resolved: [products_listed: catalog=7 over dataset=9; cq_score: api=34 over dataset=38.0]
cold_start: false
degraded: []
data: REAL (internal use only)
---
# Seller 47648617 — Sunflash Tetratech Engineers Company, Nagpur (contact: Sanjay)

## Snapshot
- status: active
- language: hi-IN (last conversation)
- account: Free · auto-debit: Stopped - Deal Cancelled
- on_indiamart: 9 Y 1 M · listing LST
- business: Partnership · Retailer · 1.5 - 5 Cr
- kyc: mobile ✓, email ✓, GST ✓, PAN ✓
- account_manager: Bhushan

## Handle with care
- churn risk: auto-debit Stopped - Deal Cancelled
- has asked if talking to a bot: say upfront you are IndiaMART's AI assistant
- past questions: AI Bot Confirmation (1); Enquiry Lead (1); Problem Complaint (1)

## Open threads (resume these first)
- [callback requested 2026-10-10, today] Seller reports auto-debit stopped after… (not confirmed, ref CB-53A073)
- [voice 2026-10-10, today] Callback to resolve auto-debit issue (ref CB-53A073).
- [voice 2026-10-10, today] Seller must read the unread Bull HD76 enquiry.

## Known facts (do not re-ask)
- unread_enquiry: Bull HD76 4WD Backhoe Loader
- auto_debit_status: stopped due to credit exhaustion
- gst_registered_since: 2017
- products_listed: 7
- location_preference: Local
- categories: Bull Backhoe Loader, Truck Mounted Crane, Bull Wheel Loaders

## Leads & enquiries (90d) — date | product | buyer | status
- received: 2 (30d: 1) (live) | history n=1: read 0%, replied 0% | unread>48h: 1
- 2026-08-07 | Bull HD76 4WD Backhoe Loader, 76 hp, 7850 kg | Sakirkhankhangmail.Com, Bharatpur | unread

## Buyer calls (90d)
- none

## Catalog & market
- top_categories: Bull Backhoe Loader, Truck Mounted Crane, Bull Wheel Loaders (parent: Backhoe Loader)
- products: 7 live | rejected 1 | out of stock 1 | hidden in directory 0
- missing: price 3, photo 0, specs 2, description 4 | low score 7 | price looks wrong 0 | CQS 34
- market (top categories, 4w): 306 buy-leads, 4 paid sellers, local 10

## Conversations (all channels, latest 2)
- 2026-10-10 (today) voice: Sanjay discussed an unresolved meeting and an unread backhoe loader enquiry, ag…
- 2026-06-26 (106d ago) vani call: Meeting Fixed: The lead initially expressed unavailability for a meeting but la…

## Engagement
- vani_history: answered 1/1 | avg 206s
- best_time: evening
- level: low
