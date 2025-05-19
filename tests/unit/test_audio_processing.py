import pytest
from unittest.mock import patch, MagicMock
import sys
import os
# Patch pydub to avoid FileNotFoundError during import
mock_audio_segment = MagicMock()
mock_audio_segment.from_file.return_value = MagicMock(name="AudioSegment")
mock_audio_segment.silent = MagicMock(side_effect=lambda duration: MagicMock(duration=duration, __len__=lambda self: duration))

sys.modules["pydub"] = MagicMock(AudioSegment=mock_audio_segment)
sys.modules["pydub.audio_segment"] = MagicMock(AudioSegment=mock_audio_segment)

# Now safe to import audio_processing
from server.audio_processing import (
    chunk_audio,
    remove_ads,
    detect_ads,
    transcribe_audio,
    process_audio,
)

@pytest.fixture(autouse=True, scope="module")
def mock_env_key():
    with patch.dict(os.environ, {"OPENAI_API_KEY": "mock-key"}):
        yield
@pytest.fixture
def dummy_audio_segment():
    return MagicMock(duration_seconds=10, __len__=lambda self: 10000)


def test_chunk_audio_short_segment(dummy_audio_segment):
    chunks = chunk_audio(dummy_audio_segment, chunk_duration_seconds=15)
    assert len(chunks) == 1


def test_chunk_audio_multiple_chunks():
    audio = MagicMock()
    audio.__len__.return_value = 500000  # 500 seconds in ms
    audio.duration_seconds = 500
    chunks = chunk_audio(audio, chunk_duration_seconds=240)
    assert len(chunks) >= 2


def test_remove_ads_merges_and_cuts():
    audio = MagicMock()
    audio.__len__.return_value = 30000  # 30s in ms
    audio.__getitem__.side_effect = lambda x: MagicMock()
    audio.empty.return_value = MagicMock()
    ads = [
        {"start": 2.0, "end": 5.0, "summary": "First Ad"},
        {"start": 5.1, "end": 8.0, "summary": "Second Ad"},
        {"start": 25.0, "end": 29.5, "summary": "Final Ad"},
    ]
    result = remove_ads(audio, ads)
    assert result is not None


@patch("server.audio_processing.batched_model.transcribe")
def test_transcribe_audio(mock_transcribe, dummy_audio_segment):
    mock_transcribe.return_value = ([MagicMock(words=[
        MagicMock(start=0.0, end=0.5, word="Hello"),
        MagicMock(start=0.6, end=1.0, word="world")
    ])], None)

    transcript = transcribe_audio(dummy_audio_segment)
    assert "[0.0-0.5] Hello" in transcript
    assert "[0.6-1.0] world" in transcript


@patch("server.audio_processing.client.chat.completions.create")
def test_detect_ads_parsing(mock_create):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = (
        "start: 10.0, end: 15.0, summary: 'Buy now!'\n"
        "start: 20.0, end: 22.0, summary: 'Limited offer'"
    )
    mock_create.return_value = mock_resp

    ads = detect_ads("some fake transcript")
    assert ads == [
        {"start": 10.0, "end": 15.0, "summary": "Buy now!"},
        {"start": 20.0, "end": 22.0, "summary": "Limited offer"},
    ]


@patch("server.audio_processing.transcribe_audio", return_value="fake transcript")
@patch("server.audio_processing.detect_ads", return_value=[])
@patch("server.audio_processing.remove_ads", side_effect=lambda audio, ads, flag=None: audio)
@patch("server.audio_processing.cache_chunk")
@patch("server.audio_processing.update_total_number_of_chunks")
@patch("server.audio_processing.update_status_to_complete")
def test_process_audio_simple(
    mock_status,
    mock_total,
    mock_cache,
    mock_remove,
    mock_detect,
    mock_transcribe,
):
    dummy_audio = MagicMock()
    dummy_audio.frame_rate = 44100
    dummy_audio.duration_seconds = 10
    dummy_audio.__len__.return_value = 10000
    dummy_audio.__getitem__.side_effect = lambda x: dummy_audio

    process_audio(dummy_audio, url="test-key", streaming=False)

    mock_total.assert_called_once()
    mock_cache.assert_called()
    mock_status.assert_called_once()
