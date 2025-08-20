#!/usr/bin/env python3
"""
Build Shrewsbury & Shropshire ICS from official sites.

Sources:
- JSON-LD (schema.org/Event) scraped from official event pages
- Optional RSS/Atom feeds
- Optional manual YAML additions

Outputs:
- shrewsbury_events_JonnyUtah100pc.ics (root)
- data/state.json (to keep SEQUENCE stable across updates)

Notes:
- Uses STABLE UIDs: slug-of-name + YEAR @ JonnyUtah100pc.github.io
- Bumps SEQUENCE when an existing UID's content hash changes
- All-day events by default when times are unknown
"""
import os, sys, re, json, time, hashlib, unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from typing import List, Dict, Any, Optional

import requests
from bs4 import BeautifulSoup
import yaml
try:
    import feedparser  # optional; used if any RSS sources are configured
except Exception:
    feedparser = None

# -------- CONFIG --------
USERNAME = "JonnyUtah100pc"
HUB_URL = f"https://{USERNAME}.github.io/shropshire-events"
CAL_NAME = "Shrewsbury & Shropshire Events"
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_ICS = os.path.join(REPO_ROOT, "shrewsbury_events_JonnyUtah100pc.ics")
STATE_PATH = os.path.join(REPO_ROOT, "data", "state.json")
SOURCES_YAML = os.path.join(REPO_ROOT, "data", "sources.yaml")
MANUAL_YAML = os.path.join(REPO_ROOT, "data", "manual.yaml")

# Limit window to roughly next 8 months to keep file small (edit as preferred)
WINDOW_START = datetime.now(timezone.utc) - timedelta(days=7)   # keep a week of history
WINDOW_END   = datetime.now(timezone.utc) + timedelta(days=240) # ~8 months

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ShropshireICSBot/1.0; +{hub})".format(hub=HUB_URL)
}

# -------- UTILITIES --------
def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    text = re.sub(r"-{2,}", "-", text)
    return text or "event"

def parse_date_any(s: str) -> Optional[datetime]:
    """
    Parse ISO-ish datetime/date strings. Returns aware UTC datetime if possible.
    """
    if not s:
        return None
    s = s.strip()
    # try common iso forms
    fmts = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d"
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                # assume Europe/London local -> convert to UTC at build time (approx.)
                # For simplicity, treat as naive local; convert by offset from UTC now.
                # (If exact TZ handling is needed, use zoneinfo.)
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except Exception:
            continue
    # try loose, add Z
    if s.endswith("Z"):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            pass
    # fallback: only date
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d, tzinfo=timezone.utc)
    return None

def to_yyyymmdd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")

def next_day(dt: datetime) -> datetime:
    return dt + timedelta(days=1)

def stable_uid(summary: str, start: datetime, seen: set) -> str:
    year = start.strftime("%Y")
    base = f"{slugify(summary)}-{year}"
    candidate = base
    i = 2
    while candidate in seen:
        candidate = f"{base}-{i}"
        i += 1
    seen.add(candidate)
    return f"{candidate}@{USERNAME}.github.io"

def text_hash(d: Dict[str, Any]) -> str:
    blob = json.dumps(d, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()

def load_yaml(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def escape_ics(text: str) -> str:
    if text is None:
        return ""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )

# -------- SCRAPERS --------
def fetch(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        return None
    return None

def extract_events_from_jsonld(html: str, base_url: str) -> List[dict]:
    soup = BeautifulSoup(html, "lxml")
    events = []
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            import json as _json
            data = _json.loads(tag.string or "{}")
        except Exception:
            continue
        # Flatten @graph or list/object
        items = []
        if isinstance(data, dict) and "@graph" in data:
            items = data["@graph"]
        elif isinstance(data, list):
            items = data
        else:
            items = [data]
        for item in items:
            types = item.get("@type")
            if isinstance(types, list):
                is_event = any(t.lower() == "event" for t in [str(x).lower() for x in types])
            else:
                is_event = str(types).lower() == "event"
            if not is_event:
                continue
            name = item.get("name") or item.get("headline")
            start = item.get("startDate")
            end = item.get("endDate") or item.get("endDateTime") or start
            url = item.get("url") or base_url
            loc = ""
            location = item.get("location")
            if isinstance(location, dict):
                loc = location.get("name") or ""
                addr = location.get("address")
                if isinstance(addr, dict):
                    parts = [addr.get(k,"") for k in ["streetAddress","addressLocality","addressRegion","postalCode"]]
                    loc = (loc + ", " + ", ".join([p for p in parts if p])).strip(", ")
            desc = item.get("description") or ""
            # Map
            events.append({
                "summary": name,
                "start": start,
                "end": end,
                "url": url,
                "location": loc,
                "description": desc
            })
    return events

def extract_events_from_rss(url: str) -> List[dict]:
    if feedparser is None:
        return []
    try:
        feed = feedparser.parse(url)
    except Exception:
        return []
    out = []
    for e in feed.entries:
        title = getattr(e, "title", None)
        link = getattr(e, "link", url)
        summary = getattr(e, "summary", "") or getattr(e, "description", "")
        # Try dates
        # Many feeds put date in published or updated; not ideal for events.
        # We support custom 'ev:start' / 'startDate' etc if present.
        start = getattr(e, "start_date", None) or getattr(e, "startDate", None) or getattr(e, "published", None)
        end = getattr(e, "end_date", None) or getattr(e, "endDate", None) or start
        out.append({
            "summary": title, "start": start, "end": end, "url": link, "location": "", "description": summary
        })
    return out

def filter_window(evts: List[dict]) -> List[dict]:
    filtered = []
    for e in evts:
        sdt = parse_date_any(e.get("start",""))
        edt = parse_date_any(e.get("end","")) or sdt
        if not sdt:
            continue
        if edt < WINDOW_START or sdt > WINDOW_END:
            continue
        e["_sdt"] = sdt
        e["_edt"] = edt
        filtered.append(e)
    return filtered

def read_manual(path: str) -> List[dict]:
    data = load_yaml(path)
    out = []
    for item in data.get("events", []):
        out.append({
            "summary": item.get("summary"),
            "start": item.get("start"),
            "end": item.get("end") or item.get("start"),
            "location": item.get("location", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
        })
    return out

def load_sources(path: str) -> List[dict]:
    data = load_yaml(path)
    return data.get("sources", [])

# -------- MAIN BUILD --------
def main() -> int:
    os.makedirs(os.path.dirname(OUT_ICS), exist_ok=True)
    sources = load_sources(SOURCES_YAML)
    all_events: List[dict] = []

    for src in sources:
        stype = src.get("type")
        url = src.get("url")
        if not url:
            continue
        print(f"[source] {stype} {url}")
        try:
            if stype == "jsonld":
                html = fetch(url)
                if not html:
                    continue
                evs = extract_events_from_jsonld(html, url)
            elif stype == "rss":
                evs = extract_events_from_rss(url)
            else:
                # Unknown type -> skip (you can add custom scrapers here)
                evs = []
        except Exception as ex:
            print("  ! error:", ex)
            evs = []
        # tag source for troubleshooting
        for e in evs:
            e["_source"] = url
        all_events.extend(evs)

    # Add manual events
    all_events.extend(read_manual(MANUAL_YAML))

    # Window filter
    all_events = filter_window(all_events)

    # Normalize and deduplicate by (summary, start date)
    normalized = {}
    for e in all_events:
        sdt = e["_sdt"]
        edt = e["_edt"] or sdt
        key = (e.get("summary") or "", sdt.strftime("%Y-%m-%d"))
        if key in normalized:
            # prefer one with URL/desc/location
            curr = normalized[key]
            def better(a, b): return a if len(a or "") >= len(b or "") else b
            curr["url"] = curr.get("url") or e.get("url")
            curr["description"] = better(curr.get("description"), e.get("description"))
            curr["location"] = better(curr.get("location"), e.get("location"))
            curr["_source"] = curr.get("_source") or e.get("_source")
            curr["_edt"] = max(curr["_edt"], edt)
        else:
            normalized[key] = {
                "summary": e.get("summary"),
                "_sdt": sdt,
                "_edt": edt,
                "url": e.get("url") or "",
                "location": e.get("location") or "",
                "description": e.get("description") or "",
                "_source": e.get("_source","")
            }

    # Load state for SEQUENCE
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {"uids": {}}

    seen_uid_bases = set()
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    # Build VEVENTs
    vevents = []
    for key, e in sorted(normalized.items(), key=lambda kv: kv[1]["_sdt"]):
        summary = e["summary"] or "Event"
        sdt = e["_sdt"]
        edt = e["_edt"]
        uid = stable_uid(summary, sdt, seen_uid_bases)  # stable per year
        # Hash the content that should trigger an update
        content_hash = hashlib.sha1("|".join([
            summary,
            sdt.isoformat(),
            edt.isoformat(),
            e["location"],
            e["description"],
            e["url"],
        ]).encode("utf-8")).hexdigest()
        prev = state["uids"].get(uid, {})
        sequence = int(prev.get("sequence", 0))
        if prev.get("hash") and prev["hash"] != content_hash:
            sequence += 1
        state["uids"][uid] = {"hash": content_hash, "sequence": sequence}

        def fmt(text: str) -> str:
            return escape_ics(text) if text else ""

        vevent = "\n".join([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"SEQUENCE:{sequence}",
            f"DTSTART;VALUE=DATE:{sdt.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(edt + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{fmt(summary)}",
            f"LOCATION:{fmt(e['location'])}" if e.get("location") else "LOCATION:",
            f"DESCRIPTION:{fmt(e['description'])}" if e.get("description") else "DESCRIPTION:",
            f"URL:{e['url']}" if e.get("url") else "",
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "END:VEVENT"
        ])
        vevents.append(vevent)

    # VCALENDAR
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

    with open(OUT_ICS, "w", encoding="utf-8") as f:
        f.write(vcal)

    # Save state
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_ICS} with {len(vevents)} events.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
