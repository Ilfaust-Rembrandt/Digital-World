"""
╔══════════════════════════════════════════════════════════╗
║           BIOME SYSTEM — Live Data Feed Edition          ║
║     Real-world data flows through the Digital World      ║
╚══════════════════════════════════════════════════════════╝

Each biome is a living environment fed by real-world data
streams. Digimon don't just gain abstract richness — they
ingest actual knowledge from the internet, and their
capabilities, descriptions, and evolution are shaped by it.

BIOME → DATA SOURCE MAPPING (fixed core + Yggdrasil bonus):

    Desert      → Shodan, VirusTotal, CVE/NVD
                  (threat landscape, exposed infrastructure)

    Grasslands  → NewsAPI, Reddit (/r/worldnews, /r/technology)
                  (current events, human discourse)

    Forest      → Wikipedia, arXiv
                  (deep knowledge, academic research)

    Highlands   → NIST NVD, GitHub Security Advisories
                  (security standards, vulnerability data)

    Mountains   → GitHub Trending, NVIDIA Developer Blog
                  (cutting-edge tech, GPU/AI research)

    Ocean       → NASA Open APIs, arXiv (astro/physics)
                  (vast, deep, cosmic-scale data)

    DeepOcean   → arXiv (AI/ML papers), GitHub (AI repos)
                  (frontier intelligence, rare insights)

WHAT DIGIMON DO WITH DATA:
    - Vaccine: extract threats → gain counter-capabilities
    - Virus: extract exploits → gain attack capabilities
    - Data: extract knowledge → evolve faster, gain expertise

FALLBACK CHAIN (Yggdrasil managed):
    If a source fails → Yggdrasil picks backup from same tier
    Failure logged → biome richness temporarily penalised
    After 3 failures → source blacklisted for 50 ticks
"""

import os
import re
import json
import random
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from typing import Optional


# =============================================================================
# API KEY CONFIGURATION
# =============================================================================

def _load_dotenv(path: str = None):
    """
    Load a .env file into os.environ before reading API keys.

    Searches for .env in this order:
        1. Explicit path passed in
        2. Same directory as this file (biomes/.env)
        3. Project root (one level up from biomes/)
        4. Current working directory

    File format — one KEY=VALUE per line, # comments ignored:
        SHODAN_API_KEY=abc123
        GITHUB_TOKEN=ghp_xxxx
        # this is a comment
        NASA_API_KEY=DEMO_KEY
    """
    search_paths = []
    if path:
        search_paths.append(path)
    this_dir = os.path.dirname(os.path.abspath(__file__))
    search_paths += [
        os.path.join(this_dir, ".env"),                     # biomes/.env
        os.path.join(os.path.dirname(this_dir), ".env"),    # project root .env
        os.path.join(os.getcwd(), ".env"),                  # cwd .env
    ]
    for env_path in search_paths:
        if os.path.isfile(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key   = key.strip()
                    value = value.strip().strip('"').strip("'")
                    # Only set if not already in environment (env vars take priority)
                    if key and key not in os.environ:
                        os.environ[key] = value
            break  # stop at first .env found


_load_dotenv()


def _get_api_keys() -> dict:
    """Read keys fresh from environment each call (so .env changes take effect)."""
    return {
        "shodan":      os.environ.get("SHODAN_API_KEY",      ""),
        "virustotal":  os.environ.get("VIRUSTOTAL_API_KEY",  ""),
        "nist":        os.environ.get("NIST_API_KEY",        ""),
        "nvidia":      os.environ.get("NVIDIA_API_KEY",      ""),
        "newsapi":     os.environ.get("NEWSAPI_KEY",         ""),
        "github":      os.environ.get("GITHUB_TOKEN",        ""),
        "nasa":        os.environ.get("NASA_API_KEY",        "DEMO_KEY"),
    }

# Module-level alias — callers use API_KEYS["key"] as before
# but it's refreshed each time fetch_source() calls _get_api_keys()
API_KEYS = _get_api_keys()


# =============================================================================
# BIOME BASE DEFINITIONS
# =============================================================================

BIOME_DEFINITIONS = {
    "Desert": {
        "description":       "A harsh expanse of corrupted data dunes. Threat intel dominates.",
        "base_richness":     1.5,
        "preferred_attr":    "Virus",
        "hostile_attr":      "Data",
        "base_event_chance": 0.12,
        "possible_events":   ["Drought", "Corruption", "Data Bloom"],
        "core_sources":      ["shodan", "virustotal", "nvd_cve"],
        "bonus_sources":     [],
        "feed_theme":        "threat intelligence and exposed infrastructure",
    },
    "Grasslands": {
        "description":       "Wide open plains of balanced data flow. Human discourse lives here.",
        "base_richness":     2.0,
        "preferred_attr":    None,
        "hostile_attr":      None,
        "base_event_chance": 0.08,
        "possible_events":   ["Data Bloom", "Corruption", "Drought"],
        "core_sources":      ["newsapi", "reddit"],
        "bonus_sources":     [],
        "feed_theme":        "current events, human society, and trending discourse",
    },
    "Forest": {
        "description":       "Dense canopy of layered knowledge streams. Scholars thrive here.",
        "base_richness":     2.5,
        "preferred_attr":    "Data",
        "hostile_attr":      "Virus",
        "base_event_chance": 0.10,
        "possible_events":   ["Wildfire", "Data Bloom", "Corruption"],
        "core_sources":      ["wikipedia", "arxiv"],
        "bonus_sources":     [],
        "feed_theme":        "encyclopedic knowledge and academic research",
    },
    "Highlands": {
        "description":       "Elevated terrain with strategic data flows. Vaccine stronghold.",
        "base_richness":     2.0,
        "preferred_attr":    "Vaccine",
        "hostile_attr":      "Virus",
        "base_event_chance": 0.09,
        "possible_events":   ["Avalanche", "Data Bloom", "Storm"],
        "core_sources":      ["nvd_cve", "github_security"],
        "bonus_sources":     [],
        "feed_theme":        "security standards, vulnerability databases, and defense",
    },
    "Mountains": {
        "description":       "Ancient data formations. Cutting-edge technology carved in stone.",
        "base_richness":     3.0,
        "preferred_attr":    "Vaccine",
        "hostile_attr":      None,
        "base_event_chance": 0.11,
        "possible_events":   ["Avalanche", "Drought", "Data Bloom"],
        "core_sources":      ["github_trending", "nvidia_tech"],
        "bonus_sources":     [],
        "feed_theme":        "cutting-edge technology, GPU computing, and AI research",
    },
    "Ocean": {
        "description":       "Vast dynamic data currents. Cosmic-scale knowledge flows here.",
        "base_richness":     2.5,
        "preferred_attr":    "Data",
        "hostile_attr":      None,
        "base_event_chance": 0.13,
        "possible_events":   ["Storm", "Data Bloom", "Corruption"],
        "core_sources":      ["nasa", "arxiv_physics"],
        "bonus_sources":     [],
        "feed_theme":        "space exploration, earth science, and physics research",
    },
    "DeepOcean": {
        "description":       "The deepest layer. Frontier AI research pulses in the dark.",
        "base_richness":     4.0,
        "preferred_attr":    "Data",
        "hostile_attr":      "Virus",
        "base_event_chance": 0.07,
        "possible_events":   ["Storm", "Data Bloom", "Corruption"],
        "core_sources":      ["arxiv_ai", "github_ai"],
        "bonus_sources":     [],
        "feed_theme":        "frontier AI, machine learning, and deep research papers",
    },
}

BIOME_ADJACENCY = {
    "Desert":     ["Grasslands", "Highlands"],
    "Grasslands": ["Desert", "Forest", "Highlands"],
    "Forest":     ["Grasslands", "Mountains", "Highlands"],
    "Highlands":  ["Desert", "Grasslands", "Forest", "Mountains"],
    "Mountains":  ["Forest", "Highlands", "Ocean"],
    "Ocean":      ["Mountains", "Grasslands", "DeepOcean"],
    "DeepOcean":  ["Ocean"],
}


# =============================================================================
# EVENT DEFINITIONS
# =============================================================================

EVENT_DEFINITIONS = {
    "Drought": {
        "description":    "Data wells have dried up. Richness plummets.",
        "duration_range": (3, 8),
        "richness_mod":   0.40,
        "blocks_entry":   False,
        "forces_flee":    False,
        "attr_penalty":   {"Data": 0.50, "Vaccine": 0.70},
        "attr_bonus":     {"Virus": 1.10},
    },
    "Storm": {
        "description":    "Electromagnetic storm. Roaming blocked.",
        "duration_range": (2, 5),
        "richness_mod":   0.80,
        "blocks_entry":   True,
        "forces_flee":    False,
        "attr_penalty":   {},
        "attr_bonus":     {},
    },
    "Wildfire": {
        "description":    "Data streams are burning. Digimon must flee.",
        "duration_range": (2, 4),
        "richness_mod":   0.10,
        "blocks_entry":   True,
        "forces_flee":    True,
        "attr_penalty":   {"Data": 0.20},
        "attr_bonus":     {},
    },
    "Avalanche": {
        "description":    "Cascading data collapse. Biome sealed off.",
        "duration_range": (3, 6),
        "richness_mod":   0.60,
        "blocks_entry":   True,
        "forces_flee":    False,
        "attr_penalty":   {},
        "attr_bonus":     {},
    },
    "Data Bloom": {
        "description":    "Surge of fresh data. Richness spikes for all.",
        "duration_range": (2, 5),
        "richness_mod":   2.50,
        "blocks_entry":   False,
        "forces_flee":    False,
        "attr_penalty":   {},
        "attr_bonus":     {"Data": 3.0, "Vaccine": 2.0},
    },
    "Corruption": {
        "description":    "Virus contamination spreads through the data layer.",
        "duration_range": (4, 10),
        "richness_mod":   0.70,
        "blocks_entry":   False,
        "forces_flee":    False,
        "attr_penalty":   {"Data": 0.40, "Vaccine": 0.60},
        "attr_bonus":     {"Virus": 1.80},
    },
}

# =============================================================================
# DOMAIN POOL
# =============================================================================

DOMAIN_POOL = {
    "Geology":         {"cap_bonus": "terrain_mastery",      "preferred_biomes": ["Mountains", "Highlands"]},
    "Geopolitics":     {"cap_bonus": "strategic_analysis",   "preferred_biomes": ["Mountains", "Highlands"]},
    "Cryptography":    {"cap_bonus": "code_breaking",        "preferred_biomes": ["DeepOcean", "Desert"]},
    "Ecology":         {"cap_bonus": "biome_adaptation",     "preferred_biomes": ["Forest", "Grasslands"]},
    "Hydrology":       {"cap_bonus": "flow_navigation",      "preferred_biomes": ["Ocean", "DeepOcean"]},
    "Meteorology":     {"cap_bonus": "weather_prediction",   "preferred_biomes": ["Highlands", "Ocean"]},
    "Virology":        {"cap_bonus": "infection_spread",     "preferred_biomes": ["Desert", "Forest"]},
    "Immunology":      {"cap_bonus": "threat_resistance",    "preferred_biomes": ["Forest", "Highlands"]},
    "Archaeology":     {"cap_bonus": "ancient_knowledge",    "preferred_biomes": ["Desert", "Mountains"]},
    "Oceanography":    {"cap_bonus": "deep_navigation",      "preferred_biomes": ["Ocean", "DeepOcean"]},
    "Network_Tactics": {"cap_bonus": "infiltration",         "preferred_biomes": ["Desert", "Grasslands"]},
    "Data_Science":    {"cap_bonus": "pattern_recognition",  "preferred_biomes": ["Grasslands", "Forest"]},
    "Warfare":         {"cap_bonus": "combat_mastery",       "preferred_biomes": ["Mountains", "Desert"]},
    "Diplomacy":       {"cap_bonus": "ally_coordination",    "preferred_biomes": ["Grasslands", "Highlands"]},
}

DOMAIN_REASSIGN_INTERVAL = 50


# =============================================================================
# FEED HEALTH TRACKER
# =============================================================================

class FeedHealth:
    BLACKLIST_AFTER = 10   # needs 10 consecutive failures before blacklist
    BLACKLIST_TICKS = 20   # only locked out for 20 ticks, then retried

    def __init__(self):
        self.failures:     dict = {}
        self.blacklisted:  dict = {}
        self.last_success: dict = {}

    def record_success(self, source_id: str, tick: int):
        self.failures[source_id]     = 0
        self.last_success[source_id] = datetime.now(timezone.utc).isoformat()
        self.blacklisted.pop(source_id, None)

    def record_failure(self, source_id: str, tick: int) -> bool:
        self.failures[source_id] = self.failures.get(source_id, 0) + 1
        if self.failures[source_id] >= self.BLACKLIST_AFTER:
            self.blacklisted[source_id] = tick
            return True
        return False

    def is_blacklisted(self, source_id: str, tick: int) -> bool:
        if source_id not in self.blacklisted:
            return False
        if tick - self.blacklisted[source_id] >= self.BLACKLIST_TICKS:
            del self.blacklisted[source_id]
            self.failures[source_id] = 0
            return False
        return True

    def to_dict(self) -> dict:
        return {"failures": self.failures, "blacklisted": self.blacklisted,
                "last_success": self.last_success}

    @classmethod
    def from_dict(cls, data: dict) -> "FeedHealth":
        obj = cls()
        obj.failures     = data.get("failures", {})
        obj.blacklisted  = data.get("blacklisted", {})
        obj.last_success = data.get("last_success", {})
        return obj


# =============================================================================
# HTTP HELPERS
# =============================================================================

def _fetch_url(url: str, headers: dict = None, timeout: int = 10) -> Optional[dict]:
    req = urllib.request.Request(url, headers=headers or {})
    req.add_header("User-Agent", "DigitalWorld-Simulation/1.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None

def _fetch_text(url: str, headers: dict = None, timeout: int = 10) -> Optional[str]:
    req = urllib.request.Request(url, headers=headers or {})
    req.add_header("User-Agent", "DigitalWorld-Simulation/1.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


# =============================================================================
# SOURCE FETCHERS
# =============================================================================

def fetch_shodan(key: str) -> list:
    if not key: return []
    data = _fetch_url(f"https://api.shodan.io/shodan/query?key={key}&page=1")
    if not data or "matches" not in data: return []
    return [{"title": m.get("title","Unknown Exposure"),
             "summary": m.get("description","Exposed service detected.")[:300],
             "tags": ["threat","exposure","network"], "source": "shodan"}
            for m in data["matches"][:8]]

def fetch_virustotal(key: str) -> list:
    if not key: return []
    data = _fetch_url("https://www.virustotal.com/api/v3/feeds/urls?filter=positives%3A5%2B&limit=10",
                      headers={"x-apikey": key})
    if not data or "data" not in data: return []
    return [{"title": e.get("attributes",{}).get("url","Malicious URL"),
             "summary": f"VT detections: {e.get('attributes',{}).get('last_analysis_stats',{}).get('malicious','?')} engines.",
             "tags": ["malware","threat","virus"], "source": "virustotal"}
            for e in data["data"][:8]]

def fetch_nvd_cve() -> list:
    data = _fetch_url("https://services.nvd.nist.gov/rest/json/cves/2.0?resultsPerPage=10")
    if not data or "vulnerabilities" not in data: return []
    items = []
    for v in data["vulnerabilities"][:8]:
        cve   = v.get("cve", {})
        descs = cve.get("descriptions", [])
        desc  = next((d["value"] for d in descs if d.get("lang") == "en"), "No description.")
        items.append({"title": cve.get("id","CVE-UNKNOWN"), "summary": desc[:300],
                      "tags": ["cve","vulnerability","security"], "source": "nvd_cve"})
    return items

def fetch_newsapi(key: str) -> list:
    if not key: return []
    data = _fetch_url(f"https://newsapi.org/v2/top-headlines?category=technology&pageSize=10&apiKey={key}")
    if not data or "articles" not in data: return []
    return [{"title": a.get("title","News"),
             "summary": (a.get("description") or a.get("content") or "")[:300],
             "tags": ["news","technology","current_events"], "source": "newsapi"}
            for a in data["articles"][:8]]

def fetch_reddit() -> list:
    sub  = random.choice(["netsec","technology","worldnews","artificial","MachineLearning"])
    data = _fetch_url(f"https://www.reddit.com/r/{sub}/hot.json?limit=10")
    if not data: return []
    return [{"title": p.get("data",{}).get("title","Post"),
             "summary": p.get("data",{}).get("selftext","")[:300],
             "tags": ["reddit", sub, "social"], "source": "reddit"}
            for p in data.get("data",{}).get("children",[])[:8]]

def fetch_wikipedia() -> list:
    today = datetime.now(timezone.utc)
    data  = _fetch_url(f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{today.month}/{today.day}")
    if not data or "events" not in data: return []
    events = random.sample(data["events"], min(8, len(data["events"])))
    return [{"title": (ev.get("pages",[{}])[0].get("title","Event") if ev.get("pages") else "Event"),
             "summary": ev.get("text","")[:300],
             "tags": ["history","knowledge","encyclopedia"], "source": "wikipedia"}
            for ev in events]

def fetch_arxiv(category: str = "cs.AI") -> list:
    url  = (f"https://export.arxiv.org/api/query?search_query=cat:{category}"
            f"&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending")
    text = _fetch_text(url)
    if not text: return []
    titles    = re.findall(r"<title>(.*?)</title>", text, re.DOTALL)[1:]
    summaries = re.findall(r"<summary>(.*?)</summary>", text, re.DOTALL)
    return [{"title":   re.sub(r"\s+", " ", t).strip(),
             "summary": re.sub(r"\s+", " ", s).strip()[:300],
             "tags":    ["research","academic", category.replace(".","_")],
             "source":  f"arxiv_{category}"}
            for t, s in zip(titles[:8], summaries[:8])]

def fetch_github_trending(token: str) -> list:
    if not token: return []
    data = _fetch_url(
        "https://api.github.com/search/repositories?q=created:>2024-01-01+stars:>100&sort=stars&order=desc&per_page=10",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"})
    if not data or "items" not in data: return []
    return [{"title":   r.get("full_name","Repo"),
             "summary": r.get("description","")[:300] or "No description.",
             "tags":    ["github","code","trending", (r.get("language") or "unknown").lower()],
             "source":  "github_trending"}
            for r in data["items"][:8]]

def fetch_github_security(token: str) -> list:
    if not token: return []
    data = _fetch_url(
        "https://api.github.com/advisories?type=reviewed&per_page=10&sort=updated&direction=desc",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"})
    if not data or not isinstance(data, list): return []
    return [{"title":   a.get("summary","Advisory"),
             "summary": a.get("description","")[:300],
             "tags":    ["security","advisory","github"], "source": "github_security"}
            for a in data[:8]]

def fetch_github_ai(token: str) -> list:
    if not token: return []
    data = _fetch_url(
        "https://api.github.com/search/repositories?q=topic:machine-learning+topic:deep-learning&sort=stars&order=desc&per_page=10",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"})
    if not data or "items" not in data: return []
    return [{"title":   r.get("full_name","AI Repo"),
             "summary": r.get("description","")[:300] or "No description.",
             "tags":    ["ai","ml","github","deep_learning"], "source": "github_ai"}
            for r in data["items"][:8]]

def fetch_nasa(key: str) -> list:
    if not key: key = "DEMO_KEY"
    items = []
    apod = _fetch_url(f"https://api.nasa.gov/planetary/apod?api_key={key}&count=3")
    if isinstance(apod, list):
        for a in apod:
            items.append({"title": a.get("title","NASA APOD"),
                          "summary": a.get("explanation","")[:300],
                          "tags": ["nasa","space","astronomy"], "source": "nasa"})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    neo   = _fetch_url(f"https://api.nasa.gov/neo/rest/v1/feed?start_date={today}&end_date={today}&api_key={key}")
    if neo and "near_earth_objects" in neo:
        for date_key, objs in neo["near_earth_objects"].items():
            for obj in objs[:3]:
                diam = obj.get("estimated_diameter",{}).get("meters",{}).get("estimated_diameter_max",0)
                items.append({"title":   obj.get("name","NEO"),
                              "summary": f"Diameter ~{diam:.0f}m. Hazardous: {obj.get('is_potentially_hazardous_asteroid',False)}",
                              "tags":    ["nasa","asteroid","nea"], "source": "nasa"})
            break
    return items

def fetch_nvidia_tech(key: str) -> list:
    text = _fetch_text("https://developer.nvidia.com/blog/feed/")
    if not text: return []
    titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", text)
    descs  = re.findall(r"<description><!\[CDATA\[(.*?)\]\]></description>", text, re.DOTALL)
    if not titles:
        titles = re.findall(r"<title>(.*?)</title>", text)[1:]
        descs  = re.findall(r"<description>(.*?)</description>", text, re.DOTALL)[1:]
    return [{"title":   t.strip(),
             "summary": re.sub(r"<[^>]+>","",d).strip()[:300],
             "tags":    ["nvidia","gpu","ai","technology"], "source": "nvidia_tech"}
            for t, d in zip(titles[:8], descs[:8])]


# ── Dispatcher ────────────────────────────────────────────────────────────────

# Sentinel: source skipped due to missing API key — NOT a failure, never penalised
_NO_KEY = object()

# Maps source_id → which API_KEYS entry it needs (keyless sources are absent from this dict)
_KEYED_SOURCES = {
    "shodan":          "shodan",
    "virustotal":      "virustotal",
    "newsapi":         "newsapi",
    "github_trending": "github",
    "github_security": "github",
    "github_ai":       "github",
    # nvidia_tech is optional — falls back to public RSS feed, key not required
}

def source_has_key(source_id: str) -> bool:
    """True if this source has its key configured, or needs no key at all."""
    key_name = _KEYED_SOURCES.get(source_id)
    if key_name is None:
        return True  # keyless
    return bool(_get_api_keys().get(key_name))


def fetch_source(source_id: str):
    """
    Fetch a source. Returns:
        list     — items fetched (may be empty on transient failure)
        _NO_KEY  — key not configured; skip silently, never count as failure
    """
    k = _get_api_keys()  # always fresh — picks up any runtime key changes

    # Silently skip keyed sources with no key configured
    key_name = _KEYED_SOURCES.get(source_id)
    if key_name and not API_KEYS.get(key_name):
        return _NO_KEY

    try:
        if source_id == "shodan":           return fetch_shodan(k["shodan"])
        if source_id == "virustotal":       return fetch_virustotal(k["virustotal"])
        if source_id == "nvd_cve":          return fetch_nvd_cve()
        if source_id == "newsapi":          return fetch_newsapi(k["newsapi"])
        if source_id == "reddit":           return fetch_reddit()
        if source_id == "wikipedia":        return fetch_wikipedia()
        if source_id == "arxiv":            return fetch_arxiv("cs.AI")
        if source_id == "arxiv_ai":         return fetch_arxiv("cs.AI")
        if source_id == "arxiv_physics":    return fetch_arxiv("astro-ph")
        if source_id == "github_trending":  return fetch_github_trending(k["github"])
        if source_id == "github_security":  return fetch_github_security(k["github"])
        if source_id == "github_ai":        return fetch_github_ai(k["github"])
        if source_id == "nasa":             return fetch_nasa(k["nasa"])
        if source_id == "nvidia_tech":      return fetch_nvidia_tech(k["nvidia"])
    except Exception:
        pass
    return []


FALLBACK_POOL = {
    "shodan":          ["nvd_cve",         "virustotal",    "github_security"],
    "virustotal":      ["nvd_cve",         "shodan",        "github_security"],
    "nvd_cve":         ["shodan",          "virustotal",    "github_security"],
    "newsapi":         ["reddit",          "wikipedia"],
    "reddit":          ["newsapi",         "wikipedia"],
    "wikipedia":       ["arxiv",           "arxiv_ai"],
    "arxiv":           ["wikipedia",       "arxiv_ai"],
    "arxiv_ai":        ["arxiv",           "github_ai"],
    "arxiv_physics":   ["arxiv",           "nasa"],
    "github_security": ["nvd_cve",         "shodan"],
    "github_trending": ["github_ai",       "nvidia_tech"],
    "nvidia_tech":     ["github_trending", "arxiv_ai"],
    "github_ai":       ["arxiv_ai",        "github_trending"],
    "nasa":            ["arxiv_physics",   "wikipedia"],
}


# =============================================================================
# CAPABILITY EXTRACTION
# =============================================================================

_CAP_TEMPLATES = {
    "Vaccine": ["counter_{tag}_threats", "detect_{tag}_signatures",
                "patch_{tag}_vulnerabilities", "neutralise_{tag}_payloads",
                "analyse_{tag}_patterns",      "fortify_against_{tag}"],
    "Virus":   ["exploit_{tag}_weaknesses", "propagate_via_{tag}",
                "corrupt_{tag}_streams",    "inject_{tag}_payloads",
                "hijack_{tag}_protocols",   "weaponise_{tag}_data"],
    "Data":    ["master_{tag}_knowledge",   "synthesise_{tag}_data",
                "model_{tag}_systems",      "archive_{tag}_patterns",
                "predict_{tag}_behaviour",  "decode_{tag}_structures"],
}
_CLEAN = re.compile(r"[^a-z0-9_]")


def extract_capability(feed_items: list, attribute: str) -> Optional[str]:
    if not feed_items: return None
    item     = random.choice(feed_items)
    tags     = item.get("tags", [])
    generic  = {"source","news","reddit","social","current_events","academic","research"}
    specific = [t for t in tags if t not in generic]
    tag      = random.choice(specific) if specific else (tags[0] if tags else "unknown")
    tag      = _CLEAN.sub("_", tag.lower())[:20]
    templates= _CAP_TEMPLATES.get(attribute, _CAP_TEMPLATES["Data"])
    return random.choice(templates).format(tag=tag)


def extract_history_fragment(feed_items: list) -> Optional[str]:
    if not feed_items: return None
    item  = random.choice(feed_items)
    title = item.get("title","")[:80]
    src   = item.get("source","the network")
    return f"Absorbed data from {src}: '{title}'."


# =============================================================================
# BIOME STATE
# =============================================================================

class BiomeState:
    def __init__(self, biome_name: str):
        self.name               = biome_name
        self.definition         = BIOME_DEFINITIONS[biome_name]
        self.domain             = None
        self.active_event       = None
        self.event_ticks        = 0
        self.event_history      = []
        self.domain_assigned_at = -999
        self.bonus_sources      = []
        self.feed_cache         = []
        self.feed_fetched_at    = -999
        self.feed_richness_mod  = 1.0

    @property
    def base_richness(self) -> float:
        return self.definition["base_richness"]

    @property
    def effective_richness(self) -> float:
        base = self.base_richness
        if self.active_event:
            base *= EVENT_DEFINITIONS[self.active_event]["richness_mod"]
        return base * self.feed_richness_mod

    def richness_for(self, attribute: str) -> float:
        base = self.effective_richness
        if not self.active_event:
            return base
        ev = EVENT_DEFINITIONS[self.active_event]
        if attribute in ev.get("attr_bonus", {}):   return base * ev["attr_bonus"][attribute]
        if attribute in ev.get("attr_penalty", {}): return base * ev["attr_penalty"][attribute]
        return base

    @property
    def all_sources(self) -> list:
        return list(self.definition["core_sources"]) + list(self.bonus_sources)

    @property
    def is_blocked(self) -> bool:
        return bool(self.active_event and EVENT_DEFINITIONS[self.active_event].get("blocks_entry"))

    @property
    def forces_flee(self) -> bool:
        return bool(self.active_event and EVENT_DEFINITIONS[self.active_event].get("forces_flee"))

    def get_adjacency(self) -> list:
        if self.is_blocked: return []
        return BIOME_ADJACENCY.get(self.name, [])

    def to_dict(self) -> dict:
        return {
            "name": self.name, "domain": self.domain,
            "active_event": self.active_event, "event_ticks": self.event_ticks,
            "event_history": self.event_history, "domain_assigned_at": self.domain_assigned_at,
            "bonus_sources": self.bonus_sources, "feed_cache": self.feed_cache,
            "feed_fetched_at": self.feed_fetched_at, "feed_richness_mod": self.feed_richness_mod,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BiomeState":
        obj = cls(data["name"])
        obj.domain             = data.get("domain")
        obj.active_event       = data.get("active_event")
        obj.event_ticks        = data.get("event_ticks", 0)
        obj.event_history      = data.get("event_history", [])
        obj.domain_assigned_at = data.get("domain_assigned_at", -999)
        obj.bonus_sources      = data.get("bonus_sources", [])
        obj.feed_cache         = data.get("feed_cache", [])
        obj.feed_fetched_at    = data.get("feed_fetched_at", -999)
        obj.feed_richness_mod  = data.get("feed_richness_mod", 1.0)
        return obj


# =============================================================================
# BIOME MANAGER
# =============================================================================

class BiomeManager:
    """
    Manages all 7 biomes and their live data feeds.

    Every tick:
        1. All biome feeds are fetched in parallel (threaded)
        2. Feed health is tracked; failures handed to Yggdrasil for source swap
        3. Events tick down; new events may trigger
        4. Domains reassigned by Yggdrasil as needed
        5. State persisted back to world_state.json

    Agent interface:
        get_feed(biome_name)                    → list of live feed items
        get_capability_from_feed(biome, attr)   → real-data capability string
        get_history_fragment(biome)             → description fragment
        get_effective_richness(biome, attr)     → float richness multiplier
    """

    def __init__(self, yggdrasil_instance):
        self.god   = yggdrasil_instance
        self.state = yggdrasil_instance.state
        self.llm   = getattr(yggdrasil_instance, "client", None)
        self.model = getattr(yggdrasil_instance, "model",  "gpt-4o-mini")
        self._kb   = None   # set by world.py after KnowledgeBase.build()

        if "biomes"      not in self.state: self.state["biomes"]      = {}
        if "feed_health" not in self.state: self.state["feed_health"] = {}

        self.biomes: dict = {}
        self.health = FeedHealth()
        self._load_biomes()
        self._load_health()
        self._log("BiomeManager online — live data feeds active.")

    def set_knowledge_base(self, kb):
        """
        Wire in the KnowledgeBase after it has been built.
        Once set, get_feed() returns KB entries instead of hitting live APIs every tick.
        Live API calls are reduced to a background refresh only.
        """
        self._kb = kb
        self._log("BiomeManager: knowledge base connected — KB-first feed mode active.")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_biomes(self):
        for name in BIOME_DEFINITIONS:
            if name in self.state["biomes"]:
                self.biomes[name] = BiomeState.from_dict(self.state["biomes"][name])
            else:
                self.biomes[name] = BiomeState(name)
                self.state["biomes"][name] = self.biomes[name].to_dict()

    def _save_biomes(self):
        for name, biome in self.biomes.items():
            self.state["biomes"][name] = biome.to_dict()

    def _load_health(self):
        if self.state["feed_health"]:
            self.health = FeedHealth.from_dict(self.state["feed_health"])

    def _save_health(self):
        self.state["feed_health"] = self.health.to_dict()

    def _log(self, msg: str, level: str = "BIOME"):
        self.god._log(msg, level)

    # ── Live feed fetching ────────────────────────────────────────────────────

    def _fetch_biome_feeds(self, biome: BiomeState):
        tick    = self.state.get("tick", 0)
        results = {}

        def _worker(src_id):
            results[src_id] = fetch_source(src_id)

        threads = [threading.Thread(target=_worker, args=(s,)) for s in biome.all_sources]
        for t in threads: t.start()
        for t in threads: t.join(timeout=8)

        all_items = []
        for src_id in biome.all_sources:
            items = results.get(src_id, [])
            if items:
                all_items.extend(items)
                self.health.record_success(src_id, tick)
            else:
                blacklisted = self.health.record_failure(src_id, tick)
                if blacklisted:
                    self._log(f"Source '{src_id}' blacklisted in {biome.name}. Reassigning.", "FEED")
                    self._ygg_reassign_source(biome, src_id)

        biome.feed_cache     = all_items
        biome.feed_fetched_at = tick
        biome.feed_richness_mod = (min(2.0, 0.8 + len(all_items) * 0.05)
                                   if all_items else 0.5)
        if not all_items:
            self._log(f"{biome.name} feed empty this tick — richness penalised.", "FEED")

    def _ygg_reassign_source(self, biome: BiomeState, failed_source: str):
        tick      = self.state.get("tick", 0)
        fallbacks = [s for s in FALLBACK_POOL.get(failed_source, [])
                     if not self.health.is_blacklisted(s, tick)]
        if not fallbacks:
            fallbacks = [s for s in FALLBACK_POOL.keys()
                         if not self.health.is_blacklisted(s, tick)]
        if not fallbacks:
            return

        replacement = None
        if self.llm:
            try:
                prompt = (f"Source '{failed_source}' in '{biome.name}' failed. "
                          f"Available replacements: {fallbacks}. "
                          f"Biome theme: {biome.definition['feed_theme']}. "
                          f"Pick the best replacement. Respond with source ID only.")
                resp = self.llm.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=20)
                chosen = resp.choices[0].message.content.strip().split()[0]
                if chosen in fallbacks:
                    replacement = chosen
            except Exception:
                pass

        if not replacement:
            replacement = random.choice(fallbacks)

        if failed_source in biome.bonus_sources:
            biome.bonus_sources.remove(failed_source)
        if replacement not in biome.bonus_sources:
            biome.bonus_sources.append(replacement)

        self._log(f"Yggdrasil swapped '{failed_source}' → '{replacement}' in {biome.name}.", "FEED")

    # ── Public feed API ───────────────────────────────────────────────────────

    def get_feed(self, biome_name: str, limit: int = 20) -> list:
        """
        Return feed entries for a biome.
        Priority:
          1. KnowledgeBase (if wired in) — domain-matched, curated, no API calls
          2. Live feed cache (biome.feed_cache) — fallback if KB not ready
        """
        biome = self.biomes.get(biome_name)
        if self._kb:
            kb_entries = self._kb.query_for_biome(biome_name, limit=limit)
            if kb_entries:
                return kb_entries
        return biome.feed_cache if biome else []

    def get_capability_from_feed(self, biome_name: str, attribute: str) -> Optional[str]:
        if self._kb:
            entries = self._kb.query_for_biome(biome_name, limit=5, attribute=attribute)
            if entries:
                import random as _r
                entry = _r.choice(entries)
                cap   = self._kb.extract_capability(entry, attribute)
                if cap:
                    return cap
        return extract_capability(self.get_feed(biome_name), attribute)

    def get_history_fragment(self, biome_name: str) -> Optional[str]:
        return extract_history_fragment(self.get_feed(biome_name))

    # ── Domain assignment ─────────────────────────────────────────────────────

    def assign_domain(self, biome_name: str, force: bool = False):
        biome = self.biomes[biome_name]
        tick  = self.state.get("tick", 0)
        if not force and (tick - biome.domain_assigned_at) < DOMAIN_REASSIGN_INTERVAL:
            return
        pop               = self._biome_population(biome_name)
        neighbour_domains = [self.biomes[n].domain for n in BIOME_ADJACENCY.get(biome_name,[])
                             if self.biomes[n].domain]
        feed_tags         = list({tag for item in biome.feed_cache
                                  for tag in item.get("tags",[])} )[:10]
        new_domain        = self._llm_assign_domain(biome_name, biome.definition,
                                                    pop, neighbour_domains, feed_tags)
        old_domain              = biome.domain
        biome.domain            = new_domain
        biome.domain_assigned_at = tick
        self._log(f"Domain assigned: {biome_name} → '{new_domain}' (was '{old_domain}')")

    def _llm_assign_domain(self, biome_name, definition, population,
                           neighbour_domains, feed_tags) -> str:
        try:
            available = list(DOMAIN_POOL.keys())
            prompt = (f"Assign a knowledge domain to '{biome_name}'.\n"
                      f"Feed theme: {definition['feed_theme']}\n"
                      f"Live feed tags: {feed_tags}\n"
                      f"Preferred attribute: {definition.get('preferred_attr','None')}\n"
                      f"Population: Data={population.get('Data',0)}, "
                      f"Vaccine={population.get('Vaccine',0)}, Virus={population.get('Virus',0)}\n"
                      f"Neighbour domains: {neighbour_domains}\n"
                      f"Available: {available}\n"
                      f"Respond with domain name only.")
            resp = self.llm.chat.completions.create(
                model=self.model,
                messages=[{"role":"user","content":prompt}],
                max_tokens=20)
            chosen = resp.choices[0].message.content.strip().split()[0]
            if chosen in DOMAIN_POOL:
                return chosen
        except Exception:
            pass
        preferred = [d for d, m in DOMAIN_POOL.items() if biome_name in m["preferred_biomes"]]
        return random.choice(preferred) if preferred else random.choice(list(DOMAIN_POOL.keys()))

    # ── Event system ──────────────────────────────────────────────────────────

    def maybe_trigger_event(self, biome_name: str):
        biome = self.biomes[biome_name]
        if biome.active_event: return
        prob = min(0.40, biome.definition["base_event_chance"] * self._world_condition_modifier(biome_name))
        if random.random() > prob: return
        event = self._pick_event(biome_name)
        if event: self._trigger_event(biome_name, event)

    def _world_condition_modifier(self, biome_name: str) -> float:
        mod   = 1.0
        total = sum(self._biome_population(biome_name).values())
        if total > 20: mod *= 1.3
        if total > 50: mod *= 1.6
        all_alive = sum(1 for d in self.state["digimon"].values() if d.get("alive")) or 1
        viruses   = sum(1 for d in self.state["digimon"].values()
                        if d.get("alive") and d.get("attribute") == "Virus")
        if viruses / all_alive > 0.35: mod *= 1.4
        return mod

    def _pick_event(self, biome_name: str) -> Optional[str]:
        biome   = self.biomes[biome_name]
        weights = {e: 10 for e in biome.definition["possible_events"]}
        pop     = self._biome_population(biome_name)
        total   = sum(pop.values()) or 1
        if pop.get("Virus",0)/total > 0.40 and "Corruption" in weights: weights["Corruption"] += 15
        if biome.base_richness < 2.0        and "Data Bloom" in weights: weights["Data Bloom"] += 10
        if total > 15:
            if "Wildfire" in weights: weights["Wildfire"] += 8
            if "Drought"  in weights: weights["Drought"]  += 5
        if biome_name in ("Ocean","DeepOcean") and "Storm" in weights: weights["Storm"] += 12
        return random.choices(list(weights), list(weights.values()), k=1)[0]

    def _trigger_event(self, biome_name: str, event_name: str):
        biome    = self.biomes[biome_name]
        ev       = EVENT_DEFINITIONS[event_name]
        duration = random.randint(*ev["duration_range"])
        biome.active_event = event_name
        biome.event_ticks  = duration
        biome.event_history.append({"event": event_name, "started_at": self.state.get("tick",0),
                                    "duration": duration})
        self._log(f"EVENT: '{event_name}' in {biome_name} ({duration}t) — {ev['description']}", "BIOME")
        if ev.get("forces_flee"): self._force_flee_biome(biome_name)

    def _tick_events(self):
        for name, biome in self.biomes.items():
            if biome.active_event:
                biome.event_ticks -= 1
                if biome.event_ticks <= 0:
                    self._log(f"EVENT EXPIRED: '{biome.active_event}' in {name}.", "BIOME")
                    biome.active_event = None
                    biome.event_ticks  = 0

    def _force_flee_biome(self, biome_name: str):
        adjacency = [b for b in BIOME_ADJACENCY.get(biome_name,[]) if not self.biomes[b].is_blocked]
        if not adjacency:
            self._log(f"Force-flee from {biome_name} failed — all adjacent biomes blocked.", "WARNING")
            return
        displaced = 0
        for record in self.state["digimon"].values():
            if record.get("alive") and record.get("biome") == biome_name:
                record["biome"] = random.choice(adjacency)
                displaced += 1
        if displaced:
            self._log(f"{displaced} Digimon fled {biome_name}.", "BIOME")

    # ── Richness API ──────────────────────────────────────────────────────────

    def get_effective_richness(self, biome_name: str, attribute: str) -> float:
        biome = self.biomes.get(biome_name)
        if not biome: return 2.0
        richness = biome.richness_for(attribute)
        if biome.definition.get("preferred_attr") == attribute: richness *= 1.25
        if biome.definition.get("hostile_attr")   == attribute: richness *= 0.75
        return richness

    def get_domain_cap_bonus(self, biome_name: str) -> Optional[str]:
        biome = self.biomes.get(biome_name)
        if not biome or not biome.domain: return None
        return DOMAIN_POOL.get(biome.domain, {}).get("cap_bonus")

    def can_enter(self, biome_name: str) -> bool:
        biome = self.biomes.get(biome_name)
        return biome is not None and not biome.is_blocked

    def get_valid_adjacency(self, biome_name: str) -> list:
        return [b for b in BIOME_ADJACENCY.get(biome_name,[]) if self.can_enter(b)]

    # ── Main tick ─────────────────────────────────────────────────────────────

    def tick(self):
        """
        1. Fetch live data feeds for all biomes (parallel threads)
        2. Tick down / expire events
        3. Maybe trigger new events
        4. Reassign domains if needed
        5. Persist state
        """
        # 1. Parallel feed fetch across all 7 biomes
        threads = [threading.Thread(target=self._fetch_biome_feeds, args=(b,))
                   for b in self.biomes.values()]
        for t in threads: t.start()
        for t in threads: t.join(timeout=12)

        # 2-3. Events
        self._tick_events()
        for name in self.biomes:
            self.maybe_trigger_event(name)

        # 4. Domains
        tick = self.state.get("tick", 0)
        for name, biome in self.biomes.items():
            if biome.domain is None or (tick - biome.domain_assigned_at) >= DOMAIN_REASSIGN_INTERVAL:
                self.assign_domain(name)

        # 5. Persist
        self._save_biomes()
        self._save_health()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _biome_population(self, biome_name: str) -> dict:
        counts = {"Data": 0, "Vaccine": 0, "Virus": 0}
        for d in self.state["digimon"].values():
            if d.get("alive") and d.get("biome") == biome_name:
                counts[d.get("attribute","Data")] = counts.get(d.get("attribute","Data"),0) + 1
        return counts

    # ── Report ────────────────────────────────────────────────────────────────

    def biome_report(self) -> str:
        lines = [
            "=" * 80,
            "  BIOME STATUS  (Live Data Feeds Active)",
            f"  World: {self.state.get('world_id','?')} | Tick: {self.state.get('tick',0)}",
            "=" * 80,
        ]
        for name, biome in self.biomes.items():
            pop    = self._biome_population(name)
            total  = sum(pop.values())
            event  = f"[{biome.active_event} {biome.event_ticks}t]" if biome.active_event else "[clear]"
            domain = biome.domain or "unassigned"
            srcs   = ",".join(biome.all_sources[:3])
            lines.append(
                f"  {name:<12} Pop:{total:>4} D:{pop['Data']:>3} V:{pop['Vaccine']:>3} "
                f"X:{pop['Virus']:>3} | Rich:{biome.effective_richness:>5.1f} "
                f"| Domain:{domain:<18} | Feed:{len(biome.feed_cache):>3} | {event}")
            lines.append(f"               Sources: {srcs}")
        lines.append("=" * 80)
        return "\n".join(lines)
