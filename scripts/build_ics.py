#!/usr/bin/env python3
import os, re, json, hashlib, unicodedata
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
import yaml
try:
    import feedparser
except Exception:
    feedparser = None
try:
    from icalendar import Calendar
except Exception:
    Calendar = None

USERNAME = "JonnyUtah100pc"
HUB_URL = f"https://{USERNAME}.github.io/shropshire-events"
CAL_NAME = "Shrewsbury & Shropshire Events"
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_ICS = os.path.join(REPO_ROOT, "shrewsbury_events_JonnyUtah100pc.ics")
STATE_PATH = os.path.join(REPO_ROOT, "data", "state.json")
SOURCES_YAML = os.path.join(REPO_ROOT, "data", "sources.yaml")
MANUAL_YAML = os.path.join(REPO_ROOT, "data", "manual.yaml")

WINDOW_START = datetime.now(timezone.utc) - timedelta(days=7)
WINDOW_END   = datetime.now(timezone.utc) + timedelta(days=240)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ShropshireICSBot/1.1; +%s)" % HUB_URL}

def log(*a): print("[build_ics]", *a)

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii","ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    text = re.sub(r"-{2,}", "-", text)
    return text or "event"

def parse_date_any(s: str) -> Optional[datetime]:
    if not s: return None
    s = s.strip()
    fmts = ["%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S.%f%z","%Y-%m-%dT%H:%M%z","%Y-%m-%dT%H:%M:%S","%Y-%m-%d"]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            else: dt = dt.astimezone(timezone.utc)
            return dt
        except Exception: pass
    if s.endswith("Z"):
        try: return datetime.fromisoformat(s.replace("Z","+00:00"))
        except Exception: pass
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        y,mo,d = map(int, m.groups())
        return datetime(y,mo,d,tzinfo=timezone.utc)
    return None

def to_yyyymmdd(dt: datetime) -> str: return dt.strftime("%Y%m%d")
def next_day(dt: datetime) -> datetime: return dt + timedelta(days=1)

def stable_uid(summary: str, start: datetime, seen: set) -> str:
    base = f"{slugify(summary)}-{start.strftime('%Y')}"
    cand, i = base, 2
    while cand in seen: cand, i = f"{base}-{i}", i+1
    seen.add(cand)
    return f"{cand}@{USERNAME}.github.io"

def escape_ics(text: str) -> str:
    return str(text).replace("\\","\\\\").replace(",","\\,").replace(";","\\;").replace("\n","\\n")

def fetch(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code == 200 and r.text: return r.text
        log("HTTP", r.status_code, "for", url)
    except Exception as ex:
        log("ERR", ex, "for", url)
    return None

def extract_events_from_jsonld(html: str, base_url: str) -> List[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for tag in soup.find_all("script", {"type":"application/ld+json"}):
        try:
            import json as _json
            data = _json.loads(tag.string or "{}")
        except Exception:
            continue
        items = data.get("@graph") if isinstance(data, dict) and "@graph" in data else data
        if not isinstance(items, list): items = [data]
        for item in items:
            t = item.get("@type")
            tlist = [t] if not isinstance(t, list) else t
            if not any(str(x).lower()=="event" for x in tlist): continue
            name = item.get("name") or item.get("headline") or "Event"
            start = item.get("startDate") or item.get("startTime") or item.get("start")
            end   = item.get("endDate")   or item.get("endTime")   or item.get("end") or start
            url   = item.get("url") or base_url
            loc = ""
            location = item.get("location")
            if isinstance(location, dict):
                loc = location.get("name") or ""
                addr = location.get("address")
                if isinstance(addr, dict):
                    parts = [addr.get(k,"") for k in ["streetAddress","addressLocality","addressRegion","postalCode"]]
                    loc = (loc + ", " + ", ".join([p for p in parts if p])).strip(", ")
            desc = item.get("description") or ""
            out.append({"summary":name,"start":start,"end":end,"url":url,"location":loc,"description":desc})
    return out

def extract_events_from_rss(url: str) -> List[dict]:
    if feedparser is None: return []
    try:
        feed = feedparser.parse(url)
    except Exception:
        return []
    res = []
    for e in feed.entries:
        title = getattr(e,"title",None) or "Event"
        link = getattr(e,"link",url)
        desc = getattr(e,"summary","") or getattr(e,"description","")
        start = getattr(e,"start_date",None) or getattr(e,"published",None)
        end = getattr(e,"end_date",None) or start
        res.append({"summary":title,"start":start,"end":end,"url":link,"location":"", "description":desc})
    return res

def extract_events_from_ics(url: str) -> List[dict]:
    if Calendar is None: return []
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code != 200:
            log("ICS HTTP", r.status_code, "for", url)
            return []
        cal = Calendar.from_ical(r.content)
    except Exception as ex:
        log("ICS parse error", ex, "for", url)
        return []
    res = []
    for comp in cal.walk():
        if comp.name != "VEVENT": continue
        summary = str(comp.get("summary","Event"))
        desc = str(comp.get("description",""))
        loc = str(comp.get("location",""))
        link = str(comp.get("url","")) or url
        dtstart = comp.get("dtstart")
        dtend   = comp.get("dtend") or dtstart
        sdt = getattr(dtstart, "dt", None)
        edt = getattr(dtend, "dt", None)
        # Convert date to datetime for uniformity
        from datetime import date, datetime as dt
        if sdt and not isinstance(sdt, dt): sdt = datetime(sdt.year,sdt.month,sdt.day,tzinfo=timezone.utc)
        if edt and not isinstance(edt, dt): edt = datetime(edt.year,edt.month,edt.day,tzinfo=timezone.utc)
        if not sdt: continue
        if not edt: edt = sdt
        res.append({
            "summary": summary, "start": sdt.isoformat(), "end": edt.isoformat(),
            "url": link, "location": loc, "description": desc
        })
    return res

def filter_window(evs: List[dict]) -> List[dict]:
    out = []
    for e in evs:
        sdt = parse_date_any(e.get("start",""))
        edt = parse_date_any(e.get("end","")) or sdt
        if not sdt: continue
        if edt < WINDOW_START or sdt > WINDOW_END: continue
        e["_sdt"], e["_edt"] = sdt, edt
        out.append(e)
    return out

def load_yaml(path: str) -> dict:
    if not os.path.exists(path): return {}
    with open(path, "r", encoding="utf-8") as f: return yaml.safe_load(f) or {}

def read_manual(path: str) -> List[dict]:
    data = load_yaml(path)
    return [{
        "summary": it.get("summary"), "start": it.get("start"),
        "end": it.get("end") or it.get("start"),
        "location": it.get("location",""),
        "url": it.get("url",""),
        "description": it.get("description","")
    } for it in data.get("events", [])]

def main() -> int:
    sources = load_yaml(SOURCES_YAML).get("sources", [])
    all_events = []

    for src in sources:
        stype, url = src.get("type"), src.get("url")
        if not url: continue
        log("source:", stype, url)
        try:
            if stype == "jsonld":
                html = fetch(url)
                evs = extract_events_from_jsonld(html, url) if html else []
            elif stype == "rss":
                evs = extract_events_from_rss(url)
            elif stype == "ics":
                evs = extract_events_from_ics(url)
            else:
                log("unknown source type:", stype)
                evs = []
        except Exception as ex:
            log("  error:", ex)
            evs = []
        for e in evs: e["_source"] = url
        all_events.extend(evs)

    all_events.extend(read_manual(MANUAL_YAML))
    all_events = filter_window(all_events)

    # Dedup by (summary, start day)
    norm = {}
    for e in all_events:
        k = (e.get("summary") or "", e["_sdt"].strftime("%Y-%m-%d"))
        if k in norm:
            curr = norm[k]
            def better(a,b): return a if len(a or "")>=len(b or "") else b
            curr["url"] = curr.get("url") or e.get("url")
            curr["description"] = better(curr.get("description"), e.get("description"))
            curr["location"] = better(curr.get("location"), e.get("location"))
            curr["_edt"] = max(curr["_edt"], e["_edt"])
            continue
        norm[k] = {
            "summary": e.get("summary"),
            "_sdt": e["_sdt"], "_edt": e["_edt"],
            "url": e.get("url",""), "location": e.get("location",""),
            "description": e.get("description","")
        }

    # Load previous state for SEQUENCE
    try:
        state = json.load(open(STATE_PATH, "r", encoding="utf-8"))
    except Exception:
        state = {"uids": {}}

    seen = set()
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    vevents = []
    for _, e in sorted(norm.items(), key=lambda kv: kv[1]["_sdt"]):
        summary = e["summary"] or "Event"
        sdt, edt = e["_sdt"], e["_edt"]
        uid = stable_uid(summary, sdt, seen)
        content_hash = hashlib.sha1("|".join([
            summary, sdt.isoformat(), edt.isoformat(), e["location"], e["description"], e["url"]
        ]).encode("utf-8")).hexdigest()
        prev = state["uids"].get(uid, {})
        seq = int(prev.get("sequence", 0))
        if prev.get("hash") and prev["hash"] != content_hash: seq += 1
        state["uids"][uid] = {"hash": content_hash, "sequence": seq}

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
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "END:VEVENT"
        ]))

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
        "END:VCALENDAR"
    ])

    with open(OUT_ICS, "w", encoding="utf-8") as f: f.write(vcal)
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f: json.dump(state, f, ensure_ascii=False, indent=2)

    log(f"Wrote {OUT_ICS} with {len(vevents)} events.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
