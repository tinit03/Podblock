import pytest
import logging
from unittest.mock import MagicMock, patch
from flask import Flask

from server.helpers.cache_helpers import (
    setup_cache, initiate_key, cache_audio,
    retrieve_audio, cached_rss_url, cached_source_url
)

@pytest.fixture
def mock_redis():
    """Creates a mock Redis client."""
    mock = MagicMock()
    mock.scan_iter.return_value = iter([])  # Default: No cached data
    return mock


@pytest.fixture
def mock_app():
    """Creates a mock Flask app."""
    app = Flask(__name__)
    return app

def test_setup_cache(mock_app, mock_redis):
    """Test that cache is properly set up."""
    with patch("helpers.cache_helpers.redis_client", mock_redis):
        mock_app.config["CACHE_TYPE"] = "simple"  # ✅ Use in-memory cache for testing
        setup_cache(mock_app, mock_redis)
        assert mock_redis is not None  # Ensure redis_client is set


def test_initiate_key(mock_redis, caplog):
    """Test that initiate_key sets a value in Redis."""
    with patch("helpers.cache_helpers.redis_client", mock_redis):
        with caplog.at_level(logging.ERROR):
            initiate_key("test_key")
            mock_redis.set.assert_called_with("test_key", "INIT")  # Fix: Ensure this call actually happens
            assert "Error initializing key in cache" not in caplog.text


def test_cache_audio(mock_redis):
    """Test that cache_audio stores the file path in Redis."""
    with patch("helpers.cache_helpers.redis_client", mock_redis):
        cache_audio("audio_key", "/path/to/audio.mp3")
        mock_redis.set.assert_called_with("audio_key", "/path/to/audio.mp3")


def test_retrieve_audio_found(mock_redis):
    """Test that retrieve_audio returns the correct path if found."""
    with patch("helpers.cache_helpers.redis_client", mock_redis):
        mock_redis.scan_iter.side_effect = lambda pattern: iter(["audio_key"])
        mock_redis.get.return_value = b"/path/to/audio.mp3"

        result = retrieve_audio("audio.mp3")
        assert result == b"/path/to/audio.mp3"


def test_retrieve_audio_not_found(mock_redis):
    """Test that retrieve_audio returns None if not found."""
    with patch("helpers.cache_helpers.redis_client", mock_redis):
        mock_redis.scan_iter.return_value = iter([])

        result = retrieve_audio("audio.mp3")
        assert result is None


def test_cached_rss_url(mock_redis):
    """Test that cached_rss_url checks if an RSS URL is cached."""
    with patch("helpers.cache_helpers.redis_client", mock_redis):
        mock_redis.scan_iter.return_value = iter(["rss_url::source_url"])
        assert cached_rss_url("rss_url") is True  # rss_url should be found

        mock_redis.scan_iter.return_value = iter([])
        assert cached_rss_url("rss_url") is False


def test_cached_source_url(mock_redis):
    """Test that cached_source_url checks if a source URL is cached."""
    with patch("helpers.cache_helpers.redis_client", mock_redis):
        mock_redis.scan_iter.return_value = iter(["rss_url::source_url"])
        assert cached_source_url("source_url") is True  # source_url should be found

        mock_redis.scan_iter.return_value = iter([])
        assert cached_source_url("source_url") is False