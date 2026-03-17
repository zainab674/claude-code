import time
import hashlib
from typing import Optional

_token_store = {}
_token_expiry = {}

async def store_reset_token(token: str, user_id: str, ttl_seconds: int = 3600) -> bool:
    key = hashlib.sha256(token.encode()).hexdigest()
    _token_store[key] = user_id
    _token_expiry[key] = time.time() + ttl_seconds
    return True

async def consume_reset_token(token: str) -> Optional[str]:
    key = hashlib.sha256(token.encode()).hexdigest()
    user_id = _token_store.get(key)
    expiry = _token_expiry.get(key)
    
    if not user_id or (expiry and time.time() > expiry):
        _token_store.pop(key, None)
        _token_expiry.pop(key, None)
        return None
        
    _token_store.pop(key, None)
    _token_expiry.pop(key, None)
    return user_id
