"""FastAPI app: bot channels (voice + WhatsApp), event ingestion, runtime context files, freshness metrics.

    .venv/bin/uvicorn app:app --port 8000
"""
import json
import re
import statistics
import threading
import time

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

from bot import agent, sarvam
from config import FEATURED, FRESHNESS_LOG, ROOT, SESSION_IDLE_END_S
from context_layer import builder, dataset, gc_api, refresher, store
from context_layer.parser import parse

app = FastAPI(title="IndiaMART Global Context")
WEB = ROOT / "web"


@app.on_event("startup")
def _startup():
    store.conn()
    from context_layer import skill
    r = skill.report()                      # skill.md drives pipeline settings + bot rules
    print(f"skill.md loaded: {r['chars']} chars, settings={r['settings']}, notes={r['notes']}")
    refresher.start(extra_tasks=[lambda: refresher.refresh_stale_gc(list(FEATURED))])

    def idle_loop():   # close abandoned chats so their summary still reaches the file
        while True:
            time.sleep(30)
            try:
                agent.end_idle_sessions(SESSION_IDLE_END_S)
            except Exception as e:
                print("idle sweep error", e)
    threading.Thread(target=idle_loop, daemon=True, name="idle-sessions").start()


# ---------------------------------------------------------------- pages
@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/voices")
def voices_page():
    return FileResponse(WEB / "voices.html")


@app.get("/voices/{name}")
def voice_sample(name: str):
    p = WEB / "voices" / name
    if not p.exists() or p.parent != WEB / "voices":
        raise HTTPException(404)
    return FileResponse(p)


class VoiceIn(BaseModel):
    model: str
    speaker: str


@app.get("/api/voice")
def get_voice():
    m, s_ = sarvam.current_voice()
    return {"model": m, "speaker": s_}


@app.post("/api/voice")
def put_voice(v: VoiceIn):
    sarvam.set_voice(v.model, v.speaker)
    return get_voice()


# ---------------------------------------------------------------- context files
def _file(glid, role):
    md = builder.read(glid, role)
    if md is None:
        return None
    d = parse(md)
    d["glid"], d["role"] = str(glid), role
    return d


def _user(glid, role, why=None):
    """One entry for the user list. Name/city from the profile CSV (or the file if it exists, which adds the contact)."""
    prof = dataset.profiles().get(glid, {})
    d = _file(glid, role)
    if d:
        title = d["title"]
    elif prof:
        title = f"{'Seller' if role == 'seller' else 'Buyer'} {glid} — {prof['company']}, {prof['city']}".rstrip(", ")
    else:
        title = f"{'Seller' if role == 'seller' else 'Buyer'} {glid} — not in the CSV dump (live API only)"
    out = {"glid": glid, "role": role, "title": title, "live_api": bool(gc_api.cached(glid)),
           "cold_start": bool(d and d["meta"].get("cold_start") == "true")}
    if why:
        out["why"] = why
    return out


@app.get("/api/users")
def users(q: str = ""):
    """Featured GLIDs by default. ?q= searches all 5,000 sellers in the profile CSV by GLID or company;
    a number that isn't in the CSV is still offered (the live APIs can build it)."""
    if not q:
        out = [_user(g, "seller", why) for g, why in FEATURED.items()]
        out.insert(1, _user("209139024", "buyer", "same GLID as a buyer"))
        return out
    ql, out = q.lower().strip(), []
    for g, p in dataset.profiles().items():
        if g.startswith(ql) or ql in p["company"].lower():
            out.append(_user(g, "seller"))
            if len(out) >= 30:
                break
    if ql.isdigit() and ql not in dataset.profiles():
        out.insert(0, _user(ql, "seller"))
    return out


@app.get("/api/context/runtime/{glid}")
def context_runtime(glid: str, role: str = "seller", use_cache: bool = False, budget_s: float = 3.0):
    """Context layer pipeline for ANY GLID, right now: 1) Global Context API (generateContextUID -> getContext),
    2) that GLID's rows from the CSV files, 3) live events, 4) merge – API wins on every conflict, 5) build .md.
    Returns the file plus per-step timings, the conflicts that were resolved and where each field came from."""
    from context_layer import pipeline
    r = pipeline.run(glid, role, api_budget_s=budget_s, use_cached_api=use_cache)
    return r


@app.post("/api/gc/refresh/{glid}")
def gc_refresh(glid: str):
    """Pull the live Global Context API snapshot now and report how long until the files reflected it."""
    t = time.time()
    f = refresher.refresh_gc(glid, wait=True)
    if not f:
        raise HTTPException(502, "Global Context API fetch failed (token expired? see server log)")
    landed = gc_api.cached(glid)["_fetch"]["fetched_at"]
    role = "seller" if (glid in dataset.profiles() or builder.path_for(glid, "seller").exists()) else "buyer"
    meta = {}
    for _ in range(200):
        meta = parse(builder.read(glid, role) or "")["meta"] if builder.read(glid, role) else {}
        if meta.get("generated_at") and _epoch(meta["generated_at"]) >= landed:
            break
        time.sleep(0.005)
    return {"api_ms": {"generateContextUID": f["uid_ms"], "getContext": f["ctx_ms"]},
            "snapshot_to_file_ms": meta.get("freshness_ms"), "total_ms": round((time.time() - t) * 1000)}


@app.get("/api/context/{glid}/{role}")
def context(glid: str, role: str):
    md = builder.read(glid, role)
    if md is None:                      # runtime-only: first look at this GLID → build it now, offline (no API calls)
        from context_layer import pipeline
        md = pipeline.rebuild(glid, role, reason="preview")["md"]
    return {"markdown": md, "parsed": parse(md)}


@app.get("/context/indiamart_domain_knowledge.md", response_class=PlainTextResponse)
def domain_knowledge():
    """The shared IndiaMART glossary / playbook the bot reads alongside buyer.md / seller.md."""
    from context_layer import domain
    return domain.PATH.read_text(encoding="utf-8")


@app.get("/api/skill")
def skill_status(text: str = ""):
    """What the system loaded from skill.md: parsed settings, notes, and the bot rules selected for an utterance."""
    from context_layer import skill
    rules, procs = skill.bot_instructions(text)
    return {**skill.report(), "for_text": text, "procedures": procs, "bot_rules_chars": len(rules)}


@app.get("/api/domain/select")
def domain_select(text: str = "", role: str = "seller", phase: str = "turn"):
    """Debug: which knowledge sections the bot would load for this utterance."""
    from context_layer import domain
    kn, found = domain.select(role, text, phase)
    return {"intents": found, "chars": len(kn), "sections": [l for l in kn.splitlines() if l.startswith("#")]}


@app.get("/context/{glid}/{role}.md", response_class=PlainTextResponse)
def context_raw(glid: str, role: str):
    """The shared asset: any team can GET the raw file (built on first request, offline, if it doesn't exist yet)."""
    md = builder.read(glid, role)
    if md is None:
        from context_layer import pipeline
        md = pipeline.rebuild(glid, role, reason="preview")["md"]
    return md


# ---------------------------------------------------------------- events (new activity)
class EventIn(BaseModel):
    glid: str
    source: str
    type: str
    payload: dict
    counterpart_glid: str | None = None
    role: str | None = None
    ts: str | None = None


@app.post("/api/events")
def ingest(ev: EventIn):
    return refresher.ingest(ev.glid, ev.source, ev.type, ev.payload, ts=ev.ts,
                            counterpart_glid=ev.counterpart_glid, role=ev.role)


@app.get("/api/freshness")
def freshness():
    recs = []
    if FRESHNESS_LOG.exists():
        recs = [json.loads(l) for l in FRESHNESS_LOG.read_text().splitlines() if l.strip()]
    ev = [r["freshness_ms"] for r in recs if r.get("freshness_ms") is not None]
    stats = {}
    if ev:
        s = sorted(ev)
        stats = {"n": len(s), "p50_ms": round(statistics.median(s), 1), "p95_ms": round(s[max(0, -(-95 * len(s) // 100) - 1)], 1),
                 "max_ms": round(s[-1], 1)}
    return {"stats": stats, "recent": recs[-15:][::-1]}


@app.post("/api/simulate/{glid}/{role}")
def simulate(glid: str, role: str):
    """Fire a realistic new activity for this user (for the live freshness demo) and wait for the file."""
    from context_layer import pipeline
    if builder.read(glid, role) is None:
        pipeline.rebuild(glid, role, reason="preview")
    if role == "buyer":
        ev = refresher.ingest(glid, "simulated.whatsapp_chatbot", "wa_chat",
                              {"session_id": f"sim-{int(time.time())}", "intent": "Msite_BL", "action": "typed",
                               "user_message": "50 kg packing material chahiye", "feedback": "",
                               "bot_reply": "Thank you! Your requirement for Stretch Wrap Film has been received."}, role="buyer")
        label = "SIMULATED: posted a WhatsApp requirement for Stretch Wrap Film"
    else:
        n = len(store.query("SELECT id FROM events WHERE counterpart_glid=? AND type='enquiry'", (glid,)))
        ev = refresher.ingest("999000001", "simulated.enquiries", "enquiry",
                              {"enquiry_id": f"SIM-{glid}-{n}", "product": "Bulk order (simulated)", "buyer_name": "Kavita",
                               "buyer_city": "Nashik", "message": "Need 100 pcs, please share price", "read": False},
                              counterpart_glid=glid)
        label = "SIMULATED: new enquiry from Kavita, Nashik"
    for _ in range(200):
        meta = parse(builder.read(glid, role))["meta"]
        if meta.get("generated_at") and _epoch(meta["generated_at"]) >= ev["ingested_at"]:
            break
        time.sleep(0.005)
    e2e = round((time.time() - ev["ingested_at"]) * 1000, 1)
    return {"activity": label, "freshness_ms": meta.get("freshness_ms"), "observed_ms": e2e,
            "generated_at": meta.get("generated_at")}


# ---------------------------------------------------------------- bot sessions
class StartIn(BaseModel):
    glid: str
    role: str = "seller"
    channel: str = "voice"
    direction: str | None = None     # voice defaults to outbound (VANI calls the seller); chat/WhatsApp to inbound
    speak: bool = True


@app.post("/api/session/start")
def session_start(body: StartIn):
    t = time.time()
    from context_layer import pipeline
    ctx = pipeline.run(body.glid, body.role, api_budget_s=3.0)       # API first -> CSV -> merge -> .md
    api_note = f"{ctx['api']} · pipeline {ctx['timings']['total_ms']} ms"
    direction = body.direction or ("outbound" if body.channel == "voice" else "inbound")
    md = builder.read(body.glid, body.role)
    if md and direction == "outbound" and agent.is_do_not_call(parse(md)):
        raise HTTPException(409, "DO-NOT-CALL: this seller asked not to be called. Outbound call blocked; "
                                 "start it as an inbound call or use WhatsApp if they message us.")
    s = agent.start_session(body.glid, body.role, body.channel, direction)
    opening = s.opening()
    llm_ms = round((time.time() - t) * 1000)
    audio = None
    if body.channel == "voice" and body.speak:
        try:
            audio = sarvam.tts(opening, s.language)
        except Exception as e:
            print("tts error", e)
    return {"session_id": s.id, "opening": opening, "cold_opening": s.cold_opening(), "cold_start": s.cold,
            "audio": audio, "context_generated_at": s.meta.get("generated_at"), "opening_ms": llm_ms, "live_api": api_note}


class MsgIn(BaseModel):
    text: str
    speak: bool = True
    interrupted: bool = False      # the caller talked over / cut off the bot's previous reply


def _sess(sid):
    s = agent.get(sid)
    if not s or s.ended:
        raise HTTPException(404, "session not found or ended")
    return s


@app.post("/api/session/{sid}/message")
def session_message(sid: str, body: MsgIn):
    s = _sess(sid)
    if body.interrupted:
        s.mark_interrupted()
    n_before = len(s.actions)
    reply, changed = s.reply(body.text)
    audio = None
    if s.channel == "voice" and body.speak:
        try:
            audio = sarvam.tts(reply, s.language)
        except Exception as e:
            print("tts error", e)
    return {"reply": reply, "audio": audio, "context_changed": changed, "end_call": s.end_requested,
            "actions": s.actions[n_before:]}


_CODECS = {"webm": "webm", "ogg": "ogg", "mp4": "mp4", "m4a": "x-m4a", "mpeg": "mp3", "mp3": "mp3", "wav": "wav", "x-wav": "wav"}


@app.post("/api/session/{sid}/audio")
async def session_audio(sid: str, file: UploadFile = File(...), interrupted: str = Form("0")):
    """One spoken turn from the browser mic: Saaras STT -> bot reply (with the caller's .md) -> Bulbul TTS (voice only).
    interrupted=1: the caller barged in over the bot's previous reply (or it was never played)."""
    s = _sess(sid)
    if interrupted in ("1", "true"):
        s.mark_interrupted()
    data = await file.read()
    ctype = (file.content_type or "").split(";")[0].split("/")[-1].lower()
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    codec = _CODECS.get(ctype) or _CODECS.get(ext)
    t0 = time.time()
    try:
        transcript, lang = sarvam.stt(data, file.filename or f"turn.{ext or 'webm'}", codec)
    except Exception as e:
        print("stt error", e)
        raise HTTPException(502, f"Speech-to-text failed: {str(e)[:120]}")
    t1 = time.time()
    if not transcript.strip():
        return {"transcript": "", "reply": "", "audio": None, "timings": {"stt_ms": round((t1 - t0) * 1000)}}
    n_before = len(s.actions)
    reply, changed = s.reply(transcript)
    t2 = time.time()
    audio = None
    if s.channel == "voice":                    # WhatsApp voice notes get a text reply
        try:
            audio = sarvam.tts(reply, lang if lang != "unknown" else s.language)
        except Exception as e:
            print("tts error", e)
    t3 = time.time()
    return {"transcript": transcript, "language": lang, "reply": reply, "audio": audio, "context_changed": changed,
            "end_call": s.end_requested, "actions": s.actions[n_before:], "timings": {"stt_ms": round((t1 - t0) * 1000), "llm_ms": round((t2 - t1) * 1000),
                        "tts_ms": round((t3 - t2) * 1000) if audio else 0}}


@app.post("/api/session/{sid}/end")
def session_end(sid: str):
    s = agent.get(sid)
    if not s:
        raise HTTPException(404)
    res = s.end()
    if not res:
        return {"summary": None}
    # wait for the event-driven rebuild and report the measured delay end-to-end
    ing = res["event"]["ingested_at"]
    for _ in range(100):
        meta = parse(builder.read(s.glid, s.role))["meta"]
        gen = meta.get("generated_at", "")
        if gen and _epoch(gen) >= ing:
            break
        time.sleep(0.01)
    return {"summary": res["summary"], "freshness_ms": meta.get("freshness_ms"), "generated_at": meta.get("generated_at")}


def _epoch(iso):
    from datetime import datetime
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


# ---------------------------------------------------------------- WhatsApp webhook (Meta Cloud API shape)
@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(req: Request):
    """Plugs a real WhatsApp Business number in: resolves the sender to a GLID, keeps one session per
    sender, replies with the bot. (Sending the reply back via Graph API needs WHATSAPP_TOKEN; here we
    return it in the response body so the flow can be tested with curl.)"""
    body = await req.json()
    try:
        msg = body["entry"][0]["changes"][0]["value"]["messages"][0]
        sender, text = msg["from"], msg["text"]["body"]
    except (KeyError, IndexError):
        return {"status": "ignored"}
    glid = store.glid_for(f"whatsapp:+{sender.lstrip('+')}")
    if not glid:
        return {"reply": agent.COLD_OPENINGS[("buyer", "hi-IN")], "glid": None}
    role = "seller" if glid in dataset.profiles() else "buyer"
    s = next((x for x in agent.SESSIONS.values() if x.glid == glid and x.channel == "whatsapp" and not x.ended), None)
    if s is None:
        from context_layer import pipeline
        pipeline.run(glid, role)                      # APIs first -> CSV -> merge -> .md, same as calls
        s = agent.start_session(glid, role, "whatsapp")
        opening = s.opening()
        reply, _ = s.reply(text)
        return {"glid": glid, "reply": opening + "\n\n" + reply}
    reply, _ = s.reply(text)
    return {"glid": glid, "reply": reply}
