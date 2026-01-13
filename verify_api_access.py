import requests
import jwt
import uuid
import sys

# Configuration
BASE_URL = "http://localhost:8000"

def get_forged_jwt(user_id):
    """Forge a JWT for testing (Dev mode only, no signature verification backend side yet)"""
    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "role": "authenticated"
    }
    # We sign with a dummy secret, backend is configured to ignore signature if secret is missing
    return jwt.encode(payload, "dummy_secret", algorithm="HS256")

def run_verification():
    print("--- Starting API Key Verification ---")
    
    # 1. Simulate a User (Using a known valid user ID from DB to satisfy FK)
    user_id = "56ad8681-defe-4340-bcaa-88305a6be5dd"
    token = get_forged_jwt(user_id)
    print(f"1. Simulated User ID: {user_id}")
    
    headers_auth = {"Authorization": f"Bearer {token}"}
    
    # 2. Create API Key
    print("2. Requesting new API Key...")
    try:
        resp = requests.post(
            f"{BASE_URL}/auth/api-keys", 
            json={"name": "Test Key"},
            headers=headers_auth
        )
        if resp.status_code != 200:
            print(f"FAILED to create key: {resp.text}")
            return False
            
        data = resp.json()
        api_key = data["api_key"]
        key_id = data["id"]
        print(f"   SUCCESS: Got key {api_key[:10]}... (ID: {key_id})")
        
    except Exception as e:
        print(f"FAILED connection: {e}")
        return False

    # 3. Test Access with API Key
    print("3. Testing access to /documents with API Key...")
    headers_key = {"X-API-Key": api_key}
    
    try:
        # We try to access documents. It should return empty list (new user) but 200 OK.
        resp = requests.get(f"{BASE_URL}/documents", headers=headers_key)
        
        if resp.status_code == 200:
            print(f"   SUCCESS: Accessed /documents. Response: {resp.json()}")
        else:
            print(f"FAILED: Status {resp.status_code}, Body: {resp.text}")
            return False
            
    except Exception as e:
        print(f"FAILED connection: {e}")
        return False

    # 4. Clean up (Revoke key)
    print("4. Testing Key Revocation...")
    try:
        # Revoke using the API Key itself? No, usually management needs the User context (JWT or Key).
        # Our endpoint uses `get_current_user_or_api_key` so either works.
        # Let's use the API Key to delete itself (if logic allows) or JWT.
        # Let's use JWT to be "User Dashboard" style.
        resp = requests.delete(f"{BASE_URL}/auth/api-keys/{key_id}", headers=headers_auth)
        if resp.status_code == 200:
            print("   SUCCESS: Key revoked.")
        else:
             print(f"WARN: Revoke failed {resp.status_code}")
             
    except Exception as e:
        print(f"WARN: Cleanup failed: {e}")

    print("\n--- Verification PASSED ---")
    return True

if __name__ == "__main__":
    success = run_verification()
    if not success:
        sys.exit(1)
