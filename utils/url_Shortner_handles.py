from models.url_shortner_model import _cache_lock , CACHE_TTL , _url_cache ,  run_all_protection_layers
import time
from utils.url_shortner_utils import RATE_LIMIT_MAX , RATE_LIMIT_WINDOW , _rate_lock , _rate_data
from datetime import datetime, timedelta
from utils.urls_types import HOMOGLYPH_MAP
from flask import Flask, request, jsonify, redirect, Response, stream_with_context




              
def is_rate_limited(ip: str) -> bool:
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=RATE_LIMIT_WINDOW)
    with _rate_lock:
        _rate_data[ip] = [t for t in _rate_data[ip] if t > window_start]
        if len(_rate_data[ip]) >= RATE_LIMIT_MAX:
            return True
        _rate_data[ip].append(now)
    return False




def _check_rate_limit(ip):
    if is_rate_limited(ip):
        return jsonify({"error": "Too many requests. Please slow down."}), 429
    return None


def _extract_url_from_request():
    data = request.get_json()
    long_url = (data.get("url") if data else None or "").strip()

    if not long_url:
        return None, (jsonify({"error": "URL is required"}), 400)

    return long_url, None

def _run_security_checks(long_url):
    safe, reason = run_all_protection_layers(long_url)
    if not safe:
        return jsonify({
            "error": "URL rejected by security check",
            "reason": reason
        }), 400

    return None


def _fetch_report_record(cur, code):
    cur.execute(
        "SELECT id, reports FROM short_links WHERE short_code=%s",
        (code,)
    )
    return cur.fetchone()

def _close_db_resources(cur, db):
    if cur:
        cur.close()
    if db:
        db.close()   
        
        
def _report_success_response(auto_flagged):
    return jsonify({
        "message": "Report received. Thank you for keeping the platform safe.",
        "auto_flagged": auto_flagged,
    }), 200