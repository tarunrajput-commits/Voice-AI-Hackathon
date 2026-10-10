"""Freshness evidence: fire real activity events at the running server and measure, from the
outside, how long until the served file reflects them.

    .venv/bin/uvicorn app:app --port 8000 &
    .venv/bin/python scripts/measure_freshness.py [N]

Two delays are reported per event:
  server  = file generated_at - event ingested_at   (pipeline delay, written into the file front matter)
  client  = time from POST /api/events returning to GET /context/<glid>/<role>.md showing the new build
Writes evidence/freshness_report.md.
"""
import json
import random
import statistics
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://localhost:8000"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        raw = r.read().decode()
        return json.loads(raw) if r.headers.get_content_type() == "application/json" else raw


def meta(md):
    out = {}
    for line in md.split("---")[1].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def epoch(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


SIM = "SIMULATED event on a real GLID"
KINDS = [
    ("enquiry → seller file", lambda: ("209139024", "seller", {"glid": "999000001", "source": "simulated.enquiries", "type": "enquiry",
                                                               "counterpart_glid": "209139024",
                                                               "payload": {"enquiry_id": f"F{random.randint(1, 10**9)}", "product": "Door Seal (sim)",
                                                                           "buyer_name": "Test", "buyer_city": "Jaipur", "read": False, "note": SIM}})),
    ("buyer call → seller file", lambda: ("239368219", "seller", {"glid": "999000002", "source": "simulated.pns_calls", "type": "pns_call",
                                                                  "counterpart_glid": "239368219",
                                                                  "payload": {"status": "Connected", "talk_sec": 95, "circle": "Madhya Pradesh"}})),
    ("WhatsApp chatbot turn", lambda: ("42559301", "seller", {"glid": "42559301", "source": "simulated.whatsapp_chatbot", "type": "wa_chat",
                                                              "role": "seller", "payload": {"session_id": f"s{random.randint(1, 10**9)}",
                                                                                            "intent": "WA_Call_Feedback", "action": "typed",
                                                                                            "user_message": "ok", "bot_reply": "Thanks"}})),
    ("VANI call outcome", lambda: ("5397256", "seller", {"glid": "5397256", "source": "simulated.vani_calls", "type": "vani_call", "role": "seller",
                                                         "payload": {"disposition": "Call Later / Busy", "summary": "Seller asked to call after 5 pm (sim)",
                                                                     "duration_s": 22}})),
    ("requirement posted → buyer file", lambda: ("209139024", "buyer", {"glid": "209139024", "source": "simulated.whatsapp_chatbot", "type": "wa_chat",
                                                                        "role": "buyer", "payload": {"session_id": f"b{random.randint(1, 10**9)}",
                                                                                                     "intent": "Msite_BL", "action": "typed",
                                                                                                     "user_message": "need foam rod",
                                                                                                     "bot_reply": "Your requirement for Foam Rod has been received."}})),
]


def main():
    for label, mk in KINDS:                    # runtime-only files: make sure each target file exists first
        glid, role, _ = mk()
        call("GET", f"/api/context/{glid}/{role}")
    rows = []
    for i in range(N):
        label, mk = KINDS[i % len(KINDS)]
        glid, role, body = mk()
        res = call("POST", "/api/events", body)
        t_posted = time.time()
        while True:
            m = meta(call("GET", f"/context/{glid}/{role}.md"))
            if epoch(m["generated_at"]) >= res["ingested_at"]:
                break
            if time.time() - t_posted > 5:
                m = None
                break
            time.sleep(0.002)
        client_ms = (time.time() - res["ingested_at"]) * 1000
        rows.append({"kind": label, "server_ms": float(m["freshness_ms"]) if m else None, "client_ms": round(client_ms, 1)})
        time.sleep(0.12)   # spread events out so each one is measured on its own (not coalesced)

    def stats(xs):
        xs = sorted(x for x in xs if x is not None)
        return statistics.median(xs), xs[max(0, -(-95 * len(xs) // 100) - 1)], xs[-1]

    s50, s95, smax = stats([r["server_ms"] for r in rows])
    c50, c95, cmax = stats([r["client_ms"] for r in rows])
    lines = ["# Freshness evidence", "",
             f"Run: {datetime.now().isoformat(timespec='seconds')} · {N} events against the live server · data: REAL GLIDs + simulated events (labelled)", "",
             "Mechanism: event-driven rebuild (50 ms debounce) plus a scheduled sweep every 15 min. "
             "**Delay = time from an event being ingested to the rebuilt file being on disk.**", "",
             "| metric | p50 | p95 | max |", "|---|---|---|---|",
             f"| pipeline (ingest → file written) | {s50:.1f} ms | {s95:.1f} ms | {smax:.1f} ms |",
             f"| observed by a reader (ingest → served file changed) | {c50:.1f} ms | {c95:.1f} ms | {cmax:.1f} ms |", "",
             "Per event type (p50 pipeline ms):", ""]
    for label, _ in KINDS:
        xs = [r["server_ms"] for r in rows if r["kind"] == label and r["server_ms"] is not None]
        if xs:
            lines.append(f"- {label}: {statistics.median(xs):.1f} ms (n={len(xs)})")
    api = []
    for g in ["209139024", "239368219", "42559301", "5397256", "12855767"]:
        try:
            api.append(call("POST", f"/api/gc/refresh/{g}"))
        except Exception as e:
            print("api refresh failed", g, e)
    if api:
        lines += ["", "Live Global Context API (pull-only, refreshed at session start / sweep / on demand):", "",
                  "| GLID refresh | generateContextUID | getContext | snapshot → file |", "|---|---|---|---|"]
        for g, a in zip(["209139024", "239368219", "42559301", "5397256", "12855767"], api):
            lines.append(f"| {g} | {a['api_ms']['generateContextUID']} ms | {a['api_ms']['getContext']} ms | {a['snapshot_to_file_ms']} ms |")
    lines += ["", "Conversation write-back (end of call → summary by sarvam-105b-conversations → file rebuilt) is measured",
              "separately in `evidence/demo_transcript.md`. It is dominated by the LLM summary (~0.5–1.5 s)."]
    out = ROOT / "evidence" / "freshness_report.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
