import httpx
import sys
import uuid

BASE_URL = "http://localhost:8000/api/v1"
TEST_EMAIL = f"test_{uuid.uuid4().hex[:8]}@example.com"
TEST_PASSWORD = "TestPassword123!"


def print_result(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    icon = "+" if passed else "-"
    msg = f"[{icon}] {name}: {status}"
    if detail:
        msg += f" | {detail}"
    print(msg)
    return passed


def main():
    client = httpx.Client(timeout=120.0)
    results = []
    access_token = None
    email_id = None

    print("=" * 60)
    print("META-S Endpoint Test Suite")
    print(f"Base URL: {BASE_URL}")
    print(f"Test User: {TEST_EMAIL}")
    print("=" * 60)

    print("\n--- Health Check ---")
    try:
        resp = client.get(f"{BASE_URL}/health")
        passed = resp.status_code == 200 and resp.json().get("status") == "ok"
        results.append(print_result("Health Check", passed, f"Status: {resp.status_code}"))
    except Exception as e:
        results.append(print_result("Health Check", False, str(e)))

    print("\n--- Register ---")
    try:
        resp = client.post(f"{BASE_URL}/auth/register", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        })
        passed = resp.status_code == 200 and "user_id" in resp.json()
        results.append(print_result("Register", passed, f"Status: {resp.status_code}"))
    except Exception as e:
        results.append(print_result("Register", False, str(e)))

    print("\n--- Register Duplicate ---")
    try:
        resp = client.post(f"{BASE_URL}/auth/register", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        })
        passed = resp.status_code == 409
        results.append(print_result("Register Duplicate Rejected", passed, f"Status: {resp.status_code}"))
    except Exception as e:
        results.append(print_result("Register Duplicate Rejected", False, str(e)))

    print("\n--- Login ---")
    try:
        resp = client.post(f"{BASE_URL}/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        })
        data = resp.json()
        passed = resp.status_code == 200 and "access_token" in data
        if passed:
            access_token = data["access_token"]
        results.append(print_result("Login", passed, f"Status: {resp.status_code}"))
    except Exception as e:
        results.append(print_result("Login", False, str(e)))

    print("\n--- Login Wrong Password ---")
    try:
        resp = client.post(f"{BASE_URL}/auth/login", json={
            "email": TEST_EMAIL,
            "password": "WrongPassword999!",
        })
        passed = resp.status_code == 401
        results.append(print_result("Login Wrong Password Rejected", passed, f"Status: {resp.status_code}"))
    except Exception as e:
        results.append(print_result("Login Wrong Password Rejected", False, str(e)))

    if not access_token:
        print("\nCannot proceed without access token. Exiting.")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {access_token}"}

    print("\n--- Add RAG Document ---")
    try:
        resp = client.post(f"{BASE_URL}/rag/documents", json={
            "title": "Company Leave Policy",
            "content": "Employees are entitled to 20 days of paid leave per year. Leave requests must be submitted at least 3 days in advance to the HR department.",
        }, headers=headers)
        passed = resp.status_code == 200 and "document_id" in resp.json()
        results.append(print_result("Add RAG Document", passed, f"Status: {resp.status_code}"))
    except Exception as e:
        results.append(print_result("Add RAG Document", False, str(e)))

    print("\n--- Add RAG Document 2 ---")
    try:
        resp = client.post(f"{BASE_URL}/rag/documents", json={
            "title": "Meeting Room Booking",
            "content": "Conference rooms can be booked through the internal portal. Room A seats 10 people, Room B seats 6, and Room C seats 20. Bookings are limited to 2 hours.",
        }, headers=headers)
        passed = resp.status_code == 200 and "document_id" in resp.json()
        results.append(print_result("Add RAG Document 2", passed, f"Status: {resp.status_code}"))
    except Exception as e:
        results.append(print_result("Add RAG Document 2", False, str(e)))

    print("\n--- List RAG Documents ---")
    try:
        resp = client.get(f"{BASE_URL}/rag/documents", headers=headers)
        data = resp.json()
        passed = resp.status_code == 200 and len(data.get("documents", [])) >= 2
        results.append(print_result("List RAG Documents", passed, f"Status: {resp.status_code}, Count: {len(data.get('documents', []))}"))
    except Exception as e:
        results.append(print_result("List RAG Documents", False, str(e)))

    print("\n--- Email Triage (Work) ---")
    try:
        resp = client.post(f"{BASE_URL}/emails/triage", json={
            "subject": "Meeting Tomorrow",
            "body": "Hi, I would like to book a conference room for our team meeting tomorrow at 2 PM. We will need a room that seats at least 8 people. Can you help?",
            "force_reflection": True,
            "max_reflections": 2,
        }, headers=headers)
        data = resp.json()
        passed = resp.status_code == 200 and "email_id" in data and "final_draft" in data
        if passed:
            email_id = data["email_id"]
        results.append(print_result("Email Triage (Work)", passed, f"Status: {resp.status_code}, Classification: {data.get('classification', 'N/A')}"))
    except Exception as e:
        results.append(print_result("Email Triage (Work)", False, str(e)))

    print("\n--- Email Triage (Spam) ---")
    try:
        resp = client.post(f"{BASE_URL}/emails/triage", json={
            "subject": "You Won $1,000,000!!!",
            "body": "Congratulations! You have been selected as the winner of our lottery. Click this link to claim your prize money immediately. Act now before the offer expires!",
            "max_reflections": 1,
        }, headers=headers)
        data = resp.json()
        passed = resp.status_code == 200 and "email_id" in data
        results.append(print_result("Email Triage (Spam)", passed, f"Status: {resp.status_code}, Classification: {data.get('classification', 'N/A')}"))
    except Exception as e:
        results.append(print_result("Email Triage (Spam)", False, str(e)))

    print("\n--- Email Triage (Urgent) ---")
    try:
        resp = client.post(f"{BASE_URL}/emails/triage", json={
            "subject": "URGENT: Server Down",
            "body": "Our production server went down 5 minutes ago. All customer-facing services are unavailable. We need immediate assistance from the DevOps team to restore services.",
            "max_reflections": 2,
        }, headers=headers)
        data = resp.json()
        passed = resp.status_code == 200 and "email_id" in data
        results.append(print_result("Email Triage (Urgent)", passed, f"Status: {resp.status_code}, Classification: {data.get('classification', 'N/A')}"))
    except Exception as e:
        results.append(print_result("Email Triage (Urgent)", False, str(e)))

    if email_id:
        print("\n--- Draft History ---")
        try:
            resp = client.get(f"{BASE_URL}/emails/{email_id}/drafts", headers=headers)
            data = resp.json()
            passed = resp.status_code == 200 and "drafts" in data and len(data["drafts"]) > 0
            results.append(print_result("Draft History", passed, f"Status: {resp.status_code}, Drafts: {len(data.get('drafts', []))}"))
        except Exception as e:
            results.append(print_result("Draft History", False, str(e)))
    else:
        results.append(print_result("Draft History", False, "Skipped - no email_id available"))

    print("\n--- Draft History (Not Found) ---")
    try:
        fake_id = str(uuid.uuid4())
        resp = client.get(f"{BASE_URL}/emails/{fake_id}/drafts", headers=headers)
        passed = resp.status_code == 404
        results.append(print_result("Draft History Not Found", passed, f"Status: {resp.status_code}"))
    except Exception as e:
        results.append(print_result("Draft History Not Found", False, str(e)))

    print("\n--- Metrics ---")
    try:
        resp = client.get(f"{BASE_URL}/metrics", headers=headers)
        data = resp.json()
        passed = resp.status_code == 200 and "total_emails_processed" in data
        results.append(print_result("Metrics", passed, f"Status: {resp.status_code}, Processed: {data.get('total_emails_processed', 0)}"))
    except Exception as e:
        results.append(print_result("Metrics", False, str(e)))

    print("\n--- Unauthorized Access ---")
    try:
        resp = client.post(f"{BASE_URL}/emails/triage", json={"body": "test"})
        passed = resp.status_code in [401, 403]
        results.append(print_result("Unauthorized Access Blocked", passed, f"Status: {resp.status_code}"))
    except Exception as e:
        results.append(print_result("Unauthorized Access Blocked", False, str(e)))

    print("\n" + "=" * 60)
    total = len(results)
    passed = sum(results)
    failed = total - passed
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print("=" * 60)

    client.close()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
