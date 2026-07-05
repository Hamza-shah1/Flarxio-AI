from database.db import get_db
import logging

log = logging.getLogger("app")

# ---------------- TOKEN CLEANUP ----------------

def cleanup_expired_tokens():
    """Delete expired password-reset tokens. Call once on startup."""
    db = None
    cur = None
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("DELETE FROM password_resets WHERE expires_at < UTC_TIMESTAMP()")
        deleted = cur.rowcount
        db.commit()
        if deleted:
            log.info(f"Cleaned up {deleted} expired password-reset token(s)")
    except Exception:
        log.exception("cleanup_expired_tokens")
    finally:
        try:
            if cur:
                cur.close()
            if db:
                db.close()
        except Exception:
            pass
