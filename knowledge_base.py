"""
╔══════════════════════════════════════════════════════════════════╗
║           DIGITAL WORLD — KNOWLEDGE BASE CRAWLER                ║
║                                                                  ║
║  Yggdrasil reads the internet before creating a world.           ║
║  Run once at startup. All biomes feed from the result locally.   ║
║  No live API calls during the sim after this runs.               ║
║                                                                  ║
║  knowledge_base/                                                 ║
║      art.json            history.json      general_knowledge.json ║
║      tech.json           machine_learning.json                   ║
║      cybersecurity.json  offensive_security.json                 ║
║      malware_analysis.json                                       ║
║      science/                                                    ║
║          physical_sciences.json  life_sciences.json              ║
║          medical_sciences.json   engineering.json                ║
║          earth_sciences.json     cognitive_sciences.json         ║
║                                                                  ║
║  Usage:                                                          ║
║    python knowledge_base.py build     # first run                ║
║    python knowledge_base.py rebuild   # force refresh            ║
║    python knowledge_base.py status    # check freshness          ║
║                                                                  ║
║  In code:                                                        ║
║    kb = KnowledgeBase()                                          ║
║    kb.build(force=False)                                         ║
║    entries = kb.query_for_biome("Desert", limit=10)              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, sys, json, time, random, hashlib, re
import urllib.request, urllib.parse, urllib.error
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
KB_DIR             = os.getenv("KB_DIR", "knowledge_base")
SCIENCE_DIR        = os.path.join(KB_DIR, "science")
FRESHNESS_DAYS     = int(os.getenv("KB_FRESHNESS_DAYS",  "3"))
DATE_RANGE_YEARS   = int(os.getenv("KB_DATE_RANGE_YEARS","3"))
MAX_ENTRIES        = int(os.getenv("KB_MAX_ENTRIES",     "500"))
HTTP_TIMEOUT       = 12
CRAWL_DELAY        = 0.3

def _cutoff_year()  -> int:  return datetime.utcnow().year - DATE_RANGE_YEARS
def _cutoff_date()  -> str:
    return (datetime.utcnow() - timedelta(days=DATE_RANGE_YEARS*365)).strftime("%Y-%m-%d")

# ── Domain definitions ────────────────────────────────────────────────────────
DOMAINS = {
    "art": {
        "description": "Visual art, literature, music, sound — CC0 and public domain only. No paid work.",
        "biomes":     ["Forest", "Ocean", "ArtBiome"],
        "attributes": ["Data"],
        "sources":    ["gutenberg_literature","open_library_fiction","met_museum",
                       "smithsonian_art","nga_art","cleveland_art","aic_art",
                       "freesound_cc0","free_music_archive","internet_archive_texts",
                       "openverse_cc0"],
    },
    "history": {
        "description": "World history, civilisations, warfare, political history",
        "biomes":     ["Grasslands","ArtBiome"],
        "attributes": ["Data","Vaccine"],
        "sources":    ["gutenberg_history","open_library_history","wikipedia_history"],
    },
    "general_knowledge": {
        "description": "Encyclopaedic breadth — culture, geography, science overview",
        "biomes":     ["Grasslands"],
        "attributes": ["Data"],
        "sources":    ["wikipedia_general","open_library_general"],
    },
    "tech": {
        "description": "Software, hardware, systems architecture, developer tools",
        "biomes":     ["Mountains"],
        "attributes": ["Data","Vaccine"],
        "sources":    ["github_trending","openalex_cs","semantic_scholar_cs"],
    },
    "machine_learning": {
        "description": "AI/ML papers, model architectures, training methods, benchmarks",
        "biomes":     ["DeepOcean"],
        "attributes": ["Data"],
        "sources":    ["arxiv_ai","semantic_scholar_ml","openalex_ai"],
    },
    "cybersecurity": {
        "description": "Defence frameworks, compliance, blue team, vulnerability management",
        "biomes":     ["Highlands","Desert"],
        "attributes": ["Vaccine"],
        "sources":    ["nvd_cve","cisa_advisories","circl_cve"],
    },
    "offensive_security": {
        "description": "Penetration testing, exploit techniques, red team methodology",
        "biomes":     ["Desert","Highlands"],
        "attributes": ["Virus"],
        "sources":    ["alienvault_otx","exploitdb","urlhaus"],
    },
    "malware_analysis": {
        "description": "Reverse engineering, behavioural analysis, malware families, IOCs",
        "biomes":     ["Desert"],
        "attributes": ["Virus","Vaccine"],
        "sources":    ["malware_bazaar","abuseipdb_reports","honeydb"],
    },
    "science/physical_sciences": {
        "description": "Physics, chemistry, materials science, thermodynamics",
        "biomes":     ["Ocean","Mountains"],
        "attributes": ["Data"],
        "sources":    ["arxiv_physics","openalex_physics","openalex_chemistry"],
    },
    "science/life_sciences": {
        "description": "Biology, biochemistry, genetics, molecular biology, ecology",
        "biomes":     ["Forest","Ocean"],
        "attributes": ["Data","Vaccine"],
        "sources":    ["pubmed_biology","openalex_biology","semantic_scholar_bio"],
    },
    "science/medical_sciences": {
        "description": "Clinical medicine, pharmacology, pathology, all medical specialties",
        "biomes":     ["Forest"],
        "attributes": ["Vaccine"],
        "sources":    ["pubmed_medicine","openalex_medicine"],
    },
    "science/engineering": {
        "description": "Mechanical, electrical, civil, chemical, aerospace, biomedical engineering",
        "biomes":     ["Mountains"],
        "attributes": ["Data","Vaccine"],
        "sources":    ["openalex_engineering","arxiv_engineering","semantic_scholar_eng"],
    },
    "science/earth_sciences": {
        "description": "Geology, climate science, oceanography, atmospheric science",
        "biomes":     ["Ocean","Highlands"],
        "attributes": ["Data"],
        "sources":    ["nasa_earth","openalex_earth","noaa_data"],
    },
    "science/cognitive_sciences": {
        "description": "Neurology, psychology, psychiatry, cognitive science, consciousness",
        "biomes":     ["DeepOcean","ArtBiome"],
        "attributes": ["Data"],
        "sources":    ["pubmed_neuro","semantic_scholar_psych","openalex_psych"],
    },
}

BIOME_DOMAINS = {
    "Desert":     ["cybersecurity","offensive_security","malware_analysis"],
    "Grasslands": ["general_knowledge","history"],
    "Forest":     ["art","science/life_sciences","science/medical_sciences"],
    "Highlands":  ["cybersecurity","offensive_security"],
    "Mountains":  ["tech","science/engineering","science/physical_sciences"],
    "Ocean":      ["science/earth_sciences","science/physical_sciences","art"],
    "DeepOcean":  ["machine_learning","science/cognitive_sciences"],
    "ArtBiome":   ["art","history","science/cognitive_sciences"],
}

ATTRIBUTE_DOMAINS = {
    "Vaccine": ["cybersecurity","science/medical_sciences","science/life_sciences","malware_analysis"],
    "Virus":   ["offensive_security","malware_analysis","cybersecurity"],
    "Data":    ["machine_learning","tech","science/physical_sciences",
                "science/cognitive_sciences","art","general_knowledge"],
}

# ── HTTP helpers ──────────────────────────────────────────────────────────────
HTTP_TIMEOUT  = 10      # seconds for connect
READ_TIMEOUT  = 8       # seconds max for reading response
MAX_RESPONSE  = 512_000 # bytes — skip sources returning huge payloads

def _get(url, headers=None, debug=False):
    import socket
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(HTTP_TIMEOUT)
        req = urllib.request.Request(url, headers={
            "User-Agent": "DigitalWorld-KB/1.0 (educational sim)",
            **(headers or {})})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            # Read with hard size cap — skip sources that return massive payloads
            raw = r.read(MAX_RESPONSE)
            return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as e:
        if debug or os.getenv("KB_DEBUG"):
            print(f"[KB] FETCH FAILED: {url[:60]}\n  → {type(e).__name__}: {e}")
        return None
    finally:
        socket.setdefaulttimeout(old_timeout)

def _get_text(url):
    import socket
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(HTTP_TIMEOUT)
        req = urllib.request.Request(url,
            headers={"User-Agent": "DigitalWorld-KB/1.0"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return r.read(MAX_RESPONSE).decode("utf-8", errors="replace")
    except Exception:
        return None
    finally:
        socket.setdefaulttimeout(old_timeout)

def _entry(title, summary, source, date=None, tags=None, url=None):
    uid = hashlib.md5(f"{source}:{title}".encode()).hexdigest()[:12]
    return {"id": uid, "title": title[:200], "summary": summary[:800],
            "source": source, "date": date or datetime.utcnow().strftime("%Y-%m-%d"),
            "tags": tags or [], "url": url or ""}

# ── Source fetchers ───────────────────────────────────────────────────────────

def fetch_gutenberg_literature(limit=32):
    # Gutendex: topic= searches bookshelves/subjects, copyright=false = public domain
    # max 32 results per page (Gutendex hard limit)
    d = _get("https://gutendex.com/books/?topic=fiction&languages=en&copyright=false")
    if not d: return []
    return [_entry(
        b.get("title",""),
        f"Authors: {', '.join(a['name'] for a in b.get('authors',[])[:3])}. "
        f"Subjects: {', '.join(b.get('subjects',[])[:4])}.",
        "gutenberg",
        tags=["literature","fiction","public_domain"]
    ) for b in d.get("results",[])[:limit]]

def fetch_gutenberg_history(limit=32):
    d = _get("https://gutendex.com/books/?topic=history&languages=en&copyright=false")
    if not d: return []
    return [_entry(
        b.get("title",""),
        f"Authors: {', '.join(a['name'] for a in b.get('authors',[])[:3])}. "
        f"Subjects: {', '.join(b.get('subjects',[])[:4])}.",
        "gutenberg",
        tags=["history","public_domain"]
    ) for b in d.get("results",[])[:limit]]

def fetch_gutenberg_science(limit=32):
    d = _get("https://gutendex.com/books/?topic=science&languages=en&copyright=false")
    if not d: return []
    return [_entry(
        b.get("title",""),
        f"Authors: {', '.join(a['name'] for a in b.get('authors',[])[:3])}. "
        f"Subjects: {', '.join(b.get('subjects',[])[:4])}.",
        "gutenberg",
        tags=["science","public_domain"]
    ) for b in d.get("results",[])[:limit]]

def fetch_gutenberg_philosophy(limit=32):
    d = _get("https://gutendex.com/books/?topic=philosophy&languages=en&copyright=false")
    if not d: return []
    return [_entry(
        b.get("title",""),
        f"Authors: {', '.join(a['name'] for a in b.get('authors',[])[:3])}. "
        f"Subjects: {', '.join(b.get('subjects',[])[:4])}.",
        "gutenberg",
        tags=["philosophy","public_domain"]
    ) for b in d.get("results",[])[:limit]]

def fetch_open_library_fiction(limit=40):
    d = _get(f"https://openlibrary.org/search.json?subject=fiction&language=eng&limit={limit}"
             f"&fields=title,author_name,subject,first_publish_year")
    if not d: return []
    return [_entry(b.get("title",""),
            f"By {', '.join(b.get('author_name',['?'])[:2])}. Year: {b.get('first_publish_year','?')}. "
            f"Subjects: {', '.join(b.get('subject',[])[:3])}.", "open_library",
            tags=["fiction","literature"]) for b in d.get("docs",[])[:limit]]

def fetch_open_library_history(limit=40):
    d = _get(f"https://openlibrary.org/search.json?subject=history&language=eng&limit={limit}"
             f"&fields=title,author_name,first_publish_year")
    if not d: return []
    return [_entry(b.get("title",""),
            f"By {', '.join(b.get('author_name',['?'])[:2])}. Year: {b.get('first_publish_year','?')}.",
            "open_library", tags=["history"]) for b in d.get("docs",[])[:limit]]

def fetch_open_library_general(limit=40):
    d = _get(f"https://openlibrary.org/search.json?q=knowledge&language=eng&limit={limit}"
             f"&fields=title,author_name,subject")
    if not d: return []
    return [_entry(b.get("title",""),
            f"By {', '.join(b.get('author_name',['?'])[:2])}. "
            f"Subjects: {', '.join(b.get('subject',[])[:3])}.", "open_library",
            tags=["general"]) for b in d.get("docs",[])[:limit]]

def fetch_met_museum(limit=40):
    s = _get("https://collectionapi.metmuseum.org/public/collection/v1/search"
             "?hasImages=true&isPublicDomain=true&q=art")
    if not s: return []
    ids = random.sample((s.get("objectIDs") or [])[:500], min(limit, 40))
    out = []
    for oid in ids:
        o = _get(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}")
        if not o or not o.get("isPublicDomain"): continue
        out.append(_entry(o.get("title","Untitled"),
            f"{o.get('objectName','Art')} by {o.get('artistDisplayName','Unknown')}. "
            f"Period: {o.get('period','?')}. Medium: {o.get('medium','?')}.",
            "met_museum", date=str(o.get("objectDate","")),
            tags=["visual_art","cc0","museum"], url=o.get("objectURL","")))
        time.sleep(0.1)
    return out

def fetch_smithsonian_art(limit=40):
    d = _get(f"https://api.si.edu/openaccess/api/v1.0/search?q=art&rows={limit}&api_key=OPENACCESS")
    if not d: return []
    out = []
    for row in d.get("response",{}).get("rows",[])[:limit]:
        desc = row.get("content",{}).get("descriptiveNonRepeating",{})
        out.append(_entry(desc.get("title",{}).get("content","Untitled"),
            f"Unit: {row.get('unitCode','?')}.", "smithsonian",
            tags=["visual_art","museum"], url=desc.get("record_link","")))
    return out

def fetch_nga_art(limit=40):
    d = _get(f"https://api.nga.gov/art/tms/objects?limit={limit}&offset={random.randint(0,2000)}")
    if not d: return []
    items = d.get("data",{}).get("objects",{}).get("items",[])
    return [_entry(o.get("title","Untitled"),
            f"Artist: {o.get('attributionInverted','?')}. Year: {o.get('displayDate','?')}. "
            f"Medium: {o.get('medium','?')}.", "nga",
            tags=["visual_art","cc0"]) for o in items[:limit]]

def fetch_cleveland_art(limit=40):
    d = _get(f"https://openaccess-api.clevelandart.org/api/artworks/"
             f"?has_image=1&cc0=1&limit={limit}&skip={random.randint(0,5000)}")
    if not d: return []
    return [_entry(o.get("title","Untitled"),
            f"Artist: {(o.get('creators') or [{}])[0].get('description','?')}. "
            f"Date: {o.get('creation_date','?')}. Type: {o.get('type','?')}.",
            "cleveland_art", tags=["visual_art","cc0"], url=o.get("url",""))
            for o in d.get("data",[])[:limit]]

def fetch_aic_art(limit=40):
    d = _get(f"https://api.artic.edu/api/v1/artworks?limit={limit}&page={random.randint(1,50)}"
             f"&fields=id,title,artist_display,date_display,medium_display,style_title")
    if not d: return []
    return [_entry(o.get("title","Untitled"),
            f"Artist: {o.get('artist_display','?')}. Date: {o.get('date_display','?')}. "
            f"Medium: {o.get('medium_display','?')}.", "aic",
            tags=["visual_art","cc0"],
            url=f"https://www.artic.edu/artworks/{o.get('id','')}") for o in d.get("data",[])[:limit]]

def fetch_wikipedia_general(limit=40):
    out = []
    for _ in range(min(limit, 40)):
        d = _get("https://en.wikipedia.org/api/rest_v1/page/random/summary")
        if d:
            out.append(_entry(d.get("title",""), d.get("extract","")[:400], "wikipedia",
                tags=["general_knowledge"],
                url=d.get("content_urls",{}).get("desktop",{}).get("page","")))
        time.sleep(CRAWL_DELAY)
    return out

def fetch_wikipedia_history(limit=40):
    topics = ["World_War_II","Roman_Empire","Ancient_Egypt","Ming_dynasty",
              "Byzantine_Empire","Cold_War","Ottoman_Empire","Mongol_Empire",
              "Renaissance","Industrial_Revolution","French_Revolution",
              "British_Empire","Han_dynasty","Aztec_Empire"]
    out = []
    for t in random.sample(topics, min(limit, len(topics))):
        d = _get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{t}")
        if d:
            out.append(_entry(d.get("title",t), d.get("extract","")[:400], "wikipedia",
                tags=["history"],
                url=d.get("content_urls",{}).get("desktop",{}).get("page","")))
        time.sleep(CRAWL_DELAY)
    return out

def _semantic_scholar(query, limit=40):
    cutoff = _cutoff_year()
    d = _get(f"https://api.semanticscholar.org/graph/v1/paper/search"
             f"?query={urllib.parse.quote(query)}"
             f"&fields=title,abstract,authors,year,publicationDate,fieldsOfStudy"
             f"&limit={limit}&publicationDateOrYear={cutoff}-")
    if not d: return []
    out = []
    for p in d.get("data",[])[:limit]:
        out.append(_entry(p.get("title",""),
            p.get("abstract") or f"Authors: {', '.join(a.get('name','') for a in p.get('authors',[])[:3])}",
            "semantic_scholar", date=p.get("publicationDate") or str(p.get("year","")),
            tags=p.get("fieldsOfStudy",[]),
            url=f"https://www.semanticscholar.org/paper/{p.get('paperId','')}"))
    return out

def _openalex(concept, limit=40):
    cutoff = _cutoff_year()
    d = _get(f"https://api.openalex.org/works"
             f"?filter=concepts.display_name:{urllib.parse.quote(concept)},"
             f"publication_year:{cutoff}-&per-page={limit}&sort=cited_by_count:desc"
             f"&select=title,abstract_inverted_index,publication_date,doi,concepts",
             headers={"mailto": "digitalworld@local.sim"})
    if not d: return []
    out = []
    for w in d.get("results",[])[:limit]:
        inv = w.get("abstract_inverted_index") or {}
        if inv:
            try:
                words = [""] * (max(max(v) for v in inv.values()) + 1)
                for word, positions in inv.items():
                    for pos in positions:
                        if pos < len(words): words[pos] = word
                abstract = " ".join(words)[:400]
            except Exception:
                abstract = ""
        else:
            abstract = ""
        tags = [c.get("display_name","") for c in w.get("concepts",[])[:4]]
        out.append(_entry(w.get("title",""), abstract or f"Concepts: {', '.join(tags)}",
            "openalex", date=w.get("publication_date",""), tags=tags,
            url=f"https://doi.org/{w['doi']}" if w.get("doi") else ""))
    return out

def _arxiv(category, limit=40):
    text = _get_text(f"https://export.arxiv.org/api/query"
                     f"?search_query=cat:{category}"
                     f"&start=0&max_results={limit}&sortBy=submittedDate&sortOrder=descending")
    if not text: return []
    titles  = re.findall(r"<title>(?!arXiv)(.*?)</title>", text, re.DOTALL)
    summaries=re.findall(r"<summary>(.*?)</summary>",       text, re.DOTALL)
    dates   = re.findall(r"<published>(.*?)</published>",   text, re.DOTALL)
    links   = re.findall(r"<id>(http.*?)</id>",             text, re.DOTALL)
    out = []
    for i, title in enumerate(titles[:limit]):
        out.append(_entry(title.strip(),
            summaries[i].strip()[:400] if i < len(summaries) else "",
            "arxiv", date=dates[i][:10] if i < len(dates) else "",
            tags=[category], url=links[i].strip() if i < len(links) else ""))
    return out

def _pubmed(term, limit=40):
    cutoff = (datetime.utcnow() - timedelta(days=DATE_RANGE_YEARS*365)).strftime("%Y/%m/%d")
    s = _get(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
             f"?db=pubmed&term={urllib.parse.quote(term)}&retmax={limit}"
             f"&retmode=json&mindate={cutoff}&datetype=pdat")
    if not s: return []
    ids = s.get("esearchresult",{}).get("idlist",[])
    if not ids: return []
    r = _get(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
             f"?db=pubmed&id={','.join(ids[:limit])}&retmode=json")
    if not r: return []
    out = []
    for uid, doc in r.get("result",{}).items():
        if uid == "uids": continue
        out.append(_entry(doc.get("title",""),
            f"Authors: {', '.join(a.get('name','') for a in doc.get('authors',[])[:3])}. "
            f"Journal: {doc.get('fulljournalname','?')}. Date: {doc.get('pubdate','?')}.",
            "pubmed", date=doc.get("pubdate",""),
            tags=[term.split("[")[0].strip()],
            url=f"https://pubmed.ncbi.nlm.nih.gov/{uid}/"))
    return out

def fetch_semantic_scholar_cs(limit=40):  return _semantic_scholar("computer science software systems", limit)
def fetch_semantic_scholar_ml(limit=40):  return _semantic_scholar("machine learning deep learning neural network", limit)
def fetch_semantic_scholar_bio(limit=40): return _semantic_scholar("biology genetics molecular", limit)
def fetch_semantic_scholar_psych(limit=40):return _semantic_scholar("psychology cognitive neuroscience", limit)
def fetch_semantic_scholar_eng(limit=40): return _semantic_scholar("engineering systems design", limit)
def fetch_openalex_cs(limit=40):          return _openalex("Computer science", limit)
def fetch_openalex_ai(limit=40):          return _openalex("Artificial intelligence", limit)
def fetch_openalex_physics(limit=40):     return _openalex("Physics", limit)
def fetch_openalex_chemistry(limit=40):   return _openalex("Chemistry", limit)
def fetch_openalex_biology(limit=40):     return _openalex("Biology", limit)
def fetch_openalex_medicine(limit=40):    return _openalex("Medicine", limit)
def fetch_openalex_engineering(limit=40): return _openalex("Engineering", limit)
def fetch_openalex_earth(limit=40):       return _openalex("Earth science", limit)
def fetch_openalex_psych(limit=40):       return _openalex("Psychology", limit)
def fetch_arxiv_ai(limit=40):             return _arxiv("cs.AI", limit)
def fetch_arxiv_physics(limit=40):        return _arxiv("physics", limit)
def fetch_arxiv_engineering(limit=40):    return _arxiv("eess", limit)
def fetch_pubmed_biology(limit=40):       return _pubmed("biology[MeSH]", limit)
def fetch_pubmed_medicine(limit=40):      return _pubmed("medicine[MeSH]", limit)
def fetch_pubmed_neuro(limit=40):         return _pubmed("neurology[MeSH]", limit)
def fetch_github_trending(limit=40):
    cutoff = (datetime.utcnow()-timedelta(days=90)).strftime("%Y-%m-%d")
    d = _get(f"https://api.github.com/search/repositories"
             f"?q=created:>{cutoff}&sort=stars&order=desc&per_page={limit}",
             headers={"Authorization": f"token {os.environ.get('GITHUB_TOKEN','')}"})
    if not d: return []
    return [_entry(r.get("full_name",""), r.get("description","") or "No description.",
            "github", date=r.get("created_at","")[:10],
            tags=[r.get("language","").lower(),"github"],
            url=r.get("html_url","")) for r in d.get("items",[])[:limit]]

def fetch_nvd_cve(limit=40):
    cutoff = (datetime.utcnow()-timedelta(days=DATE_RANGE_YEARS*365)).strftime("%Y-%m-%dT00:00:00.000")
    d = _get(f"https://services.nvd.nist.gov/rest/json/cves/2.0"
             f"?pubStartDate={cutoff}&resultsPerPage={limit}")
    if not d: return []
    out = []
    for item in d.get("vulnerabilities",[])[:limit]:
        cve = item.get("cve",{})
        desc = next((x["value"] for x in cve.get("descriptions",[]) if x.get("lang")=="en"), "")
        out.append(_entry(cve.get("id","CVE"), desc[:400], "nvd",
            date=cve.get("published","")[:10], tags=["cve","vulnerability"],
            url=f"https://nvd.nist.gov/vuln/detail/{cve.get('id','')}"))
    return out

def fetch_cisa_advisories(limit=40):
    d = _get("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json")
    if not d: return []
    cutoff = _cutoff_date()
    out = []
    for v in d.get("vulnerabilities",[]):
        if v.get("dateAdded","9999") < cutoff: continue
        out.append(_entry(f"{v.get('cveID','')} — {v.get('vulnerabilityName','')}",
            f"Vendor: {v.get('vendorProject','')}. Product: {v.get('product','')}. "
            f"Action: {v.get('requiredAction','')}.", "cisa",
            date=v.get("dateAdded",""), tags=["cve","exploited","cisa"]))
        if len(out) >= limit: break
    return out

def fetch_circl_cve(limit=40):
    d = _get("https://cve.circl.lu/api/last/40")
    if not isinstance(d, list): return []
    return [_entry(c.get("id",""), c.get("summary","")[:400], "circl",
            date=c.get("Published","")[:10], tags=["cve"],
            url=f"https://cve.circl.lu/cve/{c.get('id','')}") for c in d[:limit]]

def fetch_alienvault_otx(limit=40):
    key = os.environ.get("ALIENVAULT_API_KEY","")
    since = (datetime.utcnow()-timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")
    d = _get(f"https://otx.alienvault.com/api/v1/pulses/subscribed?limit={limit}&modified_since={since}",
             headers={"X-OTX-API-KEY": key} if key else {})
    if not d: return []
    return [_entry(p.get("name",""), p.get("description","")[:400], "alienvault_otx",
            date=p.get("created","")[:10], tags=p.get("tags",[])[:4]+["threat_intel"],
            url=f"https://otx.alienvault.com/pulse/{p.get('id','')}") for p in d.get("results",[])[:limit]]

def fetch_exploitdb(limit=40):
    text = _get_text("https://www.exploit-db.com/rss.xml")
    if not text: return []
    items = re.findall(r"<item>(.*?)</item>", text, re.DOTALL)
    out = []
    for item in items[:limit]:
        t = re.search(r"<title>(.*?)</title>",           item, re.DOTALL)
        l = re.search(r"<link>(.*?)</link>",             item, re.DOTALL)
        s = re.search(r"<description>(.*?)</description>",item, re.DOTALL)
        d = re.search(r"<pubDate>(.*?)</pubDate>",       item, re.DOTALL)
        out.append(_entry(t.group(1).strip() if t else "",
            s.group(1).strip()[:300] if s else "", "exploitdb",
            date=d.group(1).strip()[:10] if d else "",
            tags=["exploit","offensive_security"],
            url=l.group(1).strip() if l else ""))
    return out

def fetch_urlhaus(limit=40):
    d = _get("https://urlhaus-api.abuse.ch/v1/urls/recent/")
    if not d: return []
    return [_entry(f"Malicious URL: {u.get('url_host','')}",
            f"Status: {u.get('url_status','')}. Threat: {u.get('threat','')}.",
            "urlhaus", date=u.get("date_added","")[:10],
            tags=["malware_url","threat"]+(u.get("tags") or [])) for u in d.get("urls",[])[:limit]]

def fetch_malware_bazaar(limit=40):
    d = _get("https://mb-api.abuse.ch/api/v1/?query=get_recent&selector=time")
    if not d: return []
    return [_entry(f"{s.get('file_name','')} [{s.get('file_type','')}]",
            f"SHA256: {s.get('sha256_hash','')[:16]}... Tags: {', '.join(s.get('tags') or [])}. "
            f"Signature: {s.get('signature','')}.", "malware_bazaar",
            date=s.get("first_seen","")[:10],
            tags=["malware"]+(s.get("tags") or [])) for s in (d.get("data") or [])[:limit]]

def fetch_abuseipdb_reports(limit=40):
    key = os.environ.get("ABUSEIPDB_API_KEY","")
    if not key: return []
    d = _get(f"https://api.abuseipdb.com/api/v2/blacklist?confidenceMinimum=90&limit={limit}",
             headers={"Key": key, "Accept": "application/json"})
    if not d: return []
    return [_entry(f"Blacklisted IP: {ip.get('ipAddress','')}",
            f"Score: {ip.get('abuseConfidenceScore','')}%. Country: {ip.get('countryCode','')}. "
            f"Reports: {ip.get('totalReports','')}.", "abuseipdb",
            tags=["blacklist","malicious_ip"]) for ip in d.get("data",[])[:limit]]

def fetch_honeydb(limit=40):
    aid = os.environ.get("HONEYDB_API_ID","")
    key = os.environ.get("HONEYDB_API_KEY","")
    if not aid or not key: return []
    d = _get("https://honeydb.io/api/threat-data/all",
             headers={"X-HoneyDb-ApiId": aid, "X-HoneyDb-ApiKey": key})
    if not isinstance(d, list): return []
    return [_entry(f"Honeypot: {e.get('remote_host','')} -> {e.get('service','')}",
            f"Service: {e.get('service','')}. Data: {str(e.get('data',''))[:150]}.",
            "honeydb", tags=["honeypot","threat_telemetry",e.get("service","unknown")])
            for e in d[:limit]]

def fetch_nasa_earth(limit=20):
    key = os.environ.get("NASA_API_KEY","DEMO_KEY")
    d = _get(f"https://api.nasa.gov/planetary/apod?api_key={key}&count={min(limit,20)}")
    if not d: return []
    items = d if isinstance(d, list) else [d]
    return [_entry(i.get("title",""), i.get("explanation","")[:400], "nasa",
            date=i.get("date",""), tags=["astronomy","space","nasa"],
            url=i.get("url","")) for i in items[:limit]]

def fetch_noaa_data(limit=40):
    text = _get_text("https://www.weather.gov/rss_page.php?site_name=nws")
    if not text: return []
    items = re.findall(r"<item>(.*?)</item>", text, re.DOTALL)
    out = []
    for item in items[:limit]:
        t = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
        s = re.search(r"<description>(.*?)</description>", item, re.DOTALL)
        out.append(_entry(t.group(1).strip() if t else "NOAA",
            s.group(1).strip()[:300] if s else "", "noaa",
            tags=["weather","earth_science"]))
    return out

def fetch_freesound_cc0(limit=30):
    """Freesound — CC0 sounds only. Free API key required."""
    key = os.environ.get("FREESOUND_API_KEY", "")
    if not key:
        return []
    d = _get(f"https://freesound.org/apiv2/search/text/"
             f"?query=ambient&filter=license:%22Creative+Commons+0%22"
             f"&fields=name,description,tags,license,url&page_size={limit}"
             f"&token={key}")
    if not d: return []
    return [_entry(
        s.get("name",""),
        f"Sound: {s.get('description','')[:200]}. Tags: {', '.join((s.get('tags') or [])[:5])}.",
        "freesound_cc0",
        tags=["sound","cc0","audio"]+(s.get("tags") or [])[:3],
        url=s.get("url","")
    ) for s in d.get("results",[])[:limit]]

def fetch_free_music_archive(limit=30):
    """Free Music Archive — CC0 tracks only."""
    d = _get(f"https://freemusicarchive.org/api/get/tracks.json"
             f"?license=Creative+Commons+0&limit={limit}")
    if not d: return []
    return [_entry(
        t.get("track_title",""),
        f"Artist: {t.get('artist_name','?')}, Album: {t.get('album_title','?')}. "
        f"Genre: {t.get('track_genres',{}).get('genre_title','?')}.",
        "free_music_archive",
        tags=["music","cc0",t.get("track_genres",{}).get("genre_title","").lower()],
        url=t.get("track_url","")
    ) for t in d.get("dataset",[])[:limit]]

def fetch_internet_archive_texts(limit=30):
    """Internet Archive — public domain texts."""
    cutoff = _cutoff_year()
    d = _get(f"https://archive.org/advancedsearch.php"
             f"?q=mediatype:texts+AND+licenseurl:(creativecommons)&fl=title,creator,description,identifier"
             f"&sort=downloads+desc&rows={limit}&output=json")
    if not d: return []
    return [_entry(
        doc.get("title",""),
        f"Creator: {doc.get('creator','?')[:50]}. {doc.get('description','')[:200]}",
        "internet_archive",
        tags=["literature","public_domain"],
        url=f"https://archive.org/details/{doc.get('identifier','')}"
    ) for doc in d.get("response",{}).get("docs",[])[:limit]]

def fetch_openverse_cc0(limit=30):
    """Openverse — CC0 images and audio across Commons, Jamendo, Freesound."""
    d = _get(f"https://api.openverse.org/v1/images/"
             f"?license=cc0&page_size={limit}&mature=false")
    if not d: return []
    return [_entry(
        img.get("title","Untitled"),
        f"Creator: {img.get('creator','?')}, Source: {img.get('source','?')}. "
        f"Tags: {img.get('tags','')[:100] if isinstance(img.get('tags'),str) else ''}",
        "openverse",
        tags=["visual_art","cc0","image"],
        url=img.get("url","")
    ) for img in d.get("results",[])[:limit]]

SOURCE_FETCHERS = {
    "gutenberg_literature": fetch_gutenberg_literature,
    "gutenberg_history":    fetch_gutenberg_history,
    "gutenberg_science":    fetch_gutenberg_science,
    "gutenberg_philosophy": fetch_gutenberg_philosophy,
    "open_library_fiction": fetch_open_library_fiction,
    "open_library_history": fetch_open_library_history,
    "open_library_general": fetch_open_library_general,
    "met_museum":           fetch_met_museum,
    "smithsonian_art":      fetch_smithsonian_art,
    "nga_art":              fetch_nga_art,
    "cleveland_art":        fetch_cleveland_art,
    "aic_art":              fetch_aic_art,
    "wikipedia_general":    fetch_wikipedia_general,
    "wikipedia_history":    fetch_wikipedia_history,
    "github_trending":      fetch_github_trending,
    "openalex_cs":          fetch_openalex_cs,
    "openalex_ai":          fetch_openalex_ai,
    "openalex_physics":     fetch_openalex_physics,
    "openalex_chemistry":   fetch_openalex_chemistry,
    "openalex_biology":     fetch_openalex_biology,
    "openalex_medicine":    fetch_openalex_medicine,
    "openalex_engineering": fetch_openalex_engineering,
    "openalex_earth":       fetch_openalex_earth,
    "openalex_psych":       fetch_openalex_psych,
    "semantic_scholar_cs":  fetch_semantic_scholar_cs,
    "semantic_scholar_ml":  fetch_semantic_scholar_ml,
    "semantic_scholar_bio": fetch_semantic_scholar_bio,
    "semantic_scholar_psych":fetch_semantic_scholar_psych,
    "semantic_scholar_eng": fetch_semantic_scholar_eng,
    "arxiv_ai":             fetch_arxiv_ai,
    "arxiv_physics":        fetch_arxiv_physics,
    "arxiv_engineering":    fetch_arxiv_engineering,
    "pubmed_biology":       fetch_pubmed_biology,
    "pubmed_medicine":      fetch_pubmed_medicine,
    "pubmed_neuro":         fetch_pubmed_neuro,
    "nvd_cve":              fetch_nvd_cve,
    "cisa_advisories":      fetch_cisa_advisories,
    "circl_cve":            fetch_circl_cve,
    "alienvault_otx":       fetch_alienvault_otx,
    "exploitdb":            fetch_exploitdb,
    "urlhaus":              fetch_urlhaus,
    "malware_bazaar":       fetch_malware_bazaar,
    "abuseipdb_reports":    fetch_abuseipdb_reports,
    "honeydb":              fetch_honeydb,
    "nasa_earth":           fetch_nasa_earth,
    "noaa_data":            fetch_noaa_data,
    # Creative CC0 sources
    "freesound_cc0":        fetch_freesound_cc0,
    "free_music_archive":   fetch_free_music_archive,
    "internet_archive_texts":fetch_internet_archive_texts,
    "openverse_cc0":        fetch_openverse_cc0,
}

# ── KnowledgeBase class ───────────────────────────────────────────────────────
class KnowledgeBase:
    """Manages the local knowledge base. Build once, query forever."""

    def __init__(self, kb_dir=KB_DIR):
        self.kb_dir      = kb_dir
        self.science_dir = os.path.join(kb_dir, "science")
        os.makedirs(self.kb_dir,      exist_ok=True)
        os.makedirs(self.science_dir, exist_ok=True)
        self._cache: dict = {}

    def _domain_path(self, domain):
        if domain.startswith("science/"):
            return os.path.join(self.science_dir, f"{domain.replace('science/','')}.json")
        return os.path.join(self.kb_dir, f"{domain}.json")

    def _is_fresh(self, domain):
        p = self._domain_path(domain)
        if not os.path.exists(p): return False
        return (time.time() - os.path.getmtime(p)) / 86400 < FRESHNESS_DAYS

    def build(self, force=False, domains=None, verbose=True):
        targets = domains or list(DOMAINS.keys())
        stale   = [d for d in targets if force or not self._is_fresh(d)]
        if not stale:
            if verbose: print("[KB] All domains fresh — loading from disk.")
            self._load_all(); return
        if verbose: print(f"[KB] Crawling {len(stale)} domain(s)...")
        for domain in stale:
            self._build_domain(domain, verbose)
        self._load_all()
        if verbose:
            total = sum(len(v) for v in self._cache.values())
            print(f"[KB] Ready — {total} entries across {len(self._cache)} domains.")

    def _build_domain(self, domain, verbose=True):
        cfg     = DOMAINS.get(domain, {})
        sources = cfg.get("sources", [])
        entries = []
        if verbose: print(f"[KB]   {domain} ({len(sources)} sources)...")
        per_src = max(5, MAX_ENTRIES // max(len(sources), 1))
        for src_id in sources:
            fn = SOURCE_FETCHERS.get(src_id)
            if not fn: continue
            try:
                if verbose: print(f"[KB]     fetching {src_id}...", end=" ", flush=True)
                import time as _t; t0 = _t.time()
                res = fn(limit=per_src)
                elapsed = _t.time() - t0
                entries.extend(res or [])
                if verbose: print(f"{len(res or [])} entries ({elapsed:.1f}s)")

                time.sleep(CRAWL_DELAY)
            except Exception as e:
                if verbose: print(f"[KB]     {src_id}: FAILED ({e})")
        # Deduplicate and cap
        seen, dedup = set(), []
        for e in entries:
            if e["id"] not in seen:
                seen.add(e["id"]); dedup.append(e)
        random.shuffle(dedup)
        dedup = dedup[:MAX_ENTRIES]
        path  = self._domain_path(domain)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"domain": domain, "description": cfg.get("description",""),
                       "biomes": cfg.get("biomes",[]), "attributes": cfg.get("attributes",[]),
                       "last_crawled": datetime.utcnow().isoformat(),
                       "date_range": {"from": _cutoff_date(),
                                      "to": datetime.utcnow().strftime("%Y-%m-%d")},
                       "source_versions": {s: datetime.utcnow().strftime("%Y-%m-%d") for s in sources},
                       "entry_count": len(dedup), "entries": dedup}, f,
                      ensure_ascii=False, indent=2)
        if verbose: print(f"[KB]   -> {path} ({len(dedup)} entries)")

    def _load_all(self):
        for domain in DOMAINS:
            p = self._domain_path(domain)
            if os.path.exists(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        self._cache[domain] = json.load(f).get("entries", [])
                except Exception:
                    self._cache[domain] = []
            else:
                self._cache[domain] = []

    def record_knowledge_from_digimon(self, digimon_id: str, digimon_name: str,
                                       topic: str, insight: str, source: str,
                                       domain: str = "data_generated"):
        """
        Add a Digimon-generated insight to the knowledge base.
        Written to the art domain cache (Data types generate cultural knowledge).
        Also persisted to a digimon_research.json file.
        """
        import hashlib, time as _t
        entry = {
            "id":      hashlib.md5(f"dgm:{digimon_id}:{topic}".encode()).hexdigest()[:12],
            "title":   f"[{digimon_name}] {topic[:100]}",
            "summary": insight[:400],
            "source":  source,
            "date":    datetime.utcnow().strftime("%Y-%m-%d"),
            "tags":    ["digimon_research", "data_generated", domain],
            "url":     "",
        }
        # Add to in-memory cache under art domain (cross-domain knowledge)
        self._cache.setdefault("art", []).append(entry)
        self._cache.setdefault("general_knowledge", []).append(entry)

        # Persist to a separate research file (grows over time, never overwritten)
        research_path = os.path.join(self.kb_dir, "digimon_research.jsonl")
        with open(research_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def query(self, domain, limit=10, tags=None, attribute=None):
        entries = self._cache.get(domain, [])
        if not entries:
            p = self._domain_path(domain)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    entries = json.load(f).get("entries", [])
                self._cache[domain] = entries
        if not entries: return []
        if tags:
            filtered = [e for e in entries if any(t in e.get("tags",[]) for t in tags)]
            entries  = filtered or entries
        return random.sample(entries, min(limit, len(entries)))

    def query_for_biome(self, biome, limit=15, attribute=None):
        domains = BIOME_DOMAINS.get(biome, ["general_knowledge"])
        entries = []
        per     = max(1, limit // len(domains))
        for d in domains:
            entries.extend(self.query(d, limit=per, attribute=attribute))
        random.shuffle(entries)
        return entries[:limit]

    def query_for_attribute(self, attribute, limit=10):
        domains = ATTRIBUTE_DOMAINS.get(attribute, ["general_knowledge"])
        entries = []
        per     = max(1, limit // len(domains))
        for d in domains:
            entries.extend(self.query(d, limit=per))
        random.shuffle(entries)
        return entries[:limit]

    def extract_capability(self, entry, attribute):
        title    = entry.get("title","").lower()
        tags     = entry.get("tags", [])
        keywords = [w for w in (tags + title.split()) if len(w) > 3 and w.isalpha()]
        if not keywords: return None
        keyword  = random.choice(keywords[:5])[:20]
        verbs    = {"Vaccine":["counter","detect","shield","neutralise","patch"],
                    "Virus":  ["exploit","corrupt","penetrate","infect","subvert"],
                    "Data":   ["analyse","synthesise","map","model","archive"]}.get(attribute,["process"])
        return f"{random.choice(verbs)}_{keyword}"

    def get_status(self):
        return {d: {"entries": len(self._cache.get(d,[])),
                    "fresh": self._is_fresh(d),
                    "path": self._domain_path(d)} for d in DOMAINS}


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Digital World Knowledge Base")
    p.add_argument("command", nargs="?", default="status",
                   choices=["build","rebuild","status","list"])
    p.add_argument("--domain", "-d", nargs="+")
    p.add_argument("--dir", default=KB_DIR)
    args = p.parse_args()
    kb   = KnowledgeBase(args.dir)

    if args.command == "status":
        s = kb.get_status()
        print(f"\n{'='*60}\n  KNOWLEDGE BASE STATUS\n{'='*60}")
        for domain, info in sorted(s.items()):
            tag = "OK" if info["fresh"] else "STALE"
            print(f"  {domain:<36} {info['entries']:>5} entries  [{tag}]")
        print(f"{'─'*60}\n  TOTAL: {sum(i['entries'] for i in s.values())} entries\n{'='*60}\n")

    elif args.command in ("build","rebuild"):
        kb.build(force=args.command == "rebuild", domains=args.domain, verbose=True)

    elif args.command == "list":
        for domain, cfg in DOMAINS.items():
            print(f"{domain:<36} biomes: {cfg['biomes']}")
