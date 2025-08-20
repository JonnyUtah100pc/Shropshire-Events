#!/usr/bin/env python3
# scripts/build_ics.py — stable pre-pagination version

import os, re, json, hashlib, unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict

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
OUT_ALIAS  = os.path.join(REPO_ROOT, "shropshire-events.ics")  # homepage expects this
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

def
