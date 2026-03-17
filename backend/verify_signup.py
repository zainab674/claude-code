import urllib.request
import json
import random
import string

BASE_URL = "http://localhost:8000"

def generate_random_string(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def test_signup_flow():
    email = f"admin_{generate_random_string()}@test.com"
    company_name = f"Test Company {generate_random_string()}"
    
    payload = {
        "company_name": company_name,
        "email": email,
        "password": "Password123!",
        "first_name": "Test",
        "last_name": "Admin"
    }
    
    print(f"Testing signup with email: {email}")
    
    # 1. Register
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}/auth/register", data=data, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req) as resp:
            reg_res = json.loads(resp.read().decode("utf-8"))
            token = reg_res["access_token"]
            print("Registration successful!")
            
        # 2. Verify immediate login (fetch user info)
        headers = {"Authorization": f"Bearer {token}"}
        req_me = urllib.request.Request(f"{BASE_URL}/users/me", headers=headers)
        with urllib.request.urlopen(req_me) as resp:
            user_data = json.loads(resp.read().decode("utf-8"))
            print(f"Logged in as: {user_data['email']} ({user_data['first_name']} {user_data['last_name']})")
            print(f"Role: {user_data['role']}")
            
    except urllib.error.HTTPError as e:
        print(f"Error: {e.code}")
        print(e.read().decode("utf-8"))

if __name__ == "__main__":
    test_signup_flow()
