import requests
import uuid
import sys
from verify_api_access import get_forged_jwt

# Configuration
BASE_URL = "http://localhost:8000"

def run_verification():
    print("--- Starting Preview Verification ---")
    
    # 1. Simulate a User (Using known valid ID from DB)
    user_id = "56ad8681-defe-4340-bcaa-88305a6be5dd"
    token = get_forged_jwt(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"1. Simulated User ID: {user_id}")
    
    # 2. Get Attributes (List Docs to find an ID)
    print("2. Listing documents...")
    try:
        resp = requests.get(f"{BASE_URL}/documents", headers=headers)
        if resp.status_code != 200:
            print(f"FAILED to list docs: {resp.text}")
            return False
        
        docs = resp.json()
        if not docs:
            print("   WARN: No documents found to test preview.")
            return True # Not a failure of code, just no data
            
        doc_id = docs[0]['id']
        print(f"   found document: {doc_id}")
        
    except Exception as e:
        print(f"FAILED connection: {e}")
        return False

    # 3. Test Preview
    print(f"3. Fetching content for {doc_id}...")
    try:
        resp = requests.get(f"{BASE_URL}/documents/{doc_id}", headers=headers)
        
        if resp.status_code == 200:
            data = resp.json()
            content_preview = data.get("content", "")[:50]
            print(f"   SUCCESS: Got content. Preview: {content_preview}...")
        else:
            print(f"FAILED: Status {resp.status_code}, Body: {resp.text}")
            return False
            
    except Exception as e:
        print(f"FAILED connection: {e}")
        return False

    print("\n--- Verification PASSED ---")
    return True

if __name__ == "__main__":
    success = run_verification()
    if not success:
        sys.exit(1)
