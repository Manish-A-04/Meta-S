"""
META-S Comprehensive Endpoint Test Suite
------------------------------------------
Tests ALL new + existing endpoints in sequence.
IMAP fetch is capped at 20 emails (safe for free Gmail tier).
Run with: python test_all_endpoints.py
"""

import asyncio
import httpx
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"
TIMEOUT = 60  # seconds per request (LLM calls can be slow)

# ── ANSI colours ───────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

results = []


def log(label: str, status: int, body: dict | str, ok: bool, latency_ms: int):
    icon = f"{GREEN}[OK]{RESET}" if ok else f"{RED}[FAIL]{RESET}"
    colour = GREEN if ok else RED
    print(f"\n{icon} {BOLD}{label}{RESET}  [{colour}{status}{RESET}]  ({latency_ms}ms)")
    if isinstance(body, dict):
        # Print only first 400 chars of response to keep output readable
        preview = json.dumps(body, indent=2, default=str)[:400]
        if len(json.dumps(body, default=str)) > 400:
            preview += "\n  ... (truncated)"
        for line in preview.splitlines():
            print(f"    {line}")
    else:
        print(f"    {str(body)[:300]}")
    results.append({"label": label, "status": status, "ok": ok, "latency_ms": latency_ms})


async def request(client: httpx.AsyncClient, method: str, path: str, token: str | None = None,
                  json_body=None, params=None, label: str = "") -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    start = time.perf_counter()
    try:
        resp = await client.request(
            method, f"{BASE_URL}{path}",
            headers=headers, json=json_body, params=params,
            timeout=TIMEOUT,
        )
        ms = int((time.perf_counter() - start) * 1000)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        ok = resp.status_code < 400
        log(label or f"{method} {path}", resp.status_code, body, ok, ms)
        return resp.status_code, body
    except Exception as e:
        ms = int((time.perf_counter() - start) * 1000)
        log(label or f"{method} {path}", 0, str(e), False, ms)
        return 0, {}


async def run_tests():
    print(f"\n{BOLD}{BLUE}═══════════════════════════════════════════════════{RESET}")
    print(f"{BOLD}{BLUE}  META-S Comprehensive Endpoint Test  {datetime.now().strftime('%H:%M:%S')}{RESET}")
    print(f"{BOLD}{BLUE}═══════════════════════════════════════════════════{RESET}")

    async with httpx.AsyncClient(follow_redirects=True) as client:

        # ── 1. HEALTH ──────────────────────────────────────────────────────────
        print(f"\n{BOLD}── Health Check ──{RESET}")
        _, health = await request(client, "GET", "/health", label="GET /health")

        # ── 2. AUTH ────────────────────────────────────────────────────────────
        print(f"\n{BOLD}── Auth ──{RESET}")
        _, reg = await request(client, "POST", "/auth/register",
                               json_body={"email": "test@meta-s.ai", "password": "TestPass123"},
                               label="POST /auth/register")

        _, login = await request(client, "POST", "/auth/login",
                                 json_body={"email": "test@meta-s.ai", "password": "TestPass123"},
                                 label="POST /auth/login")

        token = login.get("access_token", "")
        if not token:
            print(f"\n{RED}[FAIL] Login failed — cannot continue tests that require auth!{RESET}")
            print("  → Make sure the server is running: uvicorn app.main:app --reload")
            _print_summary()
            return

        # ── 3. IMAP FETCH (capped at 20 for free tier safety) ─────────────────
        print(f"\n{BOLD}── IMAP Fetch (max_emails=20 — safe for free Gmail) ──{RESET}")
        _, fetch = await request(client, "POST", "/emails/fetch", token=token,
                                 json_body={"max_emails": 20},
                                 label="POST /emails/fetch (max=20)")
        stored_count = fetch.get("stored", 0)

        # ── 4. LIST FETCHED EMAILS ─────────────────────────────────────────────
        print(f"\n{BOLD}── Fetched Emails List ──{RESET}")
        _, fetched_list = await request(client, "GET", "/emails/fetched", token=token,
                                        label="GET /emails/fetched")
        _, _ = await request(client, "GET", "/emails/fetched", token=token,
                              params={"priority": "HIGH", "limit": 5},
                              label="GET /emails/fetched?priority=HIGH")
        _, _ = await request(client, "GET", "/emails/fetched", token=token,
                              params={"days": 7, "limit": 10},
                              label="GET /emails/fetched?days=7")

        emails = fetched_list.get("emails", [])
        first_email_id = emails[0]["id"] if emails else None
        first_sender = emails[0]["sender_email"] if emails else "test@example.com"

        # ── 5. PRIORITY ────────────────────────────────────────────────────────
        print(f"\n{BOLD}── Priority ──{RESET}")
        _, _ = await request(client, "GET", "/emails/priority", token=token,
                              label="GET /emails/priority")
        _, _ = await request(client, "GET", "/emails/priority", token=token,
                              params={"label": "HIGH", "limit": 5},
                              label="GET /emails/priority?label=HIGH")
        _, _ = await request(client, "POST", "/emails/priority/refresh", token=token,
                              label="POST /emails/priority/refresh")

        # ── 6. EMBEDDING INDEX ────────────────────────────────────────────────
        print(f"\n{BOLD}── Embedding Index ──{RESET}")
        _, _ = await request(client, "POST", "/emails/index", token=token,
                              label="POST /emails/index")

        # ── 7. NATURAL LANGUAGE QUERIES ───────────────────────────────────────
        print(f"\n{BOLD}── NL Queries ──{RESET}")
        queries = [
            "Show me emails from the last 5 days",
            f"What was the last email from {first_sender}?",
            "List the most important emails",
            "Any emails about meetings or deadlines?",
        ]
        for q in queries:
            await request(client, "POST", "/query", token=token,
                          json_body={"query": q},
                          label=f"POST /query: \"{q[:45]}...\"")
            await asyncio.sleep(1)  # Brief pause between LLM calls

        # ── 8. BULK DRAFT (3 most recent emails) ──────────────────────────────
        print(f"\n{BOLD}── Bulk Draft Generation ──{RESET}")
        _, bulk = await request(client, "POST", "/emails/bulk-draft", token=token,
                                json_body={"count": 3},
                                label="POST /emails/bulk-draft (count=3)")

        drafts = bulk.get("drafts", [])
        draft_id = None
        for d in drafts:
            if d.get("draft_id"):
                draft_id = d["draft_id"]
                break

        # ── 9. DRAFT FEEDBACK & REDRAFT ────────────────────────────────────────
        print(f"\n{BOLD}── Draft Feedback & Edit ──{RESET}")
        if draft_id:
            _, _ = await request(client, "POST", f"/drafts/{draft_id}/feedback", token=token,
                                 json_body={"feedback": "Make it more formal and concise. Add a greeting."},
                                 label=f"POST /drafts/{{id}}/feedback")

            _, _ = await request(client, "PATCH", f"/drafts/{draft_id}", token=token,
                                 json_body={"content": "Dear Sender,\n\nThank you for your email. I will get back to you shortly.\n\nBest regards"},
                                 label=f"PATCH /drafts/{{id}} (direct edit)")

            _, _ = await request(client, "POST", f"/drafts/{draft_id}/approve", token=token,
                                 label=f"POST /drafts/{{id}}/approve")
        else:
            print(f"  {YELLOW}[WARN] No draft_id available — skipping draft feedback tests{RESET}")

        # ── 10. THREAD (only if we have an email with thread_id) ──────────────
        print(f"\n{BOLD}── Thread Summarizer ──{RESET}")
        thread_id_found = None
        for e in emails[:5]:
            # Check if any email has a thread_id via fetched list
            # (we don't have thread_id in FetchedEmailItem directly, skip if none)
            pass
        # Use a test thread_id from the first email if available
        await request(client, "GET", "/emails/threads/test-thread-001", token=token,
                      label="GET /emails/threads/{thread_id} (test thread)")

        # ── 11. FOLLOW-UPS ────────────────────────────────────────────────────
        print(f"\n{BOLD}── Follow-up Tracker ──{RESET}")
        _, _ = await request(client, "POST", "/followups/detect", token=token,
                             label="POST /followups/detect (auto-detect)")
        _, followups = await request(client, "GET", "/followups", token=token,
                                     label="GET /followups")

        # If we have an email, create a manual follow-up
        if first_email_id:
            _, fu = await request(client, "POST", f"/followups/{first_email_id}", token=token,
                                  json_body={"due_date": "2026-03-15", "reminder_text": "Reply to this email by the deadline"},
                                  label="POST /followups/{email_id} (manual)")

            # Update status of a follow-up if we got one
            fups = followups.get("followups", [])
            if fups:
                fu_id = fups[0]["followup_id"]
                await request(client, "PATCH", f"/followups/{fu_id}/status", token=token,
                              json_body={"status": "snoozed"},
                              label=f"PATCH /followups/{{id}}/status → snoozed")

        # ── 12. DAILY DIGEST ─────────────────────────────────────────────────
        print(f"\n{BOLD}── Daily Digest ──{RESET}")
        _, _ = await request(client, "GET", "/digest", token=token,
                             label="GET /digest")

        # ── 13. ANALYTICS ────────────────────────────────────────────────────
        print(f"\n{BOLD}── Analytics ──{RESET}")
        _, _ = await request(client, "GET", "/analytics", token=token,
                             label="GET /analytics")

        # ── 14. ORIGINAL TRIAGE (existing pipeline) ───────────────────────────
        print(f"\n{BOLD}── Original Email Triage Pipeline ──{RESET}")
        _, triage = await request(client, "POST", "/emails/triage", token=token,
                                  json_body={
                                      "subject": "Meeting Tomorrow at 2pm — Action Required",
                                      "body": "Hi, please confirm attendance for tomorrow's 2pm meeting. The agenda includes Q1 review. RSVP by EOD.",
                                      "force_reflection": False,
                                  },
                                  label="POST /emails/triage")

        email_triage_id = triage.get("email_id")
        if email_triage_id:
            await request(client, "GET", f"/emails/{email_triage_id}/drafts", token=token,
                          label="GET /emails/{id}/drafts")

        # ── 15. RAG DOCUMENTS ────────────────────────────────────────────────
        print(f"\n{BOLD}── RAG Documents ──{RESET}")
        _, _ = await request(client, "POST", "/rag/documents", token=token,
                             json_body={"title": "Company Reply Policy", "content": "All emails must be replied to within 24 hours. Use formal language."},
                             label="POST /rag/documents")
        _, _ = await request(client, "GET", "/rag/documents", token=token,
                             label="GET /rag/documents")

        # ── 16. METRICS ──────────────────────────────────────────────────────
        print(f"\n{BOLD}── Metrics ──{RESET}")
        _, _ = await request(client, "GET", "/metrics", token=token,
                             label="GET /metrics")

    _print_summary()


def _print_summary():
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    failed = total - passed

    print(f"\n{BOLD}{'═'*51}{RESET}")
    print(f"{BOLD}  TEST SUMMARY{RESET}")
    print(f"{'─'*51}")
    print(f"  Total:   {total}")
    print(f"  {GREEN}Passed:  {passed}{RESET}")
    print(f"  {RED if failed else GREEN}Failed:  {failed}{RESET}")
    print(f"{'─'*51}")
    if failed:
        print(f"\n{RED}Failed endpoints:{RESET}")
        for r in results:
            if not r["ok"]:
                print(f"  {RED}[FAIL]{RESET} {r['label']}  [HTTP {r['status']}]")
    else:
        print(f"\n{GREEN}All tests passed! [OK]{RESET}")
    print(f"{BOLD}{'═'*51}{RESET}\n")


if __name__ == "__main__":
    asyncio.run(run_tests())
