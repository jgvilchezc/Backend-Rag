import secrets
import string
from passlib.context import CryptContext
from supabase import Client
from datetime import datetime, timezone

# We use bcrypt for hashing the keys before storing them
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class ApiKeyService:
    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client

    def generate_api_key(self) -> str:
        """
        Generates a secure random API key with a prefix.
        Format: sk_rag_<32 random chars>
        """
        alphabet = string.ascii_letters + string.digits
        random_str = ''.join(secrets.choice(alphabet) for _ in range(32))
        return f"sk_rag_{random_str}"

    def hash_key(self, api_key: str) -> str:
        """
        Hashes the API key for secure storage.
        """
        return pwd_context.hash(api_key)

    def verify_key(self, plain_key: str, hashed_key: str) -> bool:
        """
        Verifies a plain API key against the stored hash.
        """
        return pwd_context.verify(plain_key, hashed_key)

    async def create_api_key(self, user_id: str, name: str) -> dict:
        """
        Generates, hashes, and stores a new API key for the user.
        Returns the raw API key (show this to user ONCE) and the ID.
        """
        raw_key = self.generate_api_key()
        key_hash = self.hash_key(raw_key)

        response = self.supabase.table("api_keys").insert({
            "user_id": user_id,
            "name": name,
            "key_hash": key_hash,
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()

        if not response.data:
            raise Exception("Failed to create API key in database")

        record = response.data[0]
        # Return the raw key so the user can see it once
        return {
            "id": record["id"],
            "name": record["name"],
            "api_key": raw_key, 
            "created_at": record["created_at"]
        }

    async def validate_api_key(self, api_key: str) -> str:
        """
        Validates an API key from a request.
        Finds the user associated with the key.
        Updates 'last_used_at' timestamp.
        Returns user_id if valid, None otherwise.
        """
        # 1. We need to find the key in DB. 
        # Since we are hashing, we can't search by plain key directly effectively if we used standard bcrypt with salt.
        # However, looking up by hash is impossible if salt is random per hash (which it is).
        # SOLUTION: 
        # Ideally, we should store a non-secret prefix or ID to lookup the row, and then verify the full key.
        # BUT, to keep it simple as per plan, we might have to scan? NO, scanning is bad.
        #
        # ALTERNATIVE: Use a static salt? No, insecure.
        #
        # CORRECT APPROACH for API Keys:
        # Usually keys are `prefix_PUBLICID_SECRET`.
        # We store PUBLICID to find the row, then verify SECRET hash.
        #
        # LET'S ADJUST implementation to be safe but simple.
        # IF we just use the raw key as the lookup... no, we want to hash it.
        #
        # Re-reading common practices:
        # Store `hash(key)`. If we use a fast hash (SHA256) we can search.
        # If we use bcrypt (slow, salted), we cannot search.
        #
        # Let's use SHA256 for the "lookupable" hash if we want speed, OR
        # Change the strategy to:
        # Key = `sk_rag_<32_random>`.
        # We can't search by it if we bcrypt it.
        #
        # Let's change the key format to be `sk_rag_<id>_<secret>`.
        # OR simply duplicate: store a "masked" version or "checksum" to filter candidates?
        #
        # Let's go with: Store SHA256(key) which is deterministic.
        # Bcrypt is for passwords (slow). API keys need to be fast.
        # SHA256 is generally acceptable for API keys if they are high entropy (which 32 chars is).
        #
        # REVISION: creating a fast hash for lookup.
        pass

# REDEFINING THE CLASS AND IMPORTS TO USE SHA256 FOR DETERMINISTIC STORAGE
import hashlib

class ApiKeyService:
    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client

    def generate_api_key(self) -> str:
        alphabet = string.ascii_letters + string.digits
        random_str = ''.join(secrets.choice(alphabet) for _ in range(40))
        return f"sk_rag_{random_str}"

    def hash_key(self, api_key: str) -> str:
        # SHA256 is deterministic, allowing us to query by hash
        return hashlib.sha256(api_key.encode()).hexdigest()

    async def create_api_key(self, user_id: str, name: str) -> dict:
        raw_key = self.generate_api_key()
        key_hash = self.hash_key(raw_key)

        response = self.supabase.table("api_keys").insert({
            "user_id": user_id,
            "name": name,
            "key_hash": key_hash,
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        
        record = response.data[0]
        return {
            "id": record["id"],
            "name": record["name"],
            "api_key": raw_key,
            "created_at": record["created_at"]
        }

    async def validate_api_key(self, api_key: str) -> str:
        """
        Returns user_id if key is valid, else raises Exception or returns None.
        Also updates last_used_at.
        """
        key_hash = self.hash_key(api_key)
        
        # We need to use the 'service_role' client or ensure RLS allows reading by key_hash? 
        # Actually standard client might be bound to a user if we logged in.
        # BUT here we are authenticating. We probably need a SERVICE_ROLE client for this lookup 
        # because the request is anonymous until validated.
        #
        # However, `main.py` initializes `supabase` with `SUPABASE_KEY` which is likely the Service Role Key 
        # (based on line 27 comment in main.py: "Service Role potentially").
        # If it is Service Role, we can bypass RLS.
        
        response = self.supabase.table("api_keys").select("id, user_id").eq("key_hash", key_hash).execute()
        
        if not response.data:
            return None
            
        record = response.data[0]
        
        # Update usage async (fire and forget ideally, but here await)
        # We don't want to block too much, but it's fine for now.
        try:
            self.supabase.table("api_keys").update({
                "last_used_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", record["id"]).execute()
        except:
            pass # Ignore update failure to not block auth
            
        return record["user_id"]
