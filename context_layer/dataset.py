"""The Global Context seller dataset (CSV exports that stand in for the source APIs).

One converter per CSV turns a row into normalised event(s). csv_index.read() uses them at runtime to read
only one GLID's rows straight from the CSV files (by byte offset). Nothing from the CSVs is copied into
the event store; it only holds live events (bot write-backs, callback/meeting requests, POSTed activity).

Event types (glid = actor, counterpart = other party, role = which file it feeds):
  seller_profile      seller   state (profile, KYC flags, engagement aggregates, VANI history flags)
  enquiry             buyer→seller   enquiry a buyer sent (feeds the seller's file and the buyer's)
  enquiry_message     seller   message inside an enquiry thread (buyer or seller side)
  pns_call            buyer→seller   buyer phone call to the seller
  buylead_bought      seller   buy-lead purchased
  wa_message          seller   WhatsApp delivery/read status (engagement only)
  wa_chat             buyer|seller   WhatsApp chatbot turn (requirement posts → buyer; rest → seller)
  call_extraction     buyer|seller   AI-extracted PNS call details (role from seller_role_on_call)
  vani_call           seller   answered VANI bot call (summary, disposition)
  vani_turns          seller   turn-by-turn transcript of a VANI call
  exec_call           seller   IndiaMART executive call attempt
"""
import csv
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from config import ROOT

DATASET_DIR = ROOT / "Global Context - Seller Dataset"
IST = timezone(timedelta(hours=5, minutes=30))
S = "dataset"
csv.field_size_limit(10 ** 9)

BUYER_INTENTS = re.compile(r"^(Msite_BL|liveCustomer_Buyer|Buy_Product|Delete BuyLead)", re.I)
PROFILE_KEEP = [
    "seller_city", "seller_state", "business_type", "annual_turnover", "nature_of_business", "gst_registration_year",
    "top_category_1", "top_category_2", "top_category_3", "top_parent_category", "num_categories",
    "eng_activity_30d", "eng_pickup_ratio_90d", "eng_enq_received_90d", "eng_enq_replies_90d", "eng_pns_received_90d",
    "eng_pns_answered_90d", "eng_product_count", "eng_products_modified_90d", "eng_cqs", "eng_meetings_1yr",
    "bot_attempts", "bot_answered", "bot_answer_rate", "calls_meeting_fixed", "calls_not_interested", "calls_call_later",
    "avg_answered_call_sec", "past_objections", "past_questions_asked", "asked_if_talking_to_bot", "showed_frustration",
    "past_dispositions_detailed", "already_in_touch_with_executive", "do_not_call_requested", "company_name",
    "customer_type", "is_paid", "listing_status", "mobile_verified_flag", "email_verified_flag", "gst_verified_flag",
    "is_pan_number_available"]


def _ts(s):
    """Dataset timestamps are IST wall-clock -> ISO UTC."""
    s = (s or "").strip()
    if not s:
        return None
    s = s.split(".")[0]
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST).astimezone(timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        return None


def _clip(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _buyer_first(subject):
    m = re.search(r" from (.+?) via IndiaMART", subject or "")
    return m.group(1).split(" ")[0].title() if m else ""


# ---------------------------------------------------------------------------------------------
# Row converters: row dict -> event tuple (glid, counterpart, role, source, type, ts, payload) or None
# ---------------------------------------------------------------------------------------------
def c_profile(r):
    return (r["fk_glusr_usr_id"], None, "seller", f"{S}.profile", "seller_profile", "2026-10-02T00:00:00+00:00",
            {k: r.get(k, "") for k in PROFILE_KEEP})


def c_enquiry(r):
    ts = _ts(r["enquiry_date"])
    return ts and (r["buyer_glid"], r["seller_glid"], None, f"{S}.enquiries", "enquiry", ts, {
        "enquiry_id": r["query_id"], "product": _clip(r["product_name"] or r["subject"], 60),
        "buyer_name": _buyer_first(r["subject"]), "buyer_city": r["buyer_city"], "buyer_state": r["buyer_state"],
        "message": _clip(r["message"], 100), "read": bool(r["first_read_date"]), "first_read": _ts(r["first_read_date"]),
        "source_module": r["source_module"]})


def c_enquiry_message(r):
    ts = _ts(r["reply_date"])
    other = r["receiver_glid"] if r["message_from"] == "seller" else r["sender_glid"]
    return ts and (r["seller_glid"], other, "seller", f"{S}.enquiry_messages", "enquiry_message", ts, {
        "enquiry_id": r["query_id"], "from": r["message_from"], "text": _clip(r["reply_text"], 120),
        "template": r["template_flag"]})


def c_pns(r):
    ts = _ts(r["call_datetime"])
    return ts and (r["buyer_glid"], r["seller_glid"], None, f"{S}.pns_calls", "pns_call", ts, {
        "status": r["call_status"], "talk_sec": int(r["talk_sec"] or 0), "circle": r["caller_circle"]})


def c_buylead(r):
    ts = _ts(r["purchase_date"])
    return ts and (r["seller_glid"], r["buyer_glid"], "seller", f"{S}.buyleads", "buylead_bought", ts, {
        "keyword": _clip((r["keyword"] or "").split("_p")[0], 50), "credits": int(float(r["credits_used"] or 0)),
        "mode": r["purchase_mode"], "distance_km": round(float(r["distance_city"] or 0))})


def c_wa_message(r):
    ts = _ts(r["entry_date"])
    return ts and (r["glid"], None, "seller", f"{S}.whatsapp", "wa_message", ts, {
        "sender": r["message_sender"], "status": (r["message_status"] or "").lower(), "campaign": r["campaign_name"]})


def c_wa_chat(r):
    ts = _ts(r["entry_date"])
    role = "buyer" if BUYER_INTENTS.match(r["intent"] or "") else "seller"
    return ts and (r["glid"], None, role, f"{S}.whatsapp_chatbot", "wa_chat", ts, {
        "session_id": r["session_id"], "intent": r["intent"], "action": r["action_type"],
        "user_message": _clip(r["user_message"], 120), "bot_reply": _clip(r["bot_reply"], 140),
        "feedback": r["feedback"], "source": r["source"]})


def c_extraction(r):
    ts = _ts(r["call_date"])
    role = "buyer" if r["seller_role_on_call"] == "BUYER" else "seller"
    return ts and (r["glid"], None, role, f"{S}.call_extractions", "call_extraction", ts, {
        "intent": r["file_intent"], "products": _clip(r["products_discussed"], 80), "categories": _clip(r["categories"], 60),
        "prices": _clip(r["prices_quoted"], 60), "specs": _clip(r["specs_discussed"], 120), "stock": r["stock_status"],
        "languages": r["languages"], "duration_s": int(float(r["file_duration_sec"] or 0)), "b2b": r["is_b2b"] == "True"})


def c_vani(r):
    ts = _ts(r["call_start_time"])
    return ts and (r["fk_glusr_usr_id"], None, "seller", f"{S}.vani_calls", "vani_call", ts, {
        "attempt_id": r["attempt_id"], "disposition": r["disposition_label"], "summary": _clip(r["lead_call_summary"], 220),
        "duration_s": int(float(r["lead_call_duration"] or 0)), "meeting_fixed": r["meeting_fixed"] == "1",
        "bot_version": r["lead_bot_version"]})


def c_exec(r):
    ts = _ts(r["call_start_time"])
    return ts and (r["fk_glusr_usr_id"], None, "seller", f"{S}.exec_calls", "exec_call", ts, {
        "status": r["status"], "module": r["module"], "talk_s": int(float(r["call_duration_customer"] or 0))})


def turns_events(turn_rows, call_ts):
    """VANI transcript rows -> one vani_turns event per call (needs the call's timestamp from gc_bot_calls)."""
    turns, owner = defaultdict(list), {}
    for r in turn_rows:
        turns[r["attempt_id"]].append((int(r["turn_no"] or 0), r["speaker"], _clip(r["text"], 160)))
        owner[r["attempt_id"]] = r["fk_glusr_usr_id"]
    return [(owner[a], None, "seller", f"{S}.vani_turns", "vani_turns", call_ts.get(a, "2026-09-30T00:00:00+00:00"),
             {"attempt_id": a, "turns": [(s, t) for _, s, t in sorted(v)]}) for a, v in turns.items()]


# file -> (GLID key columns to index on, converter)
FILES = {
    "gc_seller_profile.csv":                 (["fk_glusr_usr_id"], c_profile),
    "gc_enquiries_received.csv":             (["seller_glid", "buyer_glid"], c_enquiry),
    "gc_enquiry_messages.csv":               (["seller_glid"], c_enquiry_message),
    "gc_buyer_calls_received.csv":           (["seller_glid", "buyer_glid"], c_pns),
    "gc_buyleads_bought.csv":                (["seller_glid"], c_buylead),
    "gc_whatsapp_messages.csv":              (["glid"], c_wa_message),
    "gc_whatsapp_chatbot_conversations.csv": (["glid"], c_wa_chat),
    "gc_buyer_call_extractions.csv":         (["glid"], c_extraction),
    "gc_bot_calls.csv":                      (["fk_glusr_usr_id"], c_vani),
    "gc_bot_call_turns.csv":                 (["fk_glusr_usr_id"], None),     # grouped per call by turns_events()
    "gc_executive_calls.csv":                (["fk_glusr_usr_id"], c_exec),
}


def _rows(name):
    with open(DATASET_DIR / name, encoding="utf-8") as f:
        yield from csv.DictReader(f)


_profiles = None


def profiles():
    """GLID -> {company, city, state, category} from gc_seller_profile.csv (read once, ~5k rows).
    Used for the user list / search and to name sellers in buyer.md – no copy of the dataset is stored."""
    global _profiles
    if _profiles is None:
        _profiles = {r["fk_glusr_usr_id"]: {"company": r.get("company_name", ""), "city": r.get("seller_city", ""),
                                            "state": r.get("seller_state", ""), "category": r.get("top_category_1", "")}
                     for r in _rows("gc_seller_profile.csv")} if DATASET_DIR.exists() else {}
    return _profiles
