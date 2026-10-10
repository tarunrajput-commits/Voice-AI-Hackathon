"""Parse buyer.md / seller.md back into a dict, so non-bot consumers (dashboards, campaigns,
call-prep) read the *same* files the bot reads – no second pipeline, no rework."""
import re


def parse(text):
    if not text:
        return None
    meta, body = {}, text
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"')
    out = {"meta": meta, "title": "", "sections": {}}
    current = None
    for line in body.splitlines():
        if line.startswith("# "):
            out["title"] = line[2:].strip()
        elif line.startswith("## "):
            current = line[3:].split(" (")[0].split(" — ")[0].strip()
            out["sections"][current] = {"heading": line[3:].strip(), "items": [], "kv": {}, "rows": []}
        elif line.startswith("- ") and current:
            item = line[2:].strip()
            sec = out["sections"][current]
            if item == "none":
                continue
            sec["items"].append(item)
            if " | " in item:
                sec["rows"].append([c.strip() for c in item.split(" | ")])
            kv = re.match(r"^([a-z_0-9]+): (.*)$", item)
            if kv:
                sec["kv"][kv.group(1)] = kv.group(2)
    return out
