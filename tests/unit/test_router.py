import pytest
from unittest.mock import MagicMock, patch
import sys
import os
mock_audio_segment = MagicMock()
mock_audio_segment.from_file.return_value = MagicMock(name="AudioSegment")

os.environ["OPENAI_API_KEY"] = "fake-key-for-tests"

sys.modules["pydub"] = MagicMock(AudioSegment=mock_audio_segment)
sys.modules["pydub.audio_segment"] = MagicMock(AudioSegment=mock_audio_segment)

from flask import Flask
from server.router import audio_bp

@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(audio_bp)
    return app.test_client()
@patch("server.router.fetch_rss")
@patch("server.router.extract_rss_urls")
@patch("server.router.process_url_task.delay")
def test_process_rss_success(mock_delay, mock_extract, mock_fetch, client):
    mock_fetch.return_value = b"<rss>...</rss>"
    mock_extract.return_value = ["https://audio1.mp3", "https://audio2.mp3"]

    response = client.post("/rss?url=https://example.com/feed.xml")

    assert response.status_code == 200
    assert response.data == b"retrieved"
    assert mock_delay.call_count == 2


def test_process_rss_missing_url(client):
    response = client.post("/rss")
    assert response.status_code == 400
    assert b"No url provided" in response.data


@patch("server.router.cached_url", return_value=False)
@patch("server.router.initiate_key", return_value=True)
@patch("server.router.initiate_streaming_task.delay")
@patch("server.router.retrieve_audio", return_value=b"audio-bytes")
def test_request_podcast_new(mock_retrieve, mock_stream, mock_key, mock_cached, client):
    response = client.get("/podcast?url=https://example.com/ep.mp3")

    assert response.status_code == 200
    assert response.data == b"audio-bytes"
    mock_stream.assert_called_once()


@patch("server.router.cached_url", return_value=True)
@patch("server.router.retrieve_audio", return_value=b"cached-audio")
def test_request_podcast_cached(mock_retrieve, mock_cached, client):
    response = client.get("/podcast?url=https://example.com/ep.mp3")

    assert response.status_code == 200
    assert response.data == b"cached-audio"


def test_request_podcast_missing_url(client):
    response = client.get("/podcast")
    assert response.status_code == 400
    assert b"No url provided" in response.data