#!/usr/bin/env python3
# scripts/build_ics.py
import os
import re
import json
import hashlib
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import yaml

try:
    import feedparser  # RSS
except Exception:
    feedparser = None

try:
    from icalendar import Calendar  # ICS import
except Exception:
    Calendar = None

# --- Repo / output settings ---------------------------------------------------
USERNAME   = "JonnyUtah100pc"
REPO       = "Shropshire-Events"
HUB_URL    = f"https://{USERNAME}.github.io/{REPO}"

CAL_NAME   = "Shropshire events"
REPO_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_ICS    = os.path.join(REPO_ROOT, "shrewsbury_events_JonnyUtah100pc.ics")
OUT_ALIAS  = os.path.join(REPO_ROOT, "shropshire-events.ics")
STATE_PATH = os.path.join(REPO_ROOT, "data", "state.json")
SOURCES_YAML = os.path.join(REPO_ROOT, "data", "sources.yaml")
MANUAL_YAML  = os.path.join(REPO_ROOT, "data", "manual.yaml")

# --- Window (30 days back, 2 years ahead) ------------------------------------
WINDOW_START = datetime.now(timezone.utc) - timedelta(days=30)
WINDOW_END   = datetime.now(timezone.utc) + timedelta(days=730)

HEADERS = {
    "User-Agent": f"Mozilla/5.0 (compatible; ShropshireICSBot/1.4; +{HUB_URL})"
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

# --- Pagination helpers -------------------------------------------------------
def fetch_pages_with_next(url: str, next_selector: str, max_pages: int = 12) -> List[str]:
    """
    Follow "next" links by CSS selector, returning a list of HTML texts including the first page.
    Uses the first page as the base for resolving relative next links.
    """
    pages_html: List[str] = []
    seen_urls = set()
    current_url = url
    base_for_join = url
    for _ in range(max_pages):
        if not current_url or current_url in seen_urls:
            break
        seen_urls.add(current_url)
        html = fetch(current_url)
        if not html:
            break
        pages_html.append(html)
        try:
            soup = BeautifulSoup(html, "lxml")
            nxt = soup.select_one(next_selector)
            if nxt and nxt.get("href"):
                nxt_url = nxt.get("href")
                current_url = urljoin(base_for_join, nxt_url)
            else:
