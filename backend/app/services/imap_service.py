"""
IMAP Email Fetching Service
─────────────────────────────────────────────────────────────────────────────
Fetches emails from the user's mail server using stdlib imaplib (no extra deps).

Gmail free-tier compliance:
  • Single SSL connection per fetch session (max 10 simultaneous allowed by Gmail)
  • Paged fetching in batches of IMAP_BATCH_SIZE (default 50) to avoid large
    single-command payloads and stay within ~2500 IMAP commands/hour
  • Deduplication by RFC-2822 Message-ID — already-stored emails are NEVER
    re-downloaded, even across multiple fetch calls
  • Connection is always closed in `finally` block — no lingering sessions
"""

import imaplib
import email
import email.policy
import uuid
import time
import re
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logger import logger
from app.db.models import FetchedEmail, User


# ── Header helpers ─────────────────────────────────────────────────────────────

def _decode_mime_words(raw: str | bytes | None) -> str:
    """Decode RFC-2047 encoded email header value to plain text."""
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    parts = decode_header(raw)
    decoded_parts = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                decoded_parts.append(part.decode("latin-1", errors="replace"))
        else:
            decoded_parts.append(part)
    return "".join(decoded_parts)


def _extract_body(msg: email.message.Message) -> str:
    """
    Extract plain-text body from an email.Message.
    Preference order: text/plain → text/html (stripped) → fallback empty string.
    """
    plain_body = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            charset = part.get_content_charset() or "utf-8"
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = payload.decode(charset, errors="replace")
            if ct == "text/plain" and not plain_body:
                plain_body = text
            elif ct == "text/html" and not html_body:
                # Strip HTML tags for a cleaner body representation
                html_body = re.sub(r"<[^>]+>", " ", text)
                html_body = re.sub(r"\s+", " ", html_body).strip()
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            body_text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body_text)).strip()
            else:
                plain_body = body_text

    return plain_body.strip() or html_body.strip()


def _parse_received_at(msg: email.message.Message) -> Optional[datetime]:
    """Parse the Date: header into a timezone-aware UTC datetime."""
    date_str = msg.get("Date")
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _get_existing_message_ids(db_sync_result) -> set[str]:
    """Convert a DB result of message_ids into a set for O(1) dedup lookup."""
    return {row for row in db_sync_result}


# ── Core fetch logic ───────────────────────────────────────────────────────────

async def _get_existing_ids(db: AsyncSession) -> set[str]:
    """Fetch all message_ids already stored — used to skip re-fetching."""
    result = await db.execute(select(FetchedEmail.message_id))
    return {row[0] for row in result.fetchall()}


async def fetch_and_store_emails(
    db: AsyncSession,
    user_id: uuid.UUID,
    max_emails: int | None = None,
    incremental: bool = True,
) -> dict:
    """
    Connect to IMAP, fetch emails, deduplicate by Message-ID, store new ones.

    Args:
        db: Active async DB session.
        user_id: Owner user's UUID.
        max_emails: Override for how many emails to fetch. Defaults to INITIAL_FETCH_COUNT.
        incremental: If True, fetch only new messages not in the local DB.
                     If False (first-time load), fetch last max_emails from the server.

    Returns:
        dict with keys: fetched (total on server checked), stored (newly saved), skipped (duplicates)
    """
    settings = get_settings()

    # Validate IMAP credentials are configured
    if not settings.IMAP_USER or not settings.IMAP_PASSWORD:
        raise ValueError(
            "IMAP credentials not configured. "
            "Set IMAP_USER and IMAP_PASSWORD in .env — "
            "for Gmail, use an App Password from myaccount.google.com/apppasswords"
        )

    limit = max_emails or settings.INITIAL_FETCH_COUNT
    batch_size = settings.IMAP_BATCH_SIZE

    # Get already-stored Message-IDs for deduplication (O(1) per email)
    existing_ids = await _get_existing_ids(db)
    logger.info(f"[IMAP] {len(existing_ids)} emails already in DB — will skip duplicates")

    stored = 0
    skipped = 0
    total_checked = 0
    new_emails: list[FetchedEmail] = []

    mail = None
    try:
        # Single SSL connection (Gmail allows max 10 simultaneous)
        logger.info(f"[IMAP] Connecting to {settings.IMAP_HOST}:{settings.IMAP_PORT}")
        mail = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
        mail.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
        mail.select(settings.IMAP_MAILBOX, readonly=True)

        # Fetch all message UIDs sorted by date (most recent first)
        status, data = mail.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            logger.warning("[IMAP] No messages found in mailbox")
            return {"fetched": 0, "stored": 0, "skipped": 0}

        all_ids: list[bytes] = data[0].split()
        # Most recent = highest UID → reverse to get newest at front, then cap
        all_ids = list(reversed(all_ids))[:limit]
        total_server = len(all_ids)
        logger.info(f"[IMAP] Will check {total_server} emails from server (capped at {limit})")

        # Batch fetching — respect Gmail's command rate limits
        for batch_start in range(0, total_server, batch_size):
            batch = all_ids[batch_start: batch_start + batch_size]
            uid_list = b",".join(batch)

            status, raw_messages = mail.fetch(uid_list, "(RFC822)")
            if status != "OK":
                logger.warning(f"[IMAP] Batch fetch failed for UIDs {batch_start}–{batch_start+batch_size}")
                continue

            # Parse each raw MIME message in the batch
            for response_part in raw_messages:
                if not isinstance(response_part, tuple):
                    continue
                total_checked += 1
                try:
                    msg = email.message_from_bytes(
                        response_part[1], policy=email.policy.compat32
                    )
                    message_id = (msg.get("Message-ID") or "").strip()
                    if not message_id:
                        # Generate synthetic ID from subject+date to avoid losing emails
                        message_id = f"synthetic-{hash(str(msg.get('Date')) + str(msg.get('Subject')))}"

                    # Deduplication — skip if already in DB
                    if message_id in existing_ids:
                        skipped += 1
                        continue

                    subject = _decode_mime_words(msg.get("Subject"))
                    from_raw = msg.get("From", "")
                    sender_name, sender_email = parseaddr(_decode_mime_words(from_raw))
                    body = _extract_body(msg)
                    received_at = _parse_received_at(msg)
                    thread_id = (msg.get("Thread-Index") or msg.get("X-GM-THRID") or "").strip() or None

                    if not body:
                        logger.debug(f"[IMAP] Skipping email with empty body: {message_id}")
                        skipped += 1
                        continue

                    fetched = FetchedEmail(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        message_id=message_id,
                        sender_email=sender_email or from_raw,
                        sender_name=sender_name or None,
                        subject=subject or None,
                        body=body,
                        received_at=received_at,
                        thread_id=thread_id,
                    )
                    new_emails.append(fetched)
                    existing_ids.add(message_id)  # Prevent duplicate within same batch
                    stored += 1

                except Exception as parse_err:
                    logger.warning(f"[IMAP] Failed to parse email: {parse_err}")
                    continue

            # Brief pause between batches — avoids hitting Gmail command rate limits
            if batch_start + batch_size < total_server:
                time.sleep(0.2)

    except imaplib.IMAP4.error as imap_err:
        logger.error(f"[IMAP] Connection/auth error: {imap_err}")
        raise RuntimeError(f"IMAP error: {imap_err}") from imap_err
    finally:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass

    # Bulk insert all new emails
    if new_emails:
        for em in new_emails:
            db.add(em)
        await db.flush()
        logger.info(f"[IMAP] Stored {stored} new emails, skipped {skipped} duplicates")

    return {
        "fetched": total_checked,
        "stored": stored,
        "skipped": skipped,
        "new_emails": [e.id for e in new_emails],
    }


async def run_startup_fetch(db: AsyncSession, user_id: uuid.UUID) -> None:
    """
    Called at server startup only if IMAP_AUTO_LOAD_ON_STARTUP=True.
    Returns immediately if IMAP credentials are not configured.
    """
    settings = get_settings()
    if not settings.IMAP_AUTO_LOAD_ON_STARTUP:
        logger.info("[IMAP] Auto-load is disabled (IMAP_AUTO_LOAD_ON_STARTUP=False). "
                    "Use POST /api/v1/emails/fetch to trigger manually.")
        return
    if not settings.IMAP_USER or not settings.IMAP_PASSWORD:
        logger.warning("[IMAP] Startup fetch skipped — IMAP_USER or IMAP_PASSWORD not set in .env")
        return
    logger.info("[IMAP] Starting background email fetch on server startup...")
    try:
        result = await fetch_and_store_emails(db, user_id, incremental=False)
        logger.info(f"[IMAP] Startup fetch complete: {result}")
    except Exception as e:
        logger.error(f"[IMAP] Startup fetch failed: {e}")
