import urllib.request
import json

BASE_URL = "http://localhost:8000"

def test_leave_post():
    # Login
    login_data = json.dumps({"email": "admin@acme.com", "password": "Admin123!"}).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}/auth/login", data=login_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        token = data["access_token"]
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Payload from user
    payload = {
        "employee_id": "6fada5b0-e098-4b14-9f50-309ba12886cd",
        "leave_type": "fmla",
        "start_date": "2026-03-18",
        "expected_return": "2026-03-19",
        "intermittent": False,
        "is_paid": None,
        "reason": "hhhhhhhhh"
    }

    print(f"Testing POST /leave with payload: {json.dumps(payload)}")
    post_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}/leave", data=post_data, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Status Code: {resp.status}")
            print(f"Response Body: {resp.read().decode('utf-8')}")
    except urllib.error.HTTPError as e:
        print(f"Status Code: {e.code}")
        print(f"Response Body: {e.read().decode('utf-8')}")

if __name__ == "__main__":
    test_leave_post()
