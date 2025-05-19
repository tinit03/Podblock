import pytest
import os
from unittest.mock import patch, MagicMock

patcher = patch("server.audio_processing.AudioSegment.from_file", return_value=MagicMock(name="AudioSegment"))
patcher.start()
from server.tasks import process_url_task, initiate_streaming_task

def teardown_module(module):
    patcher.stop()
@pytest.fixture(autouse=True, scope="module")
def mock_env_key():
    with patch.dict(os.environ, {"OPENAI_API_KEY": "mock-key"}):
        yield
@patch("server.tasks.fetch_audio")
@patch("server.tasks.initiate_key")
@patch("server.tasks.cached_url", return_value=False)
@patch("server.tasks.process_audio")
def test_process_url_task_uncached(mock_process, mock_cached, mock_initiate, mock_fetch):
    dummy_audio = MagicMock()
    mock_fetch.return_value = dummy_audio
    result = process_url_task.run("http://test.com/audio.mp3")
    assert "Processing complete" in result
    mock_initiate.assert_called_once()
    mock_process.assert_called_once()


@patch("server.tasks.cached_url", return_value=True)
def test_process_url_task_cached(mock_cached):
    result = process_url_task.run("http://test.com/already.mp3")
    assert "already cached" in result


@patch("server.tasks.fetch_audio")
@patch("server.tasks.transcribe_audio", return_value="transcript")
@patch("server.tasks.detect_ads", return_value=[])
@patch("server.tasks.remove_ads", side_effect=lambda audio, ads: audio)
@patch("server.tasks.cache_chunk")
@patch("server.tasks.update_total_number_of_chunks")
@patch("server.tasks.process_audio")
def test_initiate_streaming_task(mock_process, mock_chunks, mock_cache, mock_remove, mock_detect, mock_transcribe, mock_fetch):
    audio = MagicMock()
    audio.__getitem__.side_effect = lambda s: audio
    mock_fetch.return_value = audio

    result = initiate_streaming_task.run("http://test.com/streaming.mp3")
    assert "Processing complete" in result
    mock_cache.assert_called_once()
    mock_process.assert_called_once()
