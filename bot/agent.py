"""The bot: loads the caller's context file, opens with a personalised line, answers without
re-asking known facts, and at the end writes a conversation summary back to the event store –
which triggers a rebuild so the *next* channel resumes where this one stopped."""
import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from bot import sarvam
from config import BOT_NAME
from context_layer import domain, skill
from bot import actions
from context_layer import builder, refresher, store
from context_layer.parser import parse
from context_layer.privacy import safe_facts, scrub

IST = timezone(timedelta(hours=5, minutes=30))
SESSIONS = {}
_lock = threading.Lock()

CHANNEL_STYLE = {
    "voice": ("This is a live PHONE CALL. Reply in at most 2 short spoken sentences. No markdown, no lists, no emojis. "
              "If the user's language is Hindi, write Hindi in Devanagari script (English product words are fine) so "
              "text-to-speech sounds natural."),
    "whatsapp": ("This is a WhatsApp chat. Reply in 1–3 short lines. If the user's language is Hindi, write Hinglish in "
                 "Roman script. At most one emoji. No headings."),
    "chat": "This is web/app chat. Reply in 1–3 short lines.",
}

COLD_OPENINGS = {
    ("buyer", "hi-IN"): "Namaste! Main IndiaMART assistant bol rahi hoon. Bataiye, aaj aap kya khareedna chahte hain?",
    ("buyer", "en-IN"): "Hello! I'm the IndiaMART assistant. What are you looking to buy today?",
    ("seller", "hi-IN"): "Namaste! Main IndiaMART seller assistant hoon. Bataiye, aaj main aapki kis cheez mein madad karun?",
    ("seller", "en-IN"): "Hello! I'm the IndiaMART seller assistant. How can I help your business today?",
}


def _system_prompt(role, channel, md, direction="outbound", knowledge="", skill_rules=""):
    musts = care_directives(parse(md))
    direction_note = ("This is an OUTBOUND call: you called them." if channel == "voice" and direction == "outbound" else
                      "They contacted IndiaMART (inbound): thank them for reaching out and ask how you can help; bring up open threads "
                      "only if relevant to what they ask." if direction == "inbound" else "")
    if musts:
        direction_note += "\nMUST (from Handle with care): " + " ".join(musts)
    today = datetime.now(IST).strftime("%A, %d %b %Y")
    other = "seller" if role == "buyer" else "buyer"
    purpose = ("You help sellers get more business from IndiaMART: respond to their enquiries and buyer calls, fix catalog gaps "
               "(prices, photos), use buy-leads, resolve service issues, and – only when appropriate – set up a meeting with "
               "an IndiaMART executive about paid plans."
               if role == "seller" else
               "You help buyers source products: understand the requirement, connect them with suitable verified sellers, "
               "follow up on quotes and calls.")
    return f"""You are {BOT_NAME}, IndiaMART's AI assistant (female – in Hindi use feminine forms: "bol rahi hoon", "karti hoon"),
talking to a {role.upper()} on {channel}. Today is {today} (IST). {purpose}

Below is this {role}'s context file. It is everything you know. Use it actively:
0. "Handle with care" OVERRIDES everything: respect do-not-call (no pitching), apologise once and be brief if they were
   frustrated before, say you are an AI assistant if they have asked before, don't re-pitch if an executive already handles
   them, and acknowledge open complaints / cancelled auto-debit with empathy before anything else. Never repeat a pitch they
   already objected to (see past objections).
ENDING: if the user wants to end the conversation (bye, "call band karo", "baad mein baat karte hain", "bas itna hi"),
   reply with ONE short polite goodbye (mention a callback only if they asked for one) and end your reply with <END_CALL>.
   Never add <END_CALL> otherwise.
NAMES: address the user only by the name in the context file title; if there is none, use no name. Never invent names.
1. RESUME, DON'T RESTART: continue the most recent open thread. Refer to past touchpoints naturally with their channel and
   relative date (e.g. "kal executive se baat hui thi…", "last week WhatsApp par…").
2. NEVER ASK OR RE-CONFIRM anything under "Known facts" – treat it as settled and USE it. Only revisit a fact if the user
   changes it. If a fact has "(was …)", use the new value.
3. Only ask for information that is genuinely missing and needed for the next step – one question at a time.
4. PRIVACY: never reveal phone numbers, emails, addresses or ID numbers. Never share anything about another {other} or any
   other user beyond the name/city lines in this file (e.g. never reveal a buyer's budget or other enquiries to a seller,
   or other sellers' quotes). If asked, politely say you can't share that. Never COLLECT phone numbers, emails, bank or
   ID details in chat either – point the user to the IndiaMART app (Settings) for those.
5. Don't invent buyers, sellers, prices, stock or statuses that aren't in the file. For actions (sharing leads, nudging,
   updating a listing, booking an executive callback) say you are doing it / have noted it – it will be logged. Never claim
   something already happened unless the file says so.
6. Language: if the user writes/speaks, mirror their language. Before they do, use Snapshot `language`
   (hi-IN → Hindi/Hinglish, en-IN → English, otherwise simple Hinglish).
{CHANNEL_STYLE.get(channel, CHANNEL_STYLE['chat'])}
{direction_note}
The context file describes this caller. The IndiaMART domain knowledge below describes IndiaMART: use it to interpret
jargon and the caller's intent, and follow its troubleshooting steps. The current conversation decides what they need now.
Combine all three. Never read internal codes or field names aloud (GLID, mcat, CQS, NACH, listing codes) – say it simply.

<skill_rules source="skill.md">
These rules come from skill.md (§10–§11) and override the instructions above if they conflict.
Tools: transfer_to_executive, request_callback, request_meeting. Call a tool ONLY after the caller has clearly agreed.
The tool result is the only truth about what happened: report it exactly; never claim a transfer, booking, confirmed slot
or raised request that the tool did not return. Live executive hours: {_hours_text()}. It is now {_now_ist()}.
{skill_rules or "(skill.md not available)"}
</skill_rules>

<indiamart_domain_knowledge>
{knowledge or "(not available)"}
</indiamart_domain_knowledge>

<context_file>
{md}
</context_file>
{_known_reminder(md)}"""


def care_directives(parsed):
    """Turn 'Handle with care' flags into explicit, non-negotiable instructions (the LLM follows these far more
    reliably than a general rule)."""
    items = " ".join(parsed["sections"].get("Handle with care", {}).get("items", [])).lower()
    am = re.search(r"executive \(([^)]+)\)", items)
    d = []
    if "frustration" in items:
        d.append("Start with ONE short apology for earlier calls (e.g. 'pehle ke calls ke liye maafi chahti hoon') and keep every reply brief.")
    if "asked if talking to a bot" in items:
        d.append("In your first sentence say clearly that you are IndiaMART's AI assistant.")
    if "churn risk" in items:
        d.append("Acknowledge their concern (cancelled auto-debit / poor results) with empathy first. Do NOT pitch or upsell.")
    if "already in touch with an executive" in items:
        d.append(f"Refer to their executive{' ' + am.group(1).title() if am else ''} by name; do not re-pitch paid plans.")
    if "open ticket" in items:
        d.append("Acknowledge their open service ticket and say it is being followed up.")
    if "do-not-call" in items:
        d.append("They asked not to be called: no pitching at all, help only with what they ask, keep it very short.")
    if "past objections" in items:
        d.append("Do not repeat any pitch they objected to before.")
    return d


def _hours_text():
    h1, m1, h2, m2 = skill.work_hours()
    return f"{h1:02d}:{m1:02d}–{h2:02d}:{m2:02d} IST"


def _now_ist():
    return datetime.now(IST).strftime("%A %H:%M IST") + (" (inside executive hours)" if actions.in_hours() else
                                                           " (OUTSIDE executive hours)")


def _known(md):
    return parse(md)["sections"].get("Known facts", {}).get("kv", {})


def _known_reminder(md):
    k = _known(md)
    if not k:
        return ""
    return ("ALREADY KNOWN – do not ask about or re-confirm these (no \"…, right?\" / \"hai na?\" questions): "
            + ", ".join(k.keys()) + ".")


_CONFIRM_CUES = re.compile(r"(hai na|hain na|na\?|sahi hai|right\?|correct\?|confirm|है ना|हैं ना|ना\?|सही|पक्का)", re.I)


# Caller wants to end the conversation. Deliberately specific: "bas" or "theek hai" alone do NOT end a call.
_END_CALL = re.compile(
    r"\b(bye|bye bye|goodbye|good bye|alvida|tata)\b"
    r"|\b(call|phone|chat|baat)\s*(ko\s*)?(band|khatam|end|cut|disconnect|rakh)\w*"
    r"|\b(end|cut|disconnect|close|stop)\s+(the\s+|this\s+)?(call|chat|conversation)\b"
    r"|\bhang\s*up\b|\b(phone|call)\s+rakh(ta|ti|o|iye|na|do)?\b|\brakh(ta|ti)\s+hoon\b"
    r"|\bbaad\s+mein\s+(baat|call)\s+kar\w*|\bbas\s+itna\s+hi\b|\b(that'?s\s+all|nothing\s+else)\b"
    r"|बाय|अलविदा|(कॉल|फ़ोन|फोन|बात)\s*(को\s*)?(बंद|खत्म|ख़त्म|काट|रख)|रखता\s+हूँ|रखती\s+हूँ|बाद\s+में\s+(बात|कॉल)",
    re.I)
END_TOKEN = "<END_CALL>"


# Acknowledgements / back-channel: the caller is only saying "go on" – the bot should resume, not answer.
_BACKCHANNEL = re.compile(
    r"^\s*((haan|haa|ha|han|hmm+|hm+|mm+|ok|okay|achha|accha|acha|achcha|theek hai|thik hai|theek|ji|ji haan|haan ji|"
    r"yes|yeah|yep|right|sure|uh huh|bolo|boliye|bolie|go on|continue|haan boliye|ji boliye|"
    r"हाँ|हां|हा|जी|जी हाँ|हाँ जी|अच्छा|ठीक है|ठीक|हम्म|हम|ओके|बोलिए|बोलो|हाँ बोलिए)[\s.,!?।]*)+$", re.I)


def is_backchannel(text):
    return not (text or "").strip() or bool(_BACKCHANNEL.match(text.strip()))


def wants_to_end(user_text):
    return bool(_END_CALL.search(user_text or ""))


_PII_ASK = re.compile(r"(mobile|phone|contact (number|no)|whatsapp (number|no)|e-?mail|मोबाइल|फ़ोन|फोन|ईमेल|कॉन्टैक्ट नंबर"
                      r"|aadhaar|आधार|pan card|bank account|account number|ifsc)[^?]*\?", re.I)


def _asks_for_pii(text):
    return bool(_PII_ASK.search(text))


def _reconfirms_known(text, md):
    """True if a question in `text` re-confirms a value already in Known facts."""
    values = []
    for v in _known(md).values():
        v = re.sub(r"\(.*?\)", "", v).strip()
        values += [t for t in re.split(r"[,/;]| and ", v) if len(t.strip()) >= 4]
    for q in re.findall(r"[^.!?।\n]*\?", text):
        if _CONFIRM_CUES.search(q) and any(val.strip().lower() in q.lower() for val in values):
            return True
    return False


class Session:
    def __init__(self, glid, role, channel, direction="outbound"):
        self.id = uuid.uuid4().hex[:12]
        self.glid = str(glid) if glid else None          # None = unidentified caller (in-memory cold-start file)
        self.role, self.channel, self.direction = role, channel, direction
        self.end_requested = False
        self.actions = []                 # skill.md §11 tool attempts + outcomes (written back at the end)
        self.recent_procedures = []        # caller asked to end the call/chat -> UI hangs up after the goodbye
        self.recent_intents = []          # domain-knowledge routing stays on topic for follow-up turns
        self.intent_log = []
        self.messages = []           # [{"role": "user"|"assistant", "content": ...}]
        self.started = time.time()
        self.last_activity = time.time()
        self.ended = False
        self.md = self._load()
        self.loaded_at = self.meta.get("generated_at")

    # -- context ----------------------------------------------------------------------------
    def _load(self):
        md = builder.read(self.glid, self.role)
        if md is None:                               # unknown GLID -> build an (empty) cold-start file
            from context_layer import pipeline
            pipeline.rebuild(self.glid, self.role, reason="first_contact")
            md = builder.read(self.glid, self.role)
        self.parsed = parse(md)
        self.meta = self.parsed["meta"]
        return md

    def refresh_context(self):
        """Pick up file changes mid-session (e.g. a seller replied while the buyer is on the call)."""
        if self.glid is None:
            return False
        md = builder.read(self.glid, self.role)
        changed = md != self.md
        if changed:
            self.md = md
            self.parsed = parse(md)
            self.meta = self.parsed["meta"]
        return changed

    @property
    def cold(self):
        return self.meta.get("cold_start") == "true"

    @property
    def language(self):
        lang = self.parsed["sections"].get("Snapshot", {}).get("kv", {}).get("language", "unknown").split(" ")[0]
        return lang if lang not in ("unknown", "") else "hi-IN"

    # -- conversation -------------------------------------------------------------------------
    def cold_opening(self):
        return COLD_OPENINGS.get((self.role, self.language), COLD_OPENINGS[(self.role, "en-IN")])

    def opening(self):
        if self.cold:
            # clean, generic opening; personalise only with what we truly know (first name, if any)
            text = self.cold_opening()
            title = self.parsed.get("title", "")
            m = re.search(r"— ([A-Z][a-z]+)", title)
            if m and self.role == "buyer" and m.group(1) not in ("Buyer",):
                text = text.replace("Namaste!", f"Namaste {m.group(1)} ji!").replace("Hello!", f"Hello {m.group(1)}!")
        else:
            nm = self.known_first_name()
            name_rule = (f" by name as '{nm} ji'" if nm else
                         " WITHOUT any name – their name is unknown; never invent one (say just 'Namaste ji')")
            if self.direction == "inbound":
                goal = ("They reached out to IndiaMART. Greet them" + name_rule + ", thank them, then offer help "
                        "and name the single most relevant open thread in a short clause so they don't have to explain it.")
            else:
                goal = ("You are calling them. Greet them" + name_rule + ", say you're from IndiaMART, then pick up "
                        "the most recent open thread with one concrete detail (product, number, date or who they spoke to) and "
                        "the next step.")
            prompt = (f"Write ONLY your opening line for this {self.channel} {'call' if self.channel == 'voice' else 'chat'}. "
                      + goal + " Follow 'Handle with care' first. Don't ask anything listed in Known facts. Max 35 words."
                      + (" Obey these first: " + " ".join(care_directives(self.parsed)) if care_directives(self.parsed) else ""))
            try:
                knowledge, _ = domain.select(self.role, "", "opening")
                rules, _ = skill.bot_instructions("")          # skill.md §10–§11 core applies from the very first line
                text = sarvam.chat([{"role": "system", "content": _system_prompt(self.role, self.channel, self.md, self.direction,
                                                                                    knowledge, rules)},
                                    {"role": "user", "content": prompt}], max_tokens=300)
            except Exception:
                text = ""
            if not text:   # deterministic fallback built from the file itself
                threads = self.parsed["sections"].get("Open threads", {}).get("items", [])
                name = re.search(r"— ([^,(]+)", self.parsed.get("title", ""))
                t = re.sub(r"^\[[^\]]+\]\s*", "", threads[0]) if threads else "your last request"
                text = f"Namaste {name.group(1).strip() if name else ''} ji, IndiaMART se. Pichhli baar ki baat aage badhate hain: {t}."
        text = self._strip_invented_name(scrub(text))
        self.messages.append({"role": "assistant", "content": text})
        return text

    def reply(self, user_text):
        self.last_activity = time.time()
        changed = self.refresh_context()
        self.messages.append({"role": "user", "content": user_text})
        knowledge, found = domain.select(self.role, user_text, "turn", sticky=self.recent_intents)
        self.recent_intents = list(dict.fromkeys(found + self.recent_intents))[:3]
        rules, procs = skill.bot_instructions(user_text, sticky=self.recent_procedures)
        self.recent_procedures = list(dict.fromkeys(procs + self.recent_procedures))[:2]
        self.intent_log.append(found + [f"skill:{p}" for p in procs])
        msgs = [{"role": "system", "content": _system_prompt(self.role, self.channel, self.md, self.direction, knowledge, rules)}] \
            + self.messages[-16:]
        if msgs[1]["role"] == "assistant":           # API expects a user turn first after system
            msgs.insert(1, {"role": "user", "content": "(call connected)" if self.channel == "voice" else "(chat opened)"})
        # skill.md §11 actions: let the model call a tool, run it with code-enforced guardrails, feed back the result
        turn_results = []
        try:
            draft, calls = sarvam.chat_tools(msgs, actions.TOOLS)
        except Exception as e:
            print("tool-call LLM error:", e)
            draft, calls = "", []
        if calls:
            msgs = msgs + [{"role": "assistant", "content": draft or "", "tool_calls": [
                {"id": cid, "type": "function", "function": {"name": n, "arguments": json.dumps(a, ensure_ascii=False)}}
                for cid, n, a in calls]}]
            for cid, n, a in calls[:2]:
                res = actions.execute(self, n, a, user_text)
                turn_results.append(res["status"])
                msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps(res, ensure_ascii=False)})
        text = ""
        for attempt in range(3):
            try:
                text = draft if (attempt == 0 and draft and not calls) else \
                    sarvam.chat(msgs, max_tokens=400, tools=actions.TOOLS if calls else None)
            except Exception as e:
                print("LLM error:", e)
                continue
            if not text:
                continue                                  # empty completion: retry
            if attempt < 2 and _asks_for_pii(text):
                # privacy guard: the bot must never collect contact / ID details in chat
                msgs = msgs + [{"role": "assistant", "content": text},
                               {"role": "user", "content": "(system note: never ask for phone numbers, emails or ID details. "
                                "Rewrite your last reply and point the user to IndiaMART app Settings instead. Reply with the rewrite only.)"}]
                text = ""
                continue
            if attempt < 2 and actions.unsupported_claim(text, turn_results):
                # skill.md hard guardrail: never claim transferred / booked / raised without a positive tool result
                msgs = msgs + [{"role": "assistant", "content": text},
                               {"role": "user", "content": "(system note: your reply claimed an action that no tool confirmed. "
                                f"Tool results this turn: {turn_results or 'none'}. Rewrite it truthfully – a recorded request is a "
                                "preference awaiting confirmation, and live transfer is not available. Reply with the rewrite only.)"}]
                text = ""
                continue
            if attempt == 0 and _reconfirms_known(text, self.md):
                # re-ask guard: one rewrite without the confirmation question
                msgs = msgs + [{"role": "assistant", "content": text},
                               {"role": "user", "content": "(system note: you re-confirmed a fact that is already known. "
                                "Rewrite your last reply WITHOUT asking or confirming any known fact. Reply with the rewrite only.)"}]
                text = ""
                continue
            break
        if not text:
            text = "Maaf kijiye, abhi thodi technical dikkat hai. Main aapko thodi der mein wapas contact karti hoon."
        llm_says_end = END_TOKEN.lower() in text.lower()
        text = re.sub(re.escape(END_TOKEN), "", text, flags=re.I).strip()
        if wants_to_end(user_text) or llm_says_end:
            self.end_requested = True
            if not llm_says_end:     # the caller said bye but the LLM kept talking: replace with a clean goodbye
                text = ("ठीक है, बात करने के लिए धन्यवाद। आपका दिन शुभ हो, नमस्ते!" if self.channel == "voice" and self.language == "hi-IN"
                        else "Theek hai, baat karne ke liye dhanyavad. Aapka din shubh ho!" if self.language == "hi-IN"
                        else "Sure, thank you for your time. Have a great day!")
        text = self._strip_invented_name(scrub(text))  # output guards: no contact/ID numbers, no invented names
        self.messages.append({"role": "assistant", "content": text})
        return text, changed

    def mark_interrupted(self, heard=None):
        """The caller cut the bot off mid-reply. Keep only the part they actually heard (heard = fraction 0..1 of the
        reply's audio that was played) so the LLM answers the new point instead of assuming everything was heard."""
        for m in reversed(self.messages):
            if m["role"] == "assistant":
                if "[caller interrupted" in m["content"]:
                    break
                text = m["content"]
                if heard is not None and 0 <= heard < 0.95:
                    cut = max(0, int(len(text) * heard))
                    text = text[:cut].rstrip() + "…"
                m["content"] = text + " [caller interrupted here – they only heard up to this point]"
                break

    def merge_unheard(self):
        """The caller kept talking before hearing the bot's last reply (they had only paused). Drop that unheard reply
        and return the caller's previous words, so both parts are answered together as one turn."""
        if self.messages and self.messages[-1]["role"] == "assistant":
            self.messages.pop()
        if self.messages and self.messages[-1]["role"] == "user":
            return self.messages.pop()["content"]
        return ""

    def _strip_invented_name(self, text):
        """'Namaste Sunita ji' when the file has no such name -> 'Namaste ji'. Real names from the file pass through."""
        allowed = {n.lower() for n in [self.known_first_name() or ""] if n} | {BOT_NAME.lower(), "indiamart"}
        end = r"(?![\w\u0900-\u097F])"
        names = set(re.findall(r"([A-Z][a-z]+|[\u0900-\u097F]+)(?= ?(?:ji|जी)" + end + ")", text))
        title = self.parsed.get("title", "").lower()
        known = bool(self.known_first_name())
        for n in names:
            devanagari = bool(re.match(r"[\u0900-\u097F]", n))
            if n in ("Namaste", "नमस्ते", "Haan", "हाँ", "हां") or n.lower() in allowed or n.lower() in title:
                continue
            if devanagari and known:      # can't compare scripts: a Devanagari spelling of the real name is fine
                continue
            text = re.sub(re.escape(n) + r" ?(ji|जी)" + end, r"\1", text)
        return text

    def known_first_name(self):
        """First name from the context file title ('(contact: X)' for sellers, '— X, City' for buyers), else None."""
        title = self.parsed.get("title", "")
        m = re.search(r"\(contact: ([^)]+)\)", title) or (re.search(r"— ([A-Z][a-z]+),", title) if self.role == "buyer" else None)
        return m.group(1).strip() if m else None

    # -- write-back ---------------------------------------------------------------------------
    def end(self):
        """Summarise this conversation into a `conversation` event → triggers a file rebuild."""
        if self.ended:
            return None
        self.ended = True
        if self.glid is None:          # unidentified caller: nothing to attach the summary to
            return None
        user_turns = [m for m in self.messages if m["role"] == "user"]
        if not user_turns:
            return None
        actions_json = json.dumps([{"action": a["action"], "result": a["result"], "reference": a.get("reference"),
                                    "preferred_time": a["args"].get("preferred_time")} for a in self.actions], ensure_ascii=False)
        name = self.known_first_name()
        who = f'"{name}"' if name else f'"the {self.role}" (their name is NOT known – do not use any name)'
        transcript = "\n".join(f"{'BOT' if m['role'] == 'assistant' else self.role.upper()}: {m['content']}" for m in self.messages)
        known = self.parsed["sections"].get("Known facts", {}).get("items", [])
        threads = self.parsed["sections"].get("Open threads", {}).get("items", [])
        prompt = f"""Summarise this {self.channel} conversation between IndiaMART's bot and a {self.role} for their context file.
Return JSON with exactly these keys:
- "summary": one sentence, max 30 words, English, third person. Refer to the user as {who}. NEVER invent or guess a person's name.
- "open_items": list (max 3) of concrete actions still pending after this conversation (promises the bot made, decisions the user still has to make), most important first. Keep still-relevant items from OPEN THREADS. Never list "confirm X" for anything in KNOWN FACTS. Each max 14 words.
- "resolved_items": list of previously open threads (copy wording from OPEN THREADS below) that got resolved or answered in this conversation.
- "facts": object of facts the user STATED OR CONFIRMED in this conversation (new or changed). Use snake_case keys; prefer: product, quantity, delivery_city, needed_by, budget_per_unit, target_price, sizes, payment_terms, preferred_seller, demo_date, preferred_call_time (buyers); min_order_qty, dispatch_time, lead_preference, secondary_contact_name, busy_until (sellers). Do not repeat KNOWN FACTS unless their value changed. Values max 8 words. NEVER include phone numbers, emails, addresses, GST/PAN/Aadhaar or bank details.
- "language": BCP-47 code the user spoke (e.g. hi-IN, en-IN).

ACTIONS (tool results – the ONLY truth about transfers / callbacks / meetings; mention a request only if listed here
with result recorded_unconfirmed or duplicate; a request that was only offered or asked about is NOT a request):
{actions_json}
OPEN THREADS:
{chr(10).join(threads) or '- none'}
KNOWN FACTS:
{chr(10).join(known) or '- none'}

TRANSCRIPT:
{transcript}"""
        try:
            s = sarvam.chat_json([{"role": "system", "content": "You write compact CRM notes as strict JSON."},
                                  {"role": "user", "content": prompt}])
        except Exception as e:
            print("summary error:", e)
            s = {}
        if not s.get("summary"):   # never lose the conversation: keep the user's last words verbatim
            s = {"summary": f"{self.role.capitalize()} said: " + user_turns[-1]["content"][:150], "open_items": [], "facts": {}}
        if not self.known_first_name():          # guard: no name in the file -> a name in the summary was invented
            for k in ("summary",):
                s[k] = re.sub(r"^[A-Z][a-z]+\b(?<!The)", f"The {self.role}", str(s.get(k, "")))
        payload = {"channel": self.channel, "session_id": self.id,
                   "summary": scrub(str(s.get("summary", "")))[:220],
                   "open_items": [scrub(str(x))[:120] for x in (s.get("open_items") or [])][:3],
                   "resolved_items": [str(x)[:160] for x in (s.get("resolved_items") or [])],
                   "facts": safe_facts(_facts_dict(s.get("facts"))),
                   "language": s.get("language") or self.language,
                   "intents": sorted({i for turn in self.intent_log for i in turn}),
                   "actions": self.actions,
                   "turns": len(user_turns)}
        ev = refresher.ingest(self.glid, "conversations", "conversation", payload, role=self.role)
        return {"event": ev, "summary": payload}


def _facts_dict(f):
    """Models sometimes return facts as ["Key: value", ...]; normalise to {key: value}."""
    if isinstance(f, dict):
        return f
    out = {}
    for item in f or []:
        if isinstance(item, str) and ":" in item:
            k, v = item.split(":", 1)
            out[re.sub(r"\W+", "_", k.strip().lower()).strip("_")] = v.strip()
    return out


def is_do_not_call(parsed):
    return any("do-not-call" in i.lower() for i in parsed["sections"].get("Handle with care", {}).get("items", []))


def start_session(glid, role, channel, direction=None):
    direction = direction or ("outbound" if channel == "voice" else "inbound")
    s = Session(glid, role, channel, direction)
    with _lock:
        SESSIONS[s.id] = s
    return s


def get(session_id):
    return SESSIONS.get(session_id)


def end_idle_sessions(idle_s):
    for s in list(SESSIONS.values()):
        if not s.ended and time.time() - s.last_activity > idle_s:
            s.end()
