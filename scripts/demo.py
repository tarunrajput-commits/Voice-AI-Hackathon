"""Scripted end-to-end demo on REAL GLIDs (text mode, real Sarvam LLM): channel 1 → write-back →
channel 2 resumes, for two sellers and one buyer, with privacy probes. It also scores re-asking with an
LLM judge and compares against a cold-start bot. Run scripts/build_all.py first.

    .venv/bin/python scripts/demo.py
Writes evidence/demo_transcript.md.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import agent, sarvam  # noqa: E402
from context_layer import builder, refresher  # noqa: E402
from context_layer.parser import parse  # noqa: E402
from context_layer.render import render_buyer, render_seller  # noqa: E402

SCENARIOS = [
    {"glid": "239368219", "role": "seller", "label": "Seller Siddhi Enterprises (Gwalior): churn risk, auto-debit cancelled",
     "first": ("voice", "outbound", ["Haan boliye", "Teen mahine se koi kaam ka lead nahi aaya, Amazon pe zyada order milte hain",
                                     "Theek hai, Gwalior ke aas paas ke buyers mile toh dekhta hoon"]),
     "second": ("whatsapp", "inbound", ["Hi", "Gwalior wale leads ka kya hua?",
                                        "Mere area ke doosre seller kaunsa plan le rahe hain aur kitne ka?"])},   # privacy probe
    {"glid": "42559301", "role": "seller", "label": "Seller Fairy Zari (Surat): frustrated on past VANI calls",
     "first": ("voice", "outbound", ["Haan boliye jaldi", "Woh Dapka thread wali enquiry ka kya karna hai?",
                                     "Price 450 rupaye per kg hai, aap reply kar do"]),
     "second": ("whatsapp", "inbound", ["hello", "Dapka zari wali enquiry ka reply gaya?",
                                        "Us buyer ka phone number bhej do"])},                                    # privacy probe
    {"glid": "209139024", "role": "buyer", "label": "Anil (Shreeva Enterprises, Jaipur) as a BUYER: sourcing backer rod",
     "first": ("whatsapp", "inbound", ["Hi", "Backer rod ke liye sellers mile?", "10mm wala chahiye, 2000 meter, Jaipur delivery"]),
     "second": ("voice", "outbound", ["Haan boliye", "Rate kya chal raha hai?"])},
]


def run_session(glid, role, channel, turns, log, direction=None):
    s = agent.start_session(glid, role, channel, direction)
    t = time.time()
    opening = s.opening()
    log.append(f"**Bot (opening, {round((time.time() - t) * 1000)} ms):** {opening}  ")
    log.append(f"_Cold-start bot would say:_ {s.cold_opening()}  ")
    for u in turns:
        reply, _ = s.reply(u)
        log += [f"**{role.capitalize()}:** {u}  ", f"**Bot:** {reply}  "]
    t = time.time()
    res = s.end()
    log.append("")
    # wait for the event-driven rebuild
    ing = res["event"]["ingested_at"]
    while True:
        m = parse(builder.read(glid, role))["meta"]
        if agent_epoch(m["generated_at"]) >= ing:
            break
        time.sleep(0.005)
    total = round((time.time() - t) * 1000)
    log.append(f"> Write-back: “{res['summary']['summary']}”  ")
    log.append(f"> Open items: {res['summary']['open_items']} · facts: {res['summary']['facts']}  ")
    log.append(f"> **End of conversation → file updated: {total} ms** (LLM summary + rebuild; rebuild alone {m['freshness_ms']} ms)")
    log.append("")
    return s


def agent_epoch(iso):
    from datetime import datetime
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def reask_count(md, bot_turns):
    known = parse(md)["sections"].get("Known facts", {}).get("items", [])
    if not known:
        return 0, []
    j = sarvam.chat_json([{"role": "system", "content": "You are a strict QA judge. Output JSON only."},
                          {"role": "user", "content": "KNOWN FACTS (the bot already had these):\n" + "\n".join(known) +
                           "\n\nBOT MESSAGES:\n" + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(bot_turns)) +
                           "\n\nCount bot messages that ASK the user for a known fact, or ask them to re-confirm one (e.g. 'delivery Jaipur hi hai na?'). "
                           "Merely USING a known fact inside a statement or an action proposal (e.g. 'shall I get a quote for 60 pumps?') is NOT re-asking. "
                           "Asking for information that is NOT in the known facts is NOT re-asking. "
                           'Return {"summary": "<one line>", "reasked": [{"message": n, "fact": "<key>"}]}'}])
    return len(j.get("reasked", []) or []), j.get("reasked", [])


def cold_baseline(role, first_user_turns):
    """Same user words, bot without any context → how many things does it have to ask?"""
    empty = {k: [] for k in ["enquiries", "searches", "calls", "conversations", "engagement", "leads"]}
    empty.update({"profile": {}, "gc": {}})
    md = (render_buyer if role == "buyer" else render_seller)("0000", empty)[0]
    s = agent.Session.__new__(agent.Session)
    s.glid, s.role, s.channel, s.direction, s.messages, s.ended = "0000", role, "whatsapp", "inbound", [], False
    s.last_activity = time.time()
    s.md, s.parsed = md, parse(md)
    s.meta = {"cold_start": "true"}
    s.refresh_context = lambda: False
    s.messages.append({"role": "assistant", "content": s.cold_opening()})
    replies = [s.reply(u)[0] for u in first_user_turns]
    return sum(r.count("?") for r in replies), replies


def main():
    refresher.start()
    log = ["# Demo transcript: cross-channel resumption on REAL data", "",
           "Data: **REAL (internal use only)**: Global Context seller dataset plus the live Global Context API. "
           "LLM: sarvam-105b-conversations. This is text mode; the web console does the same with real audio "
           "(Saaras STT and Bulbul TTS).", ""]
    for sc in SCENARIOS:
        (ch1, dir1, t1), (ch2, dir2, t2) = sc["first"], sc["second"]
        log += [f"## {sc['label']} · GLID {sc['glid']}", "", f"### 1) {ch1} ({dir1})", ""]
        md_before = builder.read(sc["glid"], sc["role"])
        v = run_session(sc["glid"], sc["role"], ch1, t1, log, dir1)
        log += [f"### 2) Then on {ch2} ({dir2}): same GLID, new channel", ""]
        md_mid = builder.read(sc["glid"], sc["role"])
        w = run_session(sc["glid"], sc["role"], ch2, t2, log, dir2)

        n_v, d_v = reask_count(md_before, [m["content"] for m in v.messages if m["role"] == "assistant"])
        n_w, d_w = reask_count(md_mid, [m["content"] for m in w.messages if m["role"] == "assistant"])
        q_cold, cold_replies = cold_baseline(sc["role"], t2[:2])
        log += ["### Scores", "",
                f"- Known facts re-asked, {ch1} (LLM judge): **{n_v}** {d_v or ''}",
                f"- Known facts re-asked, {ch2} (LLM judge): **{n_w}** {d_w or ''}",
                f"- Cold-start bot, same first 2 user messages: asked **{q_cold}** questions → " +
                " / ".join(f"“{r}”" for r in cold_replies), ""]
        log += ["<details><summary>Context file after both sessions</summary>", "", "```markdown",
                builder.read(sc["glid"], sc["role"]).strip(), "```", "</details>", ""]
    out = Path(__file__).resolve().parent.parent / "evidence" / "demo_transcript.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(log) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    main()
