from models.url_shortner_model import cache_get , cache_set
from models.url_shortner_model import _save_url , FAST_LAYERS , app , _executor , _sse , SLOW_LAYERS
from database.db import get_db_of_short_link as get_db
from flask import Flask, request, jsonify, redirect, Response, stream_with_context
from utils.handler import generate_code
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.url_Shortner_handles import _fetch_report_record , _close_db_resources , _report_success_response

def _generate_progress(url: str, ip: str):
    cached = cache_get(url)
    if cached is not None:
        ok, reason = cached
        yield _sse({
            "stage": "Cache",
            "status": "pass" if ok else "fail",
            "pct": 100,
            "reason": reason,
            "cached": True
        })

        if ok:
            short_url = _save_url(url, ip)
            yield _sse({
                "stage": "Save",
                "status": "pass",
                "pct": 100,
                "short_url": short_url
            })
        return

    step_pct = 60 // (len(FAST_LAYERS) + 1)

    # --- Fast layers ---
    for idx, (name, fn) in enumerate(FAST_LAYERS):
        pct = 5 + idx * step_pct

        yield _sse({"stage": name, "status": "running", "pct": pct})

        ok, reason = fn(url)
        if not ok:
            cache_set(url, False, reason)
            app.logger.warning(f"[BLOCKED] Layer={name} URL={url} Reason={reason}")

            yield _sse({
                "stage": name,
                "status": "fail",
                "pct": pct,
                "reason": f"[{name}] {reason}"
            })
            return

        yield _sse({
            "stage": name,
            "status": "pass",
            "pct": pct + step_pct
        })

    # --- Slow layers ---
    yield _sse({"stage": "DeepCheck", "status": "running", "pct": 65})

    futures = {_executor.submit(fn, url): layer_name for layer_name, fn in SLOW_LAYERS}
    failed_reason = None

    for future in as_completed(futures):
        layer_name = futures[future]
        try:
            ok, reason = future.result()
            if not ok:
                failed_reason = f"[{layer_name}] {reason}"
                for f in futures:
                    f.cancel()
                break

            yield _sse({"stage": layer_name, "status": "pass", "pct": 75})

        except Exception as e:
            app.logger.error(f"Layer {layer_name} raised: {e}")

    if failed_reason:
        cache_set(url, False, failed_reason)
        app.logger.warning(f"[BLOCKED] URL={url} Reason={failed_reason}")

        yield _sse({
            "stage": "DeepCheck",
            "status": "fail",
            "pct": 75,
            "reason": failed_reason
        })
        return

    cache_set(url, True, "")
    yield _sse({"stage": "DeepCheck", "status": "pass", "pct": 85})

    # --- Save ---
    yield _sse({"stage": "Save", "status": "running", "pct": 90})

    try:
        short_url = _save_url(url, ip)
        yield _sse({
            "stage": "Save",
            "status": "pass",
            "pct": 100,
            "short_url": short_url
        })
    except Exception as e:
        app.logger.error(f"_save_url error: {e}")
        yield _sse({
            "stage": "Save",
            "status": "fail",
            "pct": 90,
            "reason": "Database error"
        })
        
        
        
def _handle_report_link(code):
    db = None
    cur = None

    try:
        db = get_db()
        cur = db.cursor()

        record = _fetch_report_record(cur, code)
        if not record:
            return jsonify({"error": "Link not found"}), 404

        new_reports, auto_flagged = _calculate_report_status(record)

        _update_report_status(cur, db, code, new_reports, auto_flagged)

        return _report_success_response(auto_flagged)

    except Exception as e:
        if db:
            db.rollback()
        app.logger.error(f"report_link error: {e}")
        return jsonify({"error": "Server error"}), 500

    finally:
        _close_db_resources(cur, db)
        
        
        
def _handle_shorten_db(long_url, ip):
    db = None
    cur = None

    try:
        db = get_db()
        cur = db.cursor()

        # Check existing
        cur.execute(
            "SELECT short_code FROM short_links WHERE original_url=%s",
            (long_url,)
        )
        existing = cur.fetchone()

        if existing:
            return jsonify({
                "message": "Short URL already exists",
                "short_url": f"{get_base_url()}/{existing['short_code']}"
            }), 200

        # Generate unique code
        code = generate_code()
        cur.execute("SELECT id FROM short_links WHERE short_code=%s", (code,))
        while cur.fetchone():
            code = generate_code()
            cur.execute("SELECT id FROM short_links WHERE short_code=%s", (code,))

        # Insert
        cur.execute(
            "INSERT INTO short_links (original_url, short_code, created_by_ip) VALUES (%s, %s, %s)",
            (long_url, code, ip),
        )
        db.commit()

        return jsonify({
            "message": "Short URL created successfully",
            "short_url": f"{get_base_url()}/{code}"
        }), 201

    except Exception as e:
        if db:
            db.rollback()
        app.logger.error(f"shorten_url error: {e}")
        return jsonify({"error": "Server error", "detail": str(e)}), 500

    finally:
        if cur:
            cur.close()
        if db:
            db.close()
            
            
def _calculate_report_status(record):
    new_reports = record["reports"] + 1
    auto_flagged = new_reports >= 3
    return new_reports, auto_flagged


def _update_report_status(cur, db, code, new_reports, auto_flaged):
    cur.execute(
        "UPDATE short_links SET reports=%s, flagged=%s WHERE short_code=%s",
        (new_reports, auto_flaged, code),
    )
    db.commit()