---
schema: seller.v2
glid: "12855767"
role: seller
generated_at: 2026-10-10T11:55:47.376Z
freshness_ms: 20.6
build_ms: 4.8
sources: {events_until: 2026-10-10, live_api: 2026-10-10T07:00:41.588Z, catalog_api: 2026-10-10T07:00:41.329Z}
pipeline: apis_first+csv (gc=cached, catalog=cached, csv_rows=872, live=1)
lookback_days: {enquiries: 90, pns_calls: 90, buyleads: 45, wa_chat: 60, vani_calls: 180, exec_calls: 60, whatsapp: 30, conversations: 30}
merge: {policy: catalog_api > gc_api > csv, fields: {catalog: 4, api: 9, dataset: 0}}
conflicts_resolved: [account_type: api=Paid over dataset=Free; products_listed: catalog=60 over api=57; products_listed: catalog=60 over dataset=3]
cold_start: false
degraded: []
data: REAL (internal use only)
---
# Seller 12855767 — Wego International, New Delhi (contact: Bhavesh)

## Snapshot
- status: active
- language: hi-IN (last conversation)
- account: Paid · MDC Pro · Annual
- on_indiamart: 11 Y 10 M · listing TFL
- business: Proprietor · 40 L - 1.5 Cr
- kyc: mobile ✓, email ✓, GST ✓, PAN ✓, address ✓
- account_manager: Abhishek

## Handle with care
- none

## Open threads (resume these first)
- [voice 2026-10-10, today] Record executive callback to share the 15 products with missing price…
- [voice 2026-10-10, today] Transfer call to Kartik once executive callback is arranged.
- [voice 2026-10-10, today] Update prices and missing product names via the IndiaMART app.

## Known facts (do not re-ask)
- secondary_contact_name: Kartik, Subhanshu, Meet Jain, Madhur Jain, Dnyaneshwar and Vaibhav
- stock_status: in stock (Washing Machine Pipe; Inlet P…)
- gst_registered_since: 2022
- products_listed: 60
- location_preference: -

## Leads & enquiries (90d) — date | product | buyer | status
- received: 303 (30d: 97) (live) | history n=111: read 99%, replied 71% | unread>48h: 1
- buyleads_bought_45d: 53 (credits 17000) | top: Vacuum Cleaner Motors
- 2026-10-02 | Electromate Usha Air Fryer Heating Tube | Habibulla, Canning | unread

## Buyer calls (90d)
- received: 84 | connected: 46 (55%) | avg_talk: 1.2m | live received_90d: 90, picked_4w: 28/53
- last: 2026-10-01 (9d ago) connected 0.4m from 

## Catalog & market
- top_categories: Mixer Grinder Motor, Heater Tube, Gas Geyser Spare Parts (parent: Domestic Appliance Motors)
- products: 60 live | rejected 4 | out of stock 16 | hidden in directory 11
- missing: price 15, photo 0, specs 21, description 31 | low score 24 | price looks wrong 1
- market (top categories, 4w): 445 buy-leads, 41 paid sellers, local 117

## Conversations (all channels, latest 1)
- 2026-10-10 (today) voice: Bhavesh requested a callback to update prices for 15 products and lis…

## Engagement
- vani_history: answered 2/2 | avg 44s
- executive_calls_60d: answered 5/15
- best_time: afternoon
- level: high
