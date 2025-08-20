#!/usr/bin/env python3
# scripts/build_ics.py — pre-pagination, single output (shropshire-events.ics)

import os, re, json, hashlib, unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict

import requests
from bs4 import BeautifulSoup
import yaml

try:
    import feedparser  # optional: RSS
except Exception:
    feedparser = None

try:
    from icalendar import Calendar  # optional: ICS import
except Exception:
    Calendar = None

# --- Repo / output settings ---------------------------------------------------
USERNAME   = "JonnyUtah100pc"
REPO       = "Shropshire-Events"
HUB_URL    = f"https://{USERNAME}.github.io/{REPO}"

CAL_NAME   = "Shropshire events"
REPO_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_ICS    = os.path.join(REPO_ROOT, "shropshire-events.ics")   # single canonical output
STATE_PATH = os.path.join(REPO_ROOT, "data", "state.json")
SOURCES_YAML = os.path.join(REPO_ROOT, "data", "sources.yaml")
MANUAL_YAML  = os.path.join(REPO_ROOT, "data", "manual.yaml")

# --- Window (30 days back, 2 years ahead) ------------------------------------
WINDOW_START = datetime.now(timezone.utc) - timedelta(days=30)
WINDOW_END   = datetime.now(timezone.utc) + timedelta(days=730)

HEADERS = {
    "User-Agent": f"Mozilla/5.0 (compatible; ShropshireICSBot/1.3; +{HUB_URL})"
}

# Hints to boost Shrewsbury events
SHREWSBURY_HINTS = [
    "shrewsbury", "originalshrewsbury", "theatresevern", "westmidshowground",
    "shrewsburyprison", "shrewsburyfolkfestival", "attingham", "the-quarry"
]

# ------------------------------------------------------------------------------
def log(*a): print("[build_ics]", *a)

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    text = re.sub(r"-{2,}", "-", text)
    return text or "event"

def parse_date_any(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    fmts = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except Exception:
            pass
    if s.endswith("Z"):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            pass
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d, tzinfo=timezone.utc)
    return None

def escape_ics(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

def fetch(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code == 200 and r.text:
            return r.text
        log("HTTP", r.status_code, "for", url)
    except Exception as ex:
        log("ERR", ex, "for", url)
    return None

# --- Extractors ---------------------------------------------------------------
def extract_events_from_jsonld(html: str, base_url: str) -> List[Dict]:
    out: List[Dict] = []
    if not html:
        return out
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            import json as _json
            raw = tag.string or "{}"
            data = _json.loads(raw)
        except Exception:
            continue
        items = data.get("@graph") if isinstance(data, dict) and "@graph" in data else data
        if not isinstance(items, list):
            items = [data]
        for item in items:
            t = item.get("@type")
            tlist = [t] if not isinstance(t, list) else t
            if not any(str(x).lower() == "event" for x in tlist if x):
                continue
            name = item.get("name") or item.get("headline") or "Event"
            start = item.get("startDate") or item.get("start") or item.get("startTime")
            end = item.get("endDate") or item.get("end") or item.get("endTime") or start
            url = item.get("url") or base_url
            loc = ""
            location = item.get("location")
            if isinstance(location, dict):
                loc = location.get("name") or ""
                addr = location.get("address")
                if isinstance(addr, dict):
                    parts = [addr.get(k, "") for k in ["streetAddress","addressLocality","addressRegion","postalCode"]]
                    loc = (loc + ", " + ", ".join([p for p in parts if p])).strip(", ")
            desc = item.get("description") or ""
            out.append({"summary": name, "start": start, "end": end, "url": url, "location": loc, "description": desc})
    return out

def extract_events_from_rss(url: str) -> List[Dict]:
    if feedparser is None:
        return []
    try:
        feed = feedparser.parse(url)
    except Exception:
        return []
    res = []
    for e in feed.entries:
        title = getattr(e, "title", None) or "Event"
        link = getattr(e, "link", url)
        desc = getattr(e, "summary", "") or getattr(e, "description", "")
        start = getattr(e, "start_date", None) or getattr(e, "published", None)
        end = getattr(e, "end_date", None) or start
        res.append({"summary": title, "start": start, "end": end, "url": link, "location": "", "description": desc})
    return res

def extract_events_from_ics(url: str) -> List[Dict]:
    if Calendar is None:
        return []
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code != 200:
            return []
        cal = Calendar.from_ical(r.content)
    except Exception:
        return []
    out = []
    from datetime import datetime as dt
    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        summary = str(comp.get("summary", "Event"))
        desc    = str(comp.get("description", ""))
        loc     = str(comp.get("location", ""))
        link    = str(comp.get("url", "")) or url
        s       = comp.get("dtstart")
        e       = comp.get("dtend") or s
        sdt     = getattr(s, "dt", None)
        edt     = getattr(e, "dt", None)
        if sdt is None:
            continue
        if hasattr(sdt, "year") and not hasattr(sdt, "hour"):
            sdt = dt(sdt.year, sdt.month, sdt.day, tzinfo=timezone.utc)
        if edt is None:
            edt = sdt
        if hasattr(edt, "year") and not hasattr(edt, "hour"):
            edt = dt(edt.year, edt.month, edt.day, tzinfo=timezone.utc)
        out.append({"summary": summary, "start": sdt.isoformat(), "end": edt.isoformat(),
                    "url": link, "location": loc, "description": desc})
    return out

# --- Helpers ------------------------------------------------------------------
def is_shrewsbury_hit(e: Dict) -> bool:
    text = " ".join([str(e.get("location", "")), str(e.get("url", "")), str(e.get("summary", ""))]).lower()
    return any(h in text for h in SHREWSBURY_HINTS)

def filter_window(evs: List[Dict]) -> List[Dict]:
    out = []
    for e in evs:
        sdt = parse_date_any(e.get("start", ""))
        edt = parse_date_any(e.get("end", "")) or sdt
        if not sdt:
            continue
        if edt < WINDOW_START or sdt > WINDOW_END:
            continue
        e["_sdt"], e["_edt"] = sdt, edt
        e["_is_shrewsbury"] = is_shrewsbury_hit(e)
        out.append(e)
    return out

def load_yaml(path: str) -> Dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def read_manual(path: str) -> List[Dict]:
    data = load_yaml(path)
    evs = []
    for it in data.get("events", []):
        evs.append({
            "summary": it.get("summary"),
            "start": it.get("start"),
            "end": it.get("end") or it.get("start"),
            "location": it.get("location", ""),
            "url": it.get("url", ""),
            "description": it.get("description", ""),
        })
    return evs

# --- Main ---------------------------------------------------------------------
def main() -> int:
    sources = load_yaml(SOURCES_YAML).get("sources", [])
    events: List[Dict] = []

    for src in sources:
        stype = src.get("type")
        url = src.get("url")
        if not url:
            continue
        log("source:", stype, url)

        try:
            if stype == "jsonld":
                html = fetch(url)
                evs = extract_events_from_jsonld(html, url)
            elif stype == "rss":
                evs = extract_events_from_rss(url)
            elif stype == "ics":
                evs = extract_events_from_ics(url)
            else:
                evs = []
        except Exception as ex:
            log("  error:", ex)
            evs = []

        log(f"  -> {len(evs)} raw events")
        for e in evs:
            e["_source"] = url
        events.extend(evs)

    # Add manual must-haves
    manual = read_manual(MANUAL_YAML)
    events.extend(manual)
    log(f"[totals] raw + manual: {len(events)}")

    # Window filter + tag
    events = filter_window(events)
    log(f"[totals] after window filter: {len(events)}")

    # Deduplicate by (summary, start day) and prefer Shrewsbury-tagged entries
    norm: Dict = {}
    for e in events:
        key = (e.get("summary") or "", e["_sdt"].strftime("%Y-%m-%d"))
        if key in norm:
            curr = norm[key]
            if e["_is_shrewsbury"] and not curr.get("_is_shrewsbury"):
                curr.update({
                    "url": e.get("url", ""),
                    "location": e.get("location", ""),
                    "description": e.get("description", ""),
                    "_is_shrewsbury": True
                })
            else:
                def better(a, b): return a if len(a or "") >= len(b or "") else b
                curr["url"] = curr.get("url") or e.get("url")
                curr["description"] = better(curr.get("description"), e.get("description"))
                curr["location"]     = better(curr.get("location"), e.get("location"))
                curr["_edt"] = max(curr["_edt"], e["_edt"])
        else:
            norm[key] = {
                "summary": e.get("summary"),
                "_sdt": e["_sdt"], "_edt": e["_edt"],
                "url": e.get("url", ""), "location": e.get("location", ""),
                "description": e.get("description", ""),
                "_is_shrewsbury": e["_is_shrewsbury"],
            }

    log(f"[totals] after dedupe: {len(norm)} keys")

    # Load previous state for SEQUENCE bumping
    try:
        state = json.load(open(STATE_PATH, "r", encoding="utf-8"))
    except Exception:
        state = {"uids": {}}

    seen_uids = set()
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    vevents = []

    # Sort: Shrewsbury first, then by start date
    for _, e in sorted(norm.items(), key=lambda kv: (not kv[1]["_is_shrewsbury"], kv[1]["_sdt"])):
        summary = e["summary"] or "Event"
        sdt, edt = e["_sdt"], e["_edt"]

        # Stable UID: slug(summary)-YEAR@username.github.io
        base_uid = f"{slugify(summary)}-{sdt.strftime('%Y')}@{USERNAME}.github.io"
        uid = base_uid
        i = 2
        while uid in seen_uids:
            uid = f"{base_uid}-{i}"
            i += 1
        seen_uids.add(uid)

        # Hash to detect content changes for SEQUENCE
        content_hash = hashlib.sha1("|".join([
            summary,
            sdt.isoformat(),
            edt.isoformat(),
            e["location"],
            e["description"],
            e["url"]
        ]).encode("utf-8")).hexdigest()

        prev = state["uids"].get(uid, {})
        seq = int(prev.get("sequence", 0))
        if prev.get("hash") and prev["hash"] != content_hash:
            seq += 1
        state["uids"][uid] = {"hash": content_hash, "sequence": seq}

        cats = ["Shropshire"]
        if e["_is_shrewsbury"]:
            cats.append("Shrewsbury")
        categories = ",".join(cats)

        def esc(x): return escape_ics(x) if x else ""

        vevents.append("\n".join([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"SEQUENCE:{seq}",
            f"DTSTART;VALUE=DATE:{sdt.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(edt + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{esc(summary)}",
            f"LOCATION:{esc(e['location'])}" if e.get("location") else "LOCATION:",
            f"DESCRIPTION:{esc(e['description'])}" if e.get("description") else "DESCRIPTION:",
            f"URL:{e['url']}" if e.get("url") else "",
            f"CATEGORIES:{categories}",
            ("PRIORITY:1" if e["_is_shrewsbury"] else "PRIORITY:5"),
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]))

    # Build VCALENDAR
    vcal = "\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Shropshire Events Bot//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{CAL_NAME}",
        "X-WR-TIMEZONE:Europe/London",
        f"URL:{HUB_URL}",
        "REFRESH-INTERVAL;VALUE=DURATION:P1D",
        "X-PUBLISHED-TTL:PT12H",
        *vevents,
        "END:VCALENDAR",
    ])

    # Write single output
    with open(OUT_ICS, "w", encoding="utf-8") as f:
        f.write(vcal)

    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    log(f"Wrote {OUT_ICS} with {len(vevents)} events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

