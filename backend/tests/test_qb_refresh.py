import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta
from routes.quickbooks import _ensure_fresh_token, QuickBooksConnection, _refresh_locks
import services.quickbooks as qb_svc

def create_mock_conn(company_id="test_company", expired=True):
    conn = MagicMock(spec=QuickBooksConnection)
    conn.company_id = company_id
    if expired:
        conn.token_expires_at = datetime.utcnow() - timedelta(minutes=5)
    else:
        conn.token_expires_at = datetime.utcnow() + timedelta(hours=1)
    conn.refresh_token = "some_rt"
    conn.access_token = "some_at"
    conn.refresh_expires_at = datetime.utcnow() + timedelta(days=100)
    conn.save = AsyncMock()
    return conn

@pytest.mark.asyncio
async def test_ensure_fresh_token_success():
    # Mock connection
    conn = create_mock_conn()

    # Clear locks
    _refresh_locks.clear()

    # Mock qb_svc methods
    with patch("services.quickbooks.is_token_expired") as mock_expired, \
         patch("services.quickbooks.refresh_access_token", new_callable=AsyncMock) as mock_refresh, \
         patch("services.quickbooks.parse_token_response") as mock_parse, \
         patch("models.QuickBooksConnection.find_one", new_callable=AsyncMock) as mock_find:
        
        mock_expired.return_value = True
        mock_refresh.return_value = {"access_token": "new_at", "refresh_token": "new_rt"}
        mock_parse.return_value = {
            "access_token": "new_at",
            "refresh_token": "new_rt",
            "token_expires_at": datetime.utcnow() + timedelta(hours=1),
            "refresh_expires_at": datetime.utcnow() + timedelta(days=100)
        }
        mock_find.return_value = conn

        token = await _ensure_fresh_token(conn)

        assert token == "new_at"
        assert conn.access_token == "new_at"
        assert conn.refresh_token == "new_rt"
        mock_refresh.assert_called_once()
        conn.save.assert_called_once()

@pytest.mark.asyncio
async def test_ensure_fresh_token_concurrency():
    # Mock connection
    conn = create_mock_conn()

    # Mock qb_svc
    refresh_count = 0
    async def slow_refresh(rt):
        nonlocal refresh_count
        await asyncio.sleep(0.1)
        refresh_count += 1
        return {"access_token": f"at_{refresh_count}", "refresh_token": "rt"}

    _refresh_locks.clear()

    with patch("services.quickbooks.is_token_expired") as mock_expired, \
         patch("services.quickbooks.refresh_access_token", side_effect=slow_refresh), \
         patch("services.quickbooks.parse_token_response") as mock_parse, \
         patch("models.QuickBooksConnection.find_one", new_callable=AsyncMock) as mock_find:
        
        # 1. Req 1 outer check -> True
        # 2. Req 2 outer check -> True
        # 3. Req 1 inner check (inside lock) -> True (Proceed to refresh)
        # 4. Req 2 inner check (inside lock after Req 1 finishes) -> False (Skip refresh)
        mock_expired.side_effect = [True, True, True, False] 
        
        mock_parse.return_value = {
            "access_token": "at_1", "refresh_token": "rt",
            "token_expires_at": datetime.utcnow() + timedelta(hours=1),
            "refresh_expires_at": datetime.utcnow() + timedelta(days=100)
        }
        
        mock_find.return_value = conn

        # Run two refreshes concurrently
        results = await asyncio.gather(
            _ensure_fresh_token(conn),
            _ensure_fresh_token(conn)
        )

        assert results[0] == "at_1"
        assert results[1] == "at_1"
        assert refresh_count == 1
