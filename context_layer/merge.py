"""Field-level merge of the sources for one GLID.

    catalog  – live seller products-listing API (system of record for the catalogue)
    api      – live Global Context API snapshot (account, KYC, tickets, counters …)
    dataset  – seller CSV dataset / event store (history up to the export date)

Policy: for each field, the first source in its priority list that has a value wins.
  * catalogue fields (product count, products without price/photo, CQS): catalog > api > dataset
  * everything else both live and CSV provide:                         api > dataset
Whenever a lower-priority source also has a (different) value, it is recorded as a conflict
(field, winner_source, winner_value, loser_source, loser_value) and written to the front matter.
Counters (enquiries / buyer calls in 30/90 days) use the live API value; CSV rows give the detail.
"""
import re


def _norm(v):
    return re.sub(r"[^a-z0-9]+", "", str(v).lower())


def _present(v):
    return v not in (None, "", "--", "-", "NA", [], {}) and str(v).strip() not in ("", "--", "NA")


def _paid_from_dataset(prof):
    p = str(prof.get("is_paid", "")).strip()
    return "Paid" if p in ("1", "1.0") else "Free" if p in ("-1", "-1.0", "0", "0.0") else ""


def _flag(v):
    return str(v).strip() in ("1", "1.0", "True", "true")


def _cat_count(cat, key):
    v = ((cat or {}).get("counts") or {}).get(key)
    return v if v not in (None, "") else None


def _cat_cqs(cat):
    v = _cat_count(cat, "CQS")
    return v if v not in (None, 0, "0") else None          # 0 = not computed, not a score


# field -> ([(source, getter), ...] in priority order, comparable_for_conflicts)
SELLER_FIELDS = {
    "company":         ([("api", lambda c, g, p: g.get("company")), ("dataset", lambda c, g, p: p.get("company_name"))], True),
    "city":            ([("api", lambda c, g, p: g.get("city")), ("dataset", lambda c, g, p: p.get("seller_city"))], True),
    "first_name":      ([("api", lambda c, g, p: (g.get("first_name") or "").title())], False),
    "account_type":    ([("api", lambda c, g, p: g.get("customer_type")), ("dataset", lambda c, g, p: _paid_from_dataset(p))], True),
    "service":         ([("api", lambda c, g, p: g.get("highest_service"))], False),
    "listing_status":  ([("api", lambda c, g, p: g.get("listing_status")), ("dataset", lambda c, g, p: p.get("listing_status"))], True),
    "email_verified":  ([("api", lambda c, g, p: True if g.get("email_verified") else None),
                         ("dataset", lambda c, g, p: _flag(p.get("email_verified_flag")) or None)], True),
    "business_type":   ([("api", lambda c, g, p: g.get("company_type")), ("dataset", lambda c, g, p: p.get("business_type"))], False),
    "products_listed": ([("catalog", lambda c, g, p: _cat_count(c, "PRODUCT_COUNT")),
                         ("api", lambda c, g, p: g.get("approved_products")),
                         ("dataset", lambda c, g, p: p.get("eng_product_count"))], True),
    "products_without_price": ([("catalog", lambda c, g, p: _cat_count(c, "PRODUCT_COUNT_WITHOUT_PRICE")),
                                ("api", lambda c, g, p: g.get("prd_without_price"))], True),
    "products_without_photo": ([("catalog", lambda c, g, p: _cat_count(c, "PRODUCT_COUNT_WITHOUT_PHOTO")),
                                ("api", lambda c, g, p: g.get("prd_without_photo"))], True),
    "cq_score":        ([("catalog", lambda c, g, p: _cat_cqs(c)), ("api", lambda c, g, p: g.get("cq_score")),
                         ("dataset", lambda c, g, p: p.get("eng_cqs"))], True),
    "categories":      ([("catalog", lambda c, g, p: ", ".join(m["name"] for m in (c or {}).get("mcats", [])[:3])),
                         ("api", lambda c, g, p: ", ".join(g.get("top_mcats") or [])),
                         ("dataset", lambda c, g, p: ", ".join(x for x in [p.get("top_category_1"), p.get("top_category_2"),
                                                                            p.get("top_category_3")] if x))], False),
}


def _same(a, b):
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return _norm(a) == _norm(b)


def seller_view(gc, prof, cat=None):
    """Returns (values, sources, conflicts):
       values[field]  = chosen value;  sources[field] = "catalog" | "api" | "dataset"
       conflicts      = [(field, winner_src, winner_val, loser_src, loser_val)]"""
    gc, prof = gc or {}, prof or {}
    values, sources, conflicts = {}, {}, []
    for field, (chain, comparable) in SELLER_FIELDS.items():
        found = [(src, get(cat, gc, prof)) for src, get in chain]
        found = [(src, v) for src, v in found if _present(v)]
        if not found:
            continue
        (wsrc, wval) = found[0]
        values[field], sources[field] = wval, wsrc
        if comparable:
            for lsrc, lval in found[1:]:
                if not _same(wval, lval):
                    conflicts.append((field, wsrc, wval, lsrc, lval))
    return values, sources, conflicts


def counters(gc, dataset_counts):
    """API counters win (they are live); dataset counts are used only when the API has none."""
    out = {}
    for k, ds in dataset_counts.items():
        api = gc.get(k) if gc else None
        out[k] = (int(api), "api") if _present(api) else (ds, "dataset")
    return out
