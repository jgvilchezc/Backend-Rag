
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

print(f"Connecting to {url}...")
# Verify key is present
if not key:
    print("Error: SUPABASE_KEY not found in env")
    exit(1)

try:
    supabase = create_client(url, key)
    # Check if we can access documents
    res = supabase.table("documents").select("*").limit(1).execute()
    print("Success accessing documents")
    
    # Check if api_keys table exists (expecting error if not)
    try:
        res = supabase.table("api_keys").select("*").limit(1).execute()
        print("api_keys table exists")
    except Exception as e:
        print(f"api_keys table verify: {str(e)}")

except Exception as e:
    print(f"Connection Error: {str(e)}")
