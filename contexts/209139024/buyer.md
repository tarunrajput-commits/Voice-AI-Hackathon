---
schema: buyer.v2
glid: "209139024"
role: buyer
generated_at: 2026-10-10T10:49:23.436Z
freshness_ms: 129.2
build_ms: 23.2
sources: {events_until: 2026-10-10, live_api: 2026-10-10T06:19:48.604Z, catalog_api: not fetched}
pipeline: apis_first+csv (gc=cached, catalog=skipped, csv_rows=557, live=6)
lookback_days: {buyer_activity: 30, wa_chat: 60, call_extractions: 90, enquiries: 90, conversations: 30}
merge: {policy: catalog_api > gc_api > csv, fields: {catalog: 0, api: 0, dataset: 0}}
conflicts_resolved: []
cold_start: false
degraded: []
data: REAL (internal use only)
---
# Buyer 209139024 — Anil, Jaipur

## Snapshot
- status: active
- language: hi-IN (call extractions)
- business_buyer: yes — also sells Door Seals as Shreeva Enterprises
- kyc: mobile ✓, email ✓, GST ✓

## Open threads (resume these first)
- [buy-lead 2026-10-07, 3d ago] Posted requirement: EPE Becker Rod — share matching sellers / quotes
- [c2c 2026-10-05, 5d ago] Contacted a seller — ask how it went
- [call 2026-09-16, 24d ago] Was sourcing Pneumatic Door Guard Packing Machine; Band Sealer… by phone

## Known facts (do not re-ask)
- price_quoted: 300000
- number_of_guards_per_pouch: 1
- packing_type: Pouch
- product_size_compatibility: 36 Inch
- type: Manual
- product: Pneumatic Door Guard Packing Machine; Band Sealer (Manual)

## Requirements posted (60d) — date | product | channel
- 2026-10-07 | EPE Becker Rod | buy-lead
- 2026-09-22 | Digital Weighing Scale | buy-lead
- 2026-09-17 | Jaipur to Ghaziabad Part Truck Load Transport | buy-lead
- 2026-09-16 | Door Guard Packing Machine | buy-lead

## Searches & browsing (30d)
- Door Guards ×8
- Mini Bag Sealer ×5
- Hand Sealer ×4
- Plastic Bag Sealing Machine ×3
- Impulse Sealer ×3
- recent searches: Epe Becker Rod, backer rod, pp woven bags, door guard packing machine, door guard, bag closing machine

## Sellers contacted (90d)
- total: 80 sellers (C2C 71, ENQ 9), last 2026-10-05

## Sourcing calls (90d) — date | product | specs | price
- 2026-09-16 | Pneumatic Door Guard Packing Machine; B… | Type: Pneumatic; Product Size compatibility: 36 Inch; Packi… | 300000
- 2026-09-02 | Non Woven Roll (Rewinding Service) | Service Type: Rewinding | -

## Conversations (all channels, latest 4)
- 2026-09-02 (38d ago) whatsapp bot: Msite BL Quantity, Msite BL Spec
- 2026-08-22 (49d ago) whatsapp bot: Msite BL Quantity, Msite BL Spec → Backer Rod

## Engagement
- last_active: 2026-10-07 (3d ago)
- activity_30d: C2C 121, ENQ 115, Browse 97, Search 88, Others 52, BL 5
- sourcing_calls_90d: 2 | requirements_posted: 7
- best_time: afternoon
- level: high
