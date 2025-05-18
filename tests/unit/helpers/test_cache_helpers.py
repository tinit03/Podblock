import pytest
from unittest.mock import MagicMock

@pytest.fixture
def fake_redis(monkeypatch):
    import server.helpers.cache_helpers as cache_helpers
    mock_redis = MagicMock()
    monkeypatch.setattr(cache_helpers, "r", mock_redis)
    return mock_redis

def test_initiate_key_success(fake_redis):
    from server.helpers.cache_helpers import initiate_key
    lock = MagicMock()
    lock.acquire.return_value = True
    fake_redis.lock.return_value = lock

    assert initiate_key("test123") is True
    fake_redis.hset.assert_called_once()

def test_initiate_key_locked(fake_redis):
    from server.helpers.cache_helpers import initiate_key
    lock = MagicMock()
    lock.acquire.return_value = False
    fake_redis.lock.return_value = lock

    assert initiate_key("test123") is False

def test_update_total_number_of_chunks(fake_redis):
    from server.helpers.cache_helpers import update_total_number_of_chunks
    update_total_number_of_chunks("episode42", 3)
    fake_redis.hincrby.assert_called_once_with("meta::episode42", "chunks", 3)

def test_update_status_to_complete(fake_redis):
    from server.helpers.cache_helpers import update_status_to_complete
    update_status_to_complete("episode42")
    fake_redis.hset.assert_called_once_with("meta::episode42", "status", "COMPLETE")

def test_cached_url_true(fake_redis):
    from server.helpers.cache_helpers import cached_url
    fake_redis.exists.return_value = 1
    assert cached_url("url-key") is True

def test_cached_url_false(fake_redis):
    from server.helpers.cache_helpers import cached_url
    fake_redis.exists.return_value = 0
    assert cached_url("url-key") is False
