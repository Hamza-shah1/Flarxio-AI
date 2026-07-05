from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from config import BASE_URL , GOOGLE_SAFE_BROWSING_API_KEY , WHOISXML_API_KEY  
from database.db import get_db_of_short_link as get_db
from threading import Lock
from dotenv import load_dotenv
import time
import string
import random
from flask import Flask, request, jsonify, redirect, Response, stream_with_context
from utils.urls_types import SUSPICIOUS_TLDS , SUSPICIOUS_KEYWORDS , PROTECTED_BRANDS , HOMOGLYPH_MAP
from urllib.parse import urlparse
import ipaddress
from datetime import datetime, timedelta
from collections import defaultdict
import math
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.handler import generate_code 
import json


load_dotenv()


app = None;


def url_shortner_model_initilizer(main_app):
    main_app.wsgi_app = ProxyFix(main_app.wsgi_app, x_proto=1, x_host=1)
    app = main_app
    CORS(app, resources={r"/*": {"origins": "*"}})
    
def cache_get(url: str):
    with _cache_lock:
        entry = _url_cache.get(url)
        if entry and time.monotonic() - entry[2] < CACHE_TTL:
            return entry[0], entry[1]
    return None


def cache_set(url: str, ok: bool, reason: str):
    with _cache_lock:
        _url_cache[url] = (ok, reason, time.monotonic())
        


_url_cache: dict[str, tuple[bool, str, float]] = {}
_cache_lock = Lock()
CACHE_TTL = 600  # seconds

def normalize(text: str) -> str:
    return text.lower().translate(HOMOGLYPH_MAP)


def _levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if not s2:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


# ---- LAYER 1: URL Structure Validation (fast, sync) ----

def layer1_valid_structure(url: str):
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, "Only http and https URLs are allowed"
        if not parsed.netloc:
            return False, "URL must have a valid domain"
        hostname = parsed.hostname or ""
        if hostname in ("localhost", "127.0.0.1", "::1"):
            return False, "Local URLs are not allowed"
        try:
            ipaddress.ip_address(hostname)
            return False, "Raw IP addresses are not allowed"
        except ValueError:
            pass
        if "." not in hostname:
            return False, "URL must have a valid domain with a TLD"
        return True, ""
    except Exception:
        return False, "Malformed URL"
    

# ---- LAYER 2: Suspicious Keyword Detection (fast, sync) ----
  
    
def layer2_suspicious_keywords(url: str):
    url_lower = url.lower()
    domain = urlparse(url_lower).netloc
    for kw in SUSPICIOUS_KEYWORDS:
        if kw in url_lower:
            return False, f"URL contains suspicious keyword: '{kw}'"
    for tld in SUSPICIOUS_TLDS:
        if domain.endswith(tld):
            return False, f"Untrusted TLD detected: '{tld}'"
    return True, ""


# ---- LAYER 3: Homoglyph / Typosquat Detection (fast, sync) ----


def layer3_homoglyph_typosquat(url: str):
    parsed = urlparse(url)
    domain_parts = (parsed.hostname or "").split(".")
    root = ".".join(domain_parts[-2:]) if len(domain_parts) >= 2 else parsed.hostname or ""
    root_name_normalized = normalize(root.split(".")[0])
    for brand in PROTECTED_BRANDS:
        brand_norm = normalize(brand)
        if brand_norm in normalize(parsed.netloc) and root_name_normalized != brand_norm:
            return False, f"Possible brand impersonation of '{brand}' detected"
        if len(root_name_normalized) > 3 and root_name_normalized != brand_norm:
            if _levenshtein(root_name_normalized, brand_norm) == 1:
                return False, f"Domain looks like a typosquat of '{brand}'"
    return True, ""


# ---- LAYER 4: Domain Age via WHOIS API (slow, network) ----

def layer4_domain_age(url: str):
    if not WHOISXML_API_KEY:
        return True, ""
    try:
        domain = urlparse(url).hostname
        resp = requests.get(
            "https://www.whoisxmlapi.com/whoisserver/WhoisService",
            params={"apiKey": WHOISXML_API_KEY, "domainName": domain, "outputFormat": "JSON"},
            timeout=5,
        )
        data = resp.json()
        created_str = (
            data.get("WhoisRecord", {})
                .get("registryData", {})
                .get("createdDate", "")
        )
        if created_str:
            created = datetime.strptime(created_str[:10], "%Y-%m-%d")
            age_days = (datetime.utcnow() - created).days
            if age_days < 30:
                return False, f"Domain is only {age_days} days old — too new to trust"
    except Exception:
        pass
    return True, ""

# ---- LAYER 5: Google Safe Browsing (slow, network) ----



def layer5_google_safe_browsing(url: str):
    if not GOOGLE_SAFE_BROWSING_API_KEY:
        return True, ""
    try:
        payload = {
            "client": {"clientId": "urlshortener", "clientVersion": "1.0"},
            "threatInfo": {
                "threatTypes": [
                    "MALWARE", "SOCIAL_ENGINEERING",
                    "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"
                ],
                "platformTypes": ["ANY_PLATFORM"],
                "threatEntryTypes": ["URL"],
                "threatEntries": [{"url": url}],
            },
        }
        resp = requests.post(
            f"https://safebrowsing.googleapis.com/v4/threatMatches:find"
            f"?key={GOOGLE_SAFE_BROWSING_API_KEY}",
            json=payload,
            timeout=5,
        )
        data = resp.json()
        if data.get("matches"):
            threat = data["matches"][0].get("threatType", "unknown threat")
            return False, f"URL flagged by Google Safe Browsing: {threat}"
    except Exception:
        pass
    return True, ""


# ---- LAYER 6: Redirect Chain Inspection (slow, network) ----

def layer6_redirect_chain(url: str):
    try:
        resp = requests.head(url, allow_redirects=True, timeout=6)
        final_url = resp.url
        if final_url != url:
            ok, reason = layer1_valid_structure(final_url)
            if not ok:
                return False, f"Redirect leads to unsafe destination: {reason}"
            ok, reason = layer2_suspicious_keywords(final_url)
            if not ok:
                return False, f"Redirect leads to suspicious destination: {reason}"
        if len(resp.history) > 4:
            return False, f"Too many redirects ({len(resp.history)}) — suspicious"
    except requests.exceptions.SSLError:
        return False, "SSL certificate error — site is not trusted"
    except Exception:
        pass
    return True, ""

# ---- LAYER 7: Domain Entropy (fast, sync) ----

def layer7_domain_entropy(url: str):
    domain = urlparse(url).hostname or ""
    name = domain.split(".")[0]
    if len(name) < 8:
        return True, ""
    freq = defaultdict(int)
    for c in name:
        freq[c] += 1
    entropy = -sum((f / len(name)) * math.log2(f / len(name)) for f in freq.values())
    if entropy > 4.0 and len(name) >= 10:
        return False, f"Domain name appears randomly generated (entropy={entropy:.2f})"
    return True, ""


# ============================================================
#         OPTIMIZED: fast sync + slow parallel
# ============================================================

# Layers that run instantly (no network I/O) — checked first
FAST_LAYERS = [
    ("Structure", layer1_valid_structure),
    ("Keywords",  layer2_suspicious_keywords),
    ("Homoglyph", layer3_homoglyph_typosquat),
    ("Entropy",   layer7_domain_entropy),
]

# Layers that hit external APIs — run concurrently
SLOW_LAYERS = [
    ("Domain Age",    layer4_domain_age),
    ("Safe Browsing", layer5_google_safe_browsing),
    ("Redirect Chain",layer6_redirect_chain),
]

_executor = ThreadPoolExecutor(max_workers=6)



def run_all_protection_layers(url: str):
    # 1. Check result cache first
    cached = cache_get(url)
    if cached is not None:
        return cached

    # 2. Fast layers — bail immediately on first failure
    for layer_name, fn in FAST_LAYERS:
        ok, reason = fn(url)
        if not ok:
            result = False, f"[{layer_name}] {reason}"
            cache_set(url, *result)
            app.logger.warning(f"[BLOCKED] Layer={layer_name} URL={url} Reason={reason}")
            return result

    # 3. Slow layers — run in parallel, stop on first failure
    futures = {
        _executor.submit(fn, url): layer_name
        for layer_name, fn in SLOW_LAYERS
    }
    result = (True, "")
    for future in as_completed(futures):
        layer_name = futures[future]
        try:
            ok, reason = future.result()
            if not ok:
                result = False, f"[{layer_name}] {reason}"
                app.logger.warning(f"[BLOCKED] Layer={layer_name} URL={url} Reason={reason}")
                # Cancel remaining futures (best-effort)
                for f in futures:
                    f.cancel()
                break
        except Exception as e:
            app.logger.error(f"Layer {layer_name} raised: {e}")

    cache_set(url, *result)
    return result




def _save_url(long_url: str, ip: str) -> str:
    """Insert (or retrieve existing) short code; returns full short URL."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("SELECT short_code FROM short_links WHERE original_url=%s", (long_url,))
        existing = cur.fetchone()
        if existing:
            return f"{BASE_URL or 'http://localhost:5000'}/{existing['short_code']}"

        code = generate_code()
        cur.execute("SELECT id FROM short_links WHERE short_code=%s", (code,))
        while cur.fetchone():
            code = generate_code()
            cur.execute("SELECT id FROM short_links WHERE short_code=%s", (code,))

        cur.execute(
            "INSERT INTO short_links (original_url, short_code, created_by_ip) VALUES (%s, %s, %s)",
            (long_url, code, ip),
        )
        db.commit()
        return f"{BASE_URL or 'http://localhost:5000'}/{code}"
    except Exception:
        db.rollback()
        raise
    finally:
        cur.close()
        db.close()
        
def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"