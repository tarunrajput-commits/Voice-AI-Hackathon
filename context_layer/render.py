"""Deterministic renderers for buyer.md / seller.md (schema v2, real data).

No LLM here on purpose: rendering is pure and runs in milliseconds (freshness), its output is
byte-stable for the same inputs (diffs, caching), and its shape never drifts (other consumers parse
it). The only LLM-written text in a file comes from upstream summaries (VANI call summaries,
executive notes) and this bot's own end-of-conversation write-back.

Format rules (shared by both files, see README "File contract"):
  * YAML front matter: schema, GLID, timestamps, freshness, lookbacks, per-source watermarks
  * fixed `## ` sections in a fixed order; empty sections render "- none"
  * key/value sections use "- key: value"; list sections use " | "-separated rows
"""
import re
from urllib.parse import unquote
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone

from config import CAPS, LOOKBACK_DAYS
from context_layer import merge
from context_layer.privacy import first_name, safe_facts, scrub

IST = timezone(timedelta(hours=5, minutes=30))


# ------------------------------------------------------------------ helpers
def _dt(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _d(ts):
    return _dt(ts).astimezone(IST).strftime("%Y-%m-%d")


def _ago(ts):
    """Relative age, so the LLM never does date arithmetic. Kept correct by the scheduled sweep."""
    n = (datetime.now(IST).date() - _dt(ts).astimezone(IST).date()).days
    return "today" if n <= 0 else "yesterday" if n == 1 else f"{n}d ago"


def _age_days(ts):
    return (datetime.now(timezone.utc) - _dt(ts)).total_seconds() / 86400


def _clip(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _ok(x):
    return not isinstance(x, Exception)


def _rows(x):
    return x if _ok(x) and x else []


def _dict(x):
    return x if _ok(x) and isinstance(x, dict) else {}


def _pct(a, b):
    return f"{round(100 * a / b)}%" if b else "n/a"


def _flag(v):
    return str(v).strip() in ("1", "1.0", "True", "true", "Y", "yes")


def _num(v, default=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _section(title, lines):
    return f"## {title}\n" + ("\n".join(lines) if lines else "- none")


def _bucket(ts):
    h = _dt(ts).astimezone(IST).hour
    return "morning" if 6 <= h < 12 else "afternoon" if h < 17 else "evening" if h < 22 else "night"


def _level(score):
    return "high" if score >= 30 else "medium" if score >= 8 else "low"


def _request_threads(reqs, width):
    """Pending callback / meeting requests (skill.md §11) – always shown as NOT confirmed."""
    out = []
    for r in sorted(reqs, key=lambda x: x["ts"], reverse=True):
        p = r["payload"]
        kind = "callback requested" if r["type"] == "callback_request" else "meeting requested"
        pref = f" — preferred {p['preferred_time']}" if p.get("preferred_time") else ""
        flag = "; contact restriction: needs review" if p.get("contact_restriction") else ""
        out.append(f"- [{kind} {_d(r['ts'])}, {_ago(r['ts'])}] {_clip(p.get('reason', ''), width - 40)}{pref} "
                   f"(not confirmed, ref {p.get('reference')}{flag})")
    return out


def _thread_state(convs):
    """Bot write-back open items still unresolved, newest first."""
    open_items = OrderedDict()
    for c in convs:
        p = c["payload"]
        for r in p.get("resolved_items", []) or []:
            rl = r.lower()
            for k in list(open_items):
                if rl in k or k in rl:
                    open_items.pop(k)
        for item in p.get("open_items", []) or []:
            open_items[item.lower()] = (c["ts"], p.get("channel", "?"), scrub(item))
    return sorted(open_items.values(), key=lambda t: t[0], reverse=True)


def _facts(fact_events, cap):
    """fact_events: [(ts, source_label, {k: v})] chronological. Newest wins; conflicts kept visible."""
    facts = OrderedDict()
    for ts, src, kv in fact_events:
        for k, v in safe_facts(kv).items():
            k = k.strip().lower().replace(" ", "_")
            v = str(v).strip()
            if not v:
                continue
            if k in facts and facts[k][0].lower() != v.lower():
                facts[k] = (v, f"was {facts[k][0]}", ts)
            elif k not in facts:
                facts[k] = (v, src, ts)
            facts.move_to_end(k)
    out = []
    for k, (v, note, ts) in reversed(facts.items()):
        line = f"- {k}: {v}"
        if note.startswith("was "):
            line += f" ({note}; updated {_d(ts)})"
        out.append(line)
    return out[:cap]


def _spec_facts(specs):
    """'Size: 39 inch; Color: Brown' -> {'size': '39 inch', 'color': 'Brown'}"""
    out = {}
    for part in (specs or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            k = re.sub(r"\W+", "_", k.strip().lower()).strip("_")
            if k and v.strip() and k != "product_name":
                out[k] = v.strip()
    return out


_HI_WORDS = re.compile(r"\b(haan|ji|nahi|nahin|kya|hai|hain|bol|raha|rahe|kariye|baad|abhi|theek|accha|bhai)\b", re.I)
_LANG = {"Hindi": "hi-IN", "Tamil": "ta-IN", "Telugu": "te-IN", "Kannada": "kn-IN", "Malayalam": "ml-IN",
         "Bengali": "bn-IN", "Marathi": "mr-IN", "Gujarati": "gu-IN", "Punjabi": "pa-IN", "Odia": "od-IN", "English": "en-IN"}


def _language(turns, exts, convs):
    for c in reversed(convs):                                       # this bot heard them speak
        if c["payload"].get("language"):
            return c["payload"]["language"], "last conversation"
    said = " ".join(t for row in turns for spk, t in row["payload"].get("turns", []) if spk != "bot")
    if said:
        if re.search(r"[ऀ-ॿ]", said) or len(_HI_WORDS.findall(said)) >= 2:
            return "hi-IN", "VANI transcript"
        return "en-IN", "VANI transcript"
    langs = Counter()
    for e in exts:
        for l in re.findall(r"[A-Za-z]+", e["payload"].get("languages", "")):
            if l in _LANG and l != "English":
                langs[_LANG[l]] += 1
    if langs:
        return langs.most_common(1)[0][0], "call extractions"
    return "hi-IN", "default"


def _wa_sessions(chats, n):
    """Group WhatsApp chatbot turns by session -> latest n sessions (newest first)."""
    sess = OrderedDict()
    for c in chats:
        sid = c["payload"].get("session_id") or c["ts"][:10]
        s = sess.setdefault(sid, {"ts": c["ts"], "intents": [], "typed": "", "reply": ""})
        s["ts"] = c["ts"]
        p = c["payload"]
        if p.get("intent") and p["intent"] not in s["intents"]:
            s["intents"].append(p["intent"])
        if p.get("action") == "typed" and p.get("user_message"):
            s["typed"] = p["user_message"]
        if p.get("bot_reply"):
            s["reply"] = p["bot_reply"]
    return sorted(sess.values(), key=lambda s: s["ts"], reverse=True)[:n]


def _requirement(reply):
    m = re.search(r"requirement for \*?([^*\n]+?)\*? (has been|is) received", reply or "", re.I) or \
        re.search(r"Enquiry for \*([^*]+)\*", reply or "")
    return m.group(1).strip() if m and m.group(1).strip() else ""


def _clean_intent(i):
    i = (i or "").replace("_", " ").replace("..", "").strip()
    return {"WA Call Feedback": "call feedback", "WA Callback Connect Q": "callback request",
            "Photo uploaded but not added as a product as": "photo upload (not added)"}.get(i, i)


# ------------------------------------------------------------------ seller.md
def render_seller(glid, data, caps=CAPS, width=140):
    prof, gc = _dict(data.get("profile")), _dict(data.get("gc"))
    enq, msgs, pns = _rows(data.get("enquiries")), _rows(data.get("enquiry_messages")), _rows(data.get("pns_calls"))
    bls, wam, wac = _rows(data.get("buyleads")), _rows(data.get("whatsapp")), _rows(data.get("wa_chat"))
    exts, vani, turns = _rows(data.get("call_extractions")), _rows(data.get("vani_calls")), _rows(data.get("vani_turns"))
    execs, convs = _rows(data.get("exec_calls")), _rows(data.get("conversations"))

    cold = not (prof or gc or enq or pns or vani or wac or convs or _dict(data.get("catalog")).get("counts"))
    # one merged view of the fields both sources provide: live API wins, dataset fills gaps, conflicts recorded
    catalog = _dict(data.get("catalog"))
    cc = catalog.get("counts") or {}
    mv, msrc, conflicts = merge.seller_view(gc, prof, catalog)
    data["_conflicts"], data["_field_sources"] = conflicts, msrc
    company = mv.get("company") or "Seller"
    city = mv.get("city") or ""
    fname = mv.get("first_name", "")
    title = f"# Seller {glid} — {company}" + (f", {city}" if city else "") + (f" (contact: {fname})" if fname else "")
    lang, lang_src = _language(turns, exts, convs)

    # --- Snapshot
    acct = " · ".join(x for x in [mv.get("account_type"), mv.get("service"), gc.get("payment_plan")] if x)
    kyc_ok = [n for n, f in [("mobile", "mobile_verified_flag"), ("GST", "gst_verified_flag"),
                             ("PAN", "is_pan_number_available")] if _flag(prof.get(f))]
    if mv.get("email_verified"):
        kyc_ok.insert(1, "email")
    if gc.get("address_verified"):
        kyc_ok.append("address")
    snap = [f"- status: {'cold_start (no history in any source)' if cold else 'active'}",
            f"- language: {lang} ({lang_src})"]
    if acct:
        snap.append(f"- account: {acct}" + (f" · renewal {gc['renewal_date']}" if gc.get("renewal_date") else "")
                    + (f" · auto-debit: {gc['nach']}" if gc.get("nach") else ""))
    if gc.get("registered_since") or mv.get("listing_status"):
        snap.append(f"- on_indiamart: {gc.get('registered_since') or '?'} · listing {mv.get('listing_status') or '?'}")
    biz = " · ".join(x for x in [mv.get("business_type"), prof.get("nature_of_business"), prof.get("annual_turnover")] if x)
    if biz:
        snap.append(f"- business: {biz}")
    if prof or gc:
        snap.append(f"- kyc: {', '.join(k + ' ✓' for k in kyc_ok) or 'none verified'}")
    if gc.get("account_manager"):
        snap.append(f"- account_manager: {gc['account_manager']}")

    # --- Handle with care: behaviour constraints for the bot
    care = []
    if _flag(prof.get("do_not_call_requested")):
        care.append("- DO-NOT-CALL requested: no outbound pitch; inbound help only, keep it short")
    if gc.get("wip_tickets"):
        t = gc["wip_tickets"][0]
        care.append(f"- open ticket: {t['type']} (since {t['since']})" + (f" +{len(gc['wip_tickets']) - 1} more" if len(gc["wip_tickets"]) > 1 else ""))
    if gc.get("nach") and re.search(r"stop|cancel|fail|bounce", gc["nach"], re.I):
        care.append(f"- churn risk: auto-debit {gc['nach']}")
    elif gc.get("high_churn"):
        care.append("- churn risk: flagged high-churn")
    if _flag(prof.get("showed_frustration")):
        care.append("- showed frustration on past VANI calls: apologise once, be brief, offer an executive")
    if _flag(prof.get("asked_if_talking_to_bot")):
        care.append("- has asked if talking to a bot: say upfront you are IndiaMART's AI assistant")
    if _flag(prof.get("already_in_touch_with_executive")):
        care.append(f"- already in touch with an executive{' (' + gc['account_manager'] + ')' if gc.get('account_manager') else ''}: don't re-pitch")
    if prof.get("past_objections"):
        care.append(f"- past objections: {_clip(prof['past_objections'], 110)}")
    if prof.get("past_questions_asked"):
        care.append(f"- past questions: {_clip(prof['past_questions_asked'], 110)}")
    if gc.get("negative_feedback_90d") or gc.get("irate_90d"):
        care.append(f"- complaints 90d: negative feedback {gc.get('negative_feedback_90d', 0)}, irate {gc.get('irate_90d', 0)}")
    care = care[: caps["care"]]

    # --- enquiry lifecycle
    replied = {m["payload"]["enquiry_id"] for m in msgs if m["payload"].get("from") == "seller"}
    enq_by = OrderedDict((e["payload"]["enquiry_id"], e) for e in enq)
    unread_old = [e for e in enq_by.values() if not e["payload"].get("read") and _age_days(e["ts"]) > 2]
    read_n = sum(1 for e in enq_by.values() if e["payload"].get("read"))
    replied_n = sum(1 for i in enq_by if i in replied)
    enq30 = sum(1 for e in enq_by.values() if _age_days(e["ts"]) <= 30)

    # --- Open threads
    threads = _request_threads(_rows(data.get("requests")), width) + \
        [f"- [{ch} {_d(ts)}, {_ago(ts)}] {_clip(t, width)}" for ts, ch, t in _thread_state(convs)]
    for c in gc.get("exec_connects_30d", []):
        note = (c.get("summary") or c.get("status") or "").strip()
        if c.get("date") and len(note.split()) >= 4:   # skip status codes like "Nr", "Test", "ALREAdy talked"
            threads.append(f"- [executive {c['date'][:10]}, {_ago(c['date'].replace(' ', 'T') + '+05:30')}] {_clip(scrub(note), width)}")
            break
    if gc.get("last_call_comment") and len(gc["last_call_comment"].strip()) >= 12:
        threads.append(f"- [executive note {gc.get('last_call_date', '')}] {_clip(scrub(gc['last_call_comment']), width + 60)}")
    if vani:
        v = vani[-1]["payload"]
        if v.get("disposition") in ("Call Later / Busy", "Meeting Fixed"):
            what = "asked to be called later" if v["disposition"].startswith("Call") else "meeting fixed – check it happened"
            threads.append(f"- [vani {_d(vani[-1]['ts'])}, {_ago(vani[-1]['ts'])}] {what}: {_clip(v.get('summary'), 90)}")
    if unread_old:
        threads.append(f"- [system] {len(unread_old)} enquiries unread >48h (latest: {unread_old[-1]['payload']['product']})")
    rejected = [p for p in catalog.get("products", []) if p.get("rejected_reason")]
    if _num(cc.get("REJECTED_COUNT")) > 0:
        why = f" – e.g. {rejected[0]['name']}: {_clip(rejected[0]['rejected_reason'], 50)}" if rejected else ""
        threads.append(f"- [catalog] {int(_num(cc['REJECTED_COUNT']))} product(s) rejected{why}")
    gaps = [(k, n) for k, n in [("no price", mv.get("products_without_price")), ("no photo", mv.get("products_without_photo")),
                                ("no specifications", cc.get("PRODUCT_COUNT_WITHOUT_SPECIFICATION")),
                                ("price looks wrong", cc.get("PRODUCT_COUNT_WITH_INCORRECT_PRICE"))] if _num(n) > 0]
    if gaps:
        threads.append(f"- [catalog] products with {', '.join(f'{k}: {int(_num(n))}' for k, n in gaps)}")
    threads = threads[: caps["open_threads"]]

    # --- Known facts (do not re-ask)
    base = {k: v for k, v in {
        "categories": ", ".join(x for x in [prof.get("top_category_1"), prof.get("top_category_2"), prof.get("top_category_3")] if x)
                      or mv.get("categories"),
        "location_preference": gc.get("location_pref"),
        "products_listed": mv.get("products_listed"),
        "gst_registered_since": prof.get("gst_registration_year")}.items() if v}
    fe = [("2026-01-01T00:00:00+00:00", "profile", base)]
    for e in exts:
        f = {}
        prod = _clip(e["payload"].get("products"), 30)
        if e["payload"].get("stock"):
            f["stock_status"] = f"{e['payload']['stock']} ({prod})"
        if e["payload"].get("prices"):
            f["price_quoted"] = f"{e['payload']['prices']} ({prod})"
        if f:
            fe.append((e["ts"], "call", f))
    fe += [(c["ts"], c["payload"].get("channel", "bot"), c["payload"].get("facts", {})) for c in convs]
    fe.sort(key=lambda x: x[0])
    facts = _facts(fe, caps["facts"])

    # --- Leads & enquiries
    lead_lines = []
    cnt = merge.counters(gc, {"enq_90d": len(enq_by), "enq_30d": enq30})
    if enq_by or cnt["enq_90d"][1] == "api":
        tag = " (live)" if cnt["enq_90d"][1] == "api" else ""
        line = f"- received: {cnt['enq_90d'][0]} (30d: {cnt['enq_30d'][0]}){tag}"
        if enq_by:   # read / reply rates and rows come from the event history
            line += (f" | history n={len(enq_by)}: read {_pct(read_n, len(enq_by))}, replied {_pct(replied_n, len(enq_by))}"
                     f" | unread>48h: {len(unread_old)}")
        lead_lines.append(line)
    if not enq_by and gc.get("last_enquiry_product"):
        lead_lines.append(f"- last enquiry (live): {_clip(gc['last_enquiry_product'], 50)}")
    if bls:
        kws = Counter(b["payload"]["keyword"] for b in bls if b["payload"].get("keyword"))
        lead_lines.append(f"- buyleads_bought_{LOOKBACK_DAYS['buyleads']}d: {len(bls)} (credits {sum(b['payload'].get('credits', 0) for b in bls)})"
                          + (f" | top: {', '.join(k for k, _ in kws.most_common(2))}" if kws else ""))
    elif gc.get("bl_consumed_4w"):
        lead_lines.append(f"- buyleads_consumed_4w: {gc['bl_consumed_4w']} (credits allotted {gc.get('bl_credits_4w')})")
    for e in list(reversed(enq_by.values()))[: caps["enquiries"]]:
        p = e["payload"]
        status = "replied" if p["enquiry_id"] in replied else "read" if p.get("read") else "unread"
        buyer = ", ".join(x for x in [first_name(p.get("buyer_name")), p.get("buyer_city")] if x) or "buyer"
        lead_lines.append(f"- {_d(e['ts'])} | {_clip(p.get('product'), 45)} | {buyer} | {status}")

    # --- Buyer calls (PNS)
    call_lines = []
    pc = merge.counters(gc, {"pns_90d": len(pns)})
    if pns:
        con = [c for c in pns if c["payload"].get("status") == "Connected"]
        avg = sum(c["payload"].get("talk_sec", 0) for c in con) / len(con) / 60 if con else 0
        last = pns[-1]
        lp = last["payload"]
        live = f" | live received_90d: {pc['pns_90d'][0]}, picked_4w: {gc.get('pns_picked_4w')}/{gc.get('pns_received_4w')}" \
            if pc["pns_90d"][1] == "api" else ""
        call_lines.append(f"- received: {len(pns)} | connected: {len(con)} ({_pct(len(con), len(pns))}) | avg_talk: {avg:.1f}m{live}")
        call_lines.append(f"- last: {_d(last['ts'])} ({_ago(last['ts'])}) {lp.get('status', '').lower()}"
                          + (f" {round(lp.get('talk_sec', 0) / 60, 1)}m" if lp.get("talk_sec") else "") + f" from {lp.get('circle', '?')}")
        missed7 = sum(1 for c in pns if c["payload"].get("status") != "Connected" and _age_days(c["ts"]) <= 7)
        if missed7:
            call_lines.append(f"- missed_last_7d: {missed7}")
    elif gc.get("pns_90d"):
        call_lines.append(f"- received_90d: {gc['pns_90d']} | picked_4w: {gc.get('pns_picked_4w')}/{gc.get('pns_received_4w')}")

    # --- Catalog & market (live products API first, then Global Context API, then CSV)
    cat = []
    cats = [m["name"] for m in catalog.get("mcats", [])[:3]] or \
        [x for x in [prof.get("top_category_1"), prof.get("top_category_2"), prof.get("top_category_3")] if x] or gc.get("top_mcats", [])
    if cats:
        cat.append(f"- top_categories: {', '.join(cats)}" + (f" (parent: {prof['top_parent_category']})" if prof.get("top_parent_category") else ""))
    if cc:
        cat.append(f"- products: {cc.get('PRODUCT_COUNT', '?')} live | rejected {cc.get('REJECTED_COUNT', 0)} | "
                   f"out of stock {cc.get('OUT_OF_STOCK_COUNT', 0)} | hidden in directory {cc.get('PRODUCT_COUNT_INVISIBLE_ON_DIR', 0)}")
        cat.append(f"- missing: price {cc.get('PRODUCT_COUNT_WITHOUT_PRICE', 0)}, photo {cc.get('PRODUCT_COUNT_WITHOUT_PHOTO', 0)}, "
                   f"specs {cc.get('PRODUCT_COUNT_WITHOUT_SPECIFICATION', 0)}, description {cc.get('PRODUCT_COUNT_WITHOUT_DESCRIPTION', 0)} | "
                   f"low score {cc.get('PRODUCT_COUNT_WITH_LOW_SCORE', 0)} | price looks wrong {cc.get('PRODUCT_COUNT_WITH_INCORRECT_PRICE', 0)}"
                   + (f" | CQS {mv['cq_score']}" if mv.get("cq_score") else ""))
        if catalog.get("groups") and caps.get("catalog_detail", 1):
            cat.append("- groups: " + ", ".join(f"{g['name']} {g['count']}" for g in catalog["groups"][:4] if g["count"]))
        recent = [p for p in catalog.get("products", []) if p.get("name")][:3 if caps.get("catalog_detail", 1) else 0]
        if recent:
            cat.append("- recently updated: " + "; ".join(
                f"{_clip(p['name'], 32)}" + (f" ₹{p['price']}/{p['unit'] or 'unit'}" if p.get("price") else " (no price)")
                + (f" MOQ {p['moq']}" if p.get("moq") else "") for p in recent))
    elif mv.get("products_listed") or gc:
        cat.append(f"- products: {mv.get('products_listed') or '?'}"
                   + (f" | no price: {mv.get('products_without_price', 0)} | no photo: {mv.get('products_without_photo', 0)}" if gc else "")
                   + (f" | CQS: {mv['cq_score']}" if mv.get("cq_score") else ""))
    if gc.get("market_total_bl"):
        cat.append(f"- market (top categories, 4w): {gc['market_total_bl']} buy-leads, {gc.get('market_paid_sellers')} paid sellers"
                   + (f", local {gc['market_local_bl']}" if gc.get("market_local_bl") else ""))

    # --- Conversations across channels
    conv = []
    for c in convs:
        conv.append((c["ts"], c["payload"].get("channel", "bot"), c["payload"].get("summary", "")))
    for v in vani:
        conv.append((v["ts"], "vani call", f"{v['payload'].get('disposition')}: {v['payload'].get('summary', '')}"))
    for s in _wa_sessions(wac, 3):
        msg = f"“{s['typed']}”" if s["typed"] else ""
        conv.append((s["ts"], "whatsapp bot", f"{', '.join(_clean_intent(i) for i in s['intents'][:2]) or 'chat'} {msg}".strip()))
    seen = set()
    for c in gc.get("exec_connects_30d", []):
        if c.get("date") and c.get("summary") and c["summary"][:60] not in seen:
            seen.add(c["summary"][:60])
            conv.append((c["date"].replace(" ", "T") + "+05:30", "executive call", c["summary"]))
    conv.sort(key=lambda x: x[0], reverse=True)
    conv_lines = [f"- {_d(ts)} ({_ago(ts)}) {ch}: {_clip(scrub(s), width)}" for ts, ch, s in conv[: caps["conversations"]]]

    # --- Engagement
    eng = []
    if wam:
        user = [m for m in wam if m["payload"].get("sender") == "USER"]
        api = [m for m in wam if m["payload"].get("sender") == "API"]
        read = sum(1 for m in api if m["payload"].get("status") == "read")
        eng.append(f"- whatsapp_30d: {len(wam)} msgs ({len(user)} from seller) | read_rate: {_pct(read, len(api))} | last: {_d(wam[-1]['ts'])}")
    if prof.get("bot_attempts") and _num(prof["bot_attempts"]):
        eng.append(f"- vani_history: answered {int(_num(prof.get('bot_answered')))}/{int(_num(prof['bot_attempts']))} | "
                   f"avg {round(_num(prof.get('avg_answered_call_sec')))}s"
                   + (f" | {_clip(prof['past_dispositions_detailed'], 70)}" if prof.get("past_dispositions_detailed") else ""))
    if execs:
        ans = sum(1 for e in execs if e["payload"].get("status") == "Answered")
        eng.append(f"- executive_calls_{LOOKBACK_DAYS['exec_calls']}d: answered {ans}/{len(execs)}")
    acts = [x["ts"] for x in enq + pns + wam + wac + vani + convs]
    score = len(wam) / 5 + len(enq) / 2 + len(pns) / 2 + len(bls) + 3 * len(convs) + _num(prof.get("eng_activity_30d"))
    if acts:
        eng += [f"- best_time: {Counter(_bucket(t) for t in acts).most_common(1)[0][0]}", f"- level: {_level(score)}"]

    body = [title,
            _section("Snapshot", snap),
            _section("Handle with care", care),
            _section("Open threads (resume these first)", threads),
            _section("Known facts (do not re-ask)", facts),
            _section(f"Leads & enquiries ({LOOKBACK_DAYS['enquiries']}d) — date | product | buyer | status", lead_lines),
            _section(f"Buyer calls ({LOOKBACK_DAYS['pns_calls']}d)", call_lines),
            _section("Catalog & market", cat),
            _section(f"Conversations (all channels, latest {caps['conversations']})", conv_lines),
            _section("Engagement", eng)]
    return "\n\n".join(body) + "\n", cold


# ------------------------------------------------------------------ buyer.md
def render_buyer(glid, data, caps=CAPS, width=140, seller_names=None):
    prof, gc = _dict(data.get("profile")), _dict(data.get("gc"))
    acts, wac = _rows(data.get("buyer_activity")), _rows(data.get("wa_chat"))
    exts, sent, calls = _rows(data.get("call_extractions")), _rows(data.get("enquiries_sent")), _rows(data.get("calls_made"))
    convs = _rows(data.get("conversations"))
    seller_names = seller_names or {}

    cold = not (acts or wac or exts or sent or calls or convs)
    name = gc.get("first_name", "").title() or prof.get("company_name") or "Buyer"
    city = gc.get("city") or prof.get("seller_city") or ""
    title = f"# Buyer {glid} — {name}" + (f", {city}" if city else "")
    lang, lang_src = _language([], exts, convs)

    snap = [f"- status: {'cold_start (no buying activity in lookback windows)' if cold else 'active'}",
            f"- language: {lang} ({lang_src})"]
    if prof.get("company_name") or gc.get("company"):
        snap.append(f"- business_buyer: yes — also sells {prof.get('top_category_1') or 'on IndiaMART'} as {gc.get('company') or prof.get('company_name')}")
    if prof:
        ok = [n for n, f in [("mobile", "mobile_verified_flag"), ("email", "email_verified_flag"), ("GST", "gst_verified_flag")] if _flag(prof.get(f))]
        snap.append(f"- kyc: {', '.join(k + ' ✓' for k in ok) or 'none verified'}")

    # requirements posted (WhatsApp chatbot / BL activity)
    reqs = []
    for s in _wa_sessions(wac, 10):
        prod = _requirement(s["reply"]) or (s["typed"] if any("BL" in i for i in s["intents"]) else "")
        if prod:
            reqs.append((s["ts"], "whatsapp", prod))
    for a in acts:
        if a["type"] == "BL" and a.get("keyword"):
            reqs.append((a["ts"], "buy-lead", a["keyword"]))
    reqs.sort(key=lambda x: x[0], reverse=True)

    # Open threads
    threads = _request_threads(_rows(data.get("requests")), width) + \
        [f"- [{ch} {_d(ts)}, {_ago(ts)}] {_clip(t, width)}" for ts, ch, t in _thread_state(convs)]
    if reqs and _age_days(reqs[0][0]) <= 21:
        threads.append(f"- [{reqs[0][1]} {_d(reqs[0][0])}, {_ago(reqs[0][0])}] Posted requirement: {_clip(reqs[0][2], 60)} — share matching sellers / quotes")
    c2c = [a for a in acts if a["type"] in ("C2C", "ENQ") and a.get("seller_glid")]
    if c2c:
        a = c2c[-1]
        threads.append(f"- [{a['type'].lower()} {_d(a['ts'])}, {_ago(a['ts'])}] Contacted {seller_names.get(a['seller_glid'], 'a seller')} — ask how it went")
    if exts:
        e = exts[-1]["payload"]
        if e.get("intent") == "requirement" and _age_days(exts[-1]["ts"]) <= 30:
            threads.append(f"- [call {_d(exts[-1]['ts'])}, {_ago(exts[-1]['ts'])}] Was sourcing {_clip(e.get('products'), 50)} by phone")
    threads = threads[: caps["open_threads"]]

    # Known facts: specs/prices from the latest sourcing calls, then bot write-backs (newer wins)
    fe = []
    for x in exts[-1:]:
        p = x["payload"]
        f = {"product": p.get("products")} if p.get("products") else {}
        f.update(_spec_facts(p.get("specs")))
        if p.get("prices"):
            f["price_quoted"] = p["prices"]
        fe.append((x["ts"], "call", f))
    fe += [(c["ts"], c["payload"].get("channel", "bot"), c["payload"].get("facts", {})) for c in convs]
    fe.sort(key=lambda x: x[0])
    facts = _facts(fe, caps["facts"])

    req_lines = [f"- {_d(ts)} | {_clip(p, 50)} | {ch}" for ts, ch, p in reqs[: caps["requirements"]]]

    # Searches & browsing
    cats = Counter(a["category"] for a in acts if a["type"] in ("Search", "Browse") and a.get("category"))
    kws = list({unquote(a["keyword"]).strip().lower(): unquote(a["keyword"]).strip()
                for a in reversed(acts) if a["type"] == "Search" and a.get("keyword")}.values())
    search_lines = [f"- {c} ×{n}" for c, n in cats.most_common(caps["searches"])]
    if kws:
        search_lines.append(f"- recent searches: {', '.join(_clip(k, 40) for k in kws[:6])}")
    if not acts and not gc:
        search_lines = ["- unavailable (live API not fetched for this GLID)"]

    # Sellers contacted
    sellers = OrderedDict()
    for a in acts:
        if a["type"] in ("C2C", "ENQ") and a.get("seller_glid"):
            sellers[a["seller_glid"]] = (a["ts"], a["type"])
    for e in sent:
        sellers[e["counterpart_glid"]] = (e["ts"], f"enquiry: {_clip(e['payload'].get('product'), 30)}")
    for c in calls:
        sellers[c["counterpart_glid"]] = (c["ts"], f"call {c['payload'].get('status', '').lower()}")
    sellers.pop(str(glid), None)                     # own listing: not a "seller contacted"
    ranked = sorted(sellers.items(), key=lambda kv: kv[1][0], reverse=True)
    named = [(g, v) for g, v in ranked if g in seller_names][: caps["sellers"]]
    seller_lines = [f"- {seller_names[g]} — {how} {_d(ts)}" for g, (ts, how) in named]
    if sellers:
        how = Counter(v[1].split(":")[0].split(" ")[0] for v in sellers.values())
        seller_lines.append(f"- total: {len(sellers)} sellers ({', '.join(f'{k} {n}' for k, n in how.most_common())}), "
                            f"last {_d(ranked[0][1][0])}")

    # Sourcing calls (AI-extracted, buyer side)
    call_lines = [f"- {_d(x['ts'])} | {_clip(x['payload'].get('products'), 40)} | "
                  f"{_clip(x['payload'].get('specs') or '-', 60)} | {x['payload'].get('prices') or '-'}"
                  for x in list(reversed(exts))[:3]]

    conv = [(c["ts"], c["payload"].get("channel", "bot"), c["payload"].get("summary", "")) for c in convs]
    for s in _wa_sessions(wac, 3):
        prod = _requirement(s["reply"])
        conv.append((s["ts"], "whatsapp bot", f"{', '.join(_clean_intent(i) for i in s['intents'][:2])}" + (f" → {prod}" if prod else "")))
    conv.sort(key=lambda x: x[0], reverse=True)
    conv_lines = [f"- {_d(ts)} ({_ago(ts)}) {ch}: {_clip(scrub(s), width)}" for ts, ch, s in conv[: caps["conversations"]]]

    eng = []
    alla = [a["ts"] for a in acts] + [x["ts"] for x in wac + exts + sent + calls + convs]
    if alla:
        types = Counter(a["type"] for a in acts)
        eng = [f"- last_active: {_d(max(alla))} ({_ago(max(alla))})",
               f"- activity_{LOOKBACK_DAYS['buyer_activity']}d: " + (", ".join(f"{t} {n}" for t, n in types.most_common()) or "n/a"),
               f"- sourcing_calls_{LOOKBACK_DAYS['call_extractions']}d: {len(exts)} | requirements_posted: {len(reqs)}",
               f"- best_time: {Counter(_bucket(t) for t in alla).most_common(1)[0][0]}",
               f"- level: {_level(len(acts) / 10 + 2 * len(reqs) + 2 * len(exts) + 3 * len(convs))}"]

    body = [title,
            _section("Snapshot", snap),
            _section("Open threads (resume these first)", threads),
            _section("Known facts (do not re-ask)", facts),
            _section(f"Requirements posted ({LOOKBACK_DAYS['wa_chat']}d) — date | product | channel", req_lines),
            _section(f"Searches & browsing ({LOOKBACK_DAYS['buyer_activity']}d)", search_lines),
            _section(f"Sellers contacted ({LOOKBACK_DAYS['enquiries']}d)", seller_lines),
            _section(f"Sourcing calls ({LOOKBACK_DAYS['call_extractions']}d) — date | product | specs | price", call_lines),
            _section(f"Conversations (all channels, latest {caps['conversations']})", conv_lines),
            _section("Engagement", eng)]
    return "\n\n".join(body) + "\n", cold
