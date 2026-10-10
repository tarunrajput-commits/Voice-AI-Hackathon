"""IndiaMART seller products-listing API (the seller's live product catalogue).

    GET http://users.imutils.com/wservce/products/sellerproductslisting/
        token=<literal> mod_id=ANDWEB gluserid=<GLID> AK=<JWT> product_filter=ALL pg_type=<1-based> ordering=4

* 20 products per page; loop while Response.Pagination.HasNextPage is true (never compute pages from counts).
* PRODUCT_FILTER_COUNTS / CATEGORY / MAP_DATA come only on page 1 – read them there, ignore empties after.
* Observed in the live API (differs from the reference text): CATEGORY = the seller's own product GROUPS
  (pcat: "New Items", "Door Guard"); MAP_DATA = IndiaMART categories (mcats: "Door Seals"). Both are
  {id: [product_count, name]}.
* PRODUCT_FILTER_COUNTS.CQS can be 0 when not computed – treated as "not reported", not as a score.

Runtime uses page 1 only (catalogue-wide counts + the 20 most recently modified products, ~1.3 s);
fetch(max_pages=None) crawls everything for offline jobs. Raw responses are cached in data/catalog_cache/.
"""
import json
import os
import time

import httpx

from config import DATA_DIR

URL = os.environ.get("CATALOG_API_URL", "http://users.imutils.com/wservce/products/sellerproductslisting/")
TOKEN = os.environ.get("CATALOG_API_TOKEN", "")          # set in .env, never in code
MOD_ID = os.environ.get("CATALOG_API_MODID", "ANDWEB")
CACHE = DATA_DIR / "catalog_cache"
TTL_S = int(os.environ.get("CATALOG_API_TTL_S", "3600"))


class CatalogError(Exception):
    pass


def _ak():
    return os.environ.get("CATALOG_API_AK") or os.environ.get("GC_API_AK", "")


def fetch_page(glid, page=1, ordering=4, extra_detail=None, timeout=20):
    params = {"token": TOKEN, "mod_id": MOD_ID, "gluserid": str(glid), "AK": _ak(), "product_filter": "ALL",
              "pg_type": page, "ordering": ordering}
    if extra_detail:
        params["extra_detail"] = extra_detail
    r = httpx.get(URL, params=params, timeout=timeout)
    resp = (r.json() or {}).get("Response") or {}
    if str(resp.get("Code")) != "200":
        raise CatalogError(f"sellerproductslisting: {resp.get('Code')} {resp.get('Status')} {resp.get('Message') or ''}".strip())
    return resp


def _product(p):
    """Keep only what a context file / bot needs (no image URLs, no internal ids)."""
    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return {"name": (p.get("ITEM_NAME") or p.get("PC_ITEM_DISPLAY_NAME") or "").strip(),
            "price": p.get("PC_ITEM_FOB_PRICE_FORMATTED") or p.get("PC_ITEM_FOB_PRICE") or "",
            "unit": p.get("PC_ITEM_MOQ_UNIT_TYPE") or "",
            "moq": p.get("PC_ITEM_MIN_ORDER_QUANTITY") or "",
            "score": num(p.get("ITEM_QLTY_SCORE")),
            "mcats": [m.strip() for m in (p.get("MCAT_NAME_LIST") or "").split(",") if m.strip()],
            "group": p.get("PCAT_NAME") or "",
            "modified": p.get("PC_ITEM_MODBYUSRDATE_FORMATED") or "",
            "price_flagged": str(p.get("PC_ITEM_FOB_PRICE_ABSURD_FLAG")) in ("1", "True", "true"),
            "rejected_reason": (p.get("PC_ITEM_REJECTION_REASON") or "").strip() if str(p.get("PC_ITEM_REJECTION_CODE") or "0") != "0" else "",
            "no_price_needed": str(p.get("GLCAT_MCAT_NO_PRICE")) in ("1", "True", "true")}


def fetch(glid, max_pages=1, timeout=20):
    """Returns a normalised catalogue snapshot. max_pages=None crawls until HasNextPage is false."""
    t0 = time.time()
    first = fetch_page(glid, 1, timeout=timeout)
    data = first.get("Data") or {}
    counts = data.get("PRODUCT_FILTER_COUNTS") or {}
    products = [_product(p) for p in data.get("PRODUCTS_DATA") or []]
    page, has_next = 1, bool((first.get("Pagination") or {}).get("HasNextPage"))
    while has_next and (max_pages is None or page < max_pages):
        page += 1
        resp = fetch_page(glid, page, timeout=timeout)
        products += [_product(p) for p in (resp.get("Data") or {}).get("PRODUCTS_DATA") or []]
        has_next = bool((resp.get("Pagination") or {}).get("HasNextPage"))

    def dropdown(block):
        out = []
        for _id, v in (block or {}).items():
            if isinstance(v, list) and len(v) >= 2:
                out.append({"name": v[1], "count": int(v[0] or 0)})
        return sorted(out, key=lambda x: -x["count"])

    return {"counts": counts, "groups": dropdown(data.get("CATEGORY")), "mcats": dropdown(data.get("MAP_DATA")),
            "products": products, "pages_fetched": page, "has_more": has_next,
            "_fetch": {"ms": round((time.time() - t0) * 1000), "fetched_at": time.time()}}


def save(glid, snap):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{glid}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, ensure_ascii=False))
    os.replace(tmp, p)


def cached(glid):
    p = CACHE / f"{glid}.json"
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:
        return None


def is_stale(glid):
    c = cached(glid)
    return not c or time.time() - c["_fetch"]["fetched_at"] > TTL_S
