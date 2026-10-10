---
schema: seller.v2
glid: "47648617"
role: seller
generated_at: 2026-10-10T11:55:47.428Z
freshness_ms: 2.2
build_ms: 1.4
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
- [voice 2026-10-10, today] Update missing prices on 3 catalog products.
- [voice 2026-10-10, today] Contact the buyer from Bharatpur regarding the unread enquiry.
- [voice 2026-10-10, today] Verify if the scheduled meeting from June 26 occurred.

## Known facts (do not re-ask)
- delivery_city: Bharatpur
- product: Bull HD76 Backhoe Loader
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
- 2026-10-10 (today) voice: Sanjay confirmed updating Backhoe Loader photos and acknowledged an unread lead…
- 2026-10-10 (today) voice: Seller said: क्या चाहिए? नहीं, इस प्रोसेस नहीं है, प्रोसेस स्लो कर रहा है। देखो…

## Engagement
- vani_history: answered 1/1 | avg 206s
- best_time: evening
- level: low
