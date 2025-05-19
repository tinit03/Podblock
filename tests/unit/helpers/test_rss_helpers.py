import pytest
import requests
from unittest.mock import patch
from server.helpers.rss_helpers import fetch_rss, extract_rss_urls

def test_extract_rss_urls_valid():
    rss_content = b"""
    <rss><channel>
    <item><enclosure url="http://test.com/audio.mp3" type="audio/mpeg"/></item>
    </channel></rss>
    """
    urls = extract_rss_urls(rss_content)
    assert urls == ["http://test.com/audio.mp3"]

def test_extract_rss_urls_empty():
    with pytest.raises(ValueError):
        extract_rss_urls(b"")

@patch("server.helpers.rss_helpers.requests.get")
def test_fetch_rss_success(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.headers = {"Content-Type": "application/xml"}
    mock_get.return_value.content = b"<rss></rss>"
    result = fetch_rss("http://example.com/feed.xml")
    assert result == b"<rss></rss>"