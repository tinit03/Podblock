import logging
from io import BytesIO
from pydub import AudioSegment
from server.audio_processing import chunk_audio, transcribe_chunks, stream_and_process_audio
from server.helpers.cache_helpers import get_audio

logger = logging.getLogger(__name__)


def test_chunk_audio():
    """Ensures that chunk audio works as expected"""
    audio_path = "resources/test_audio.mp3"
    chunks, chunk_duration = chunk_audio(audio_path)
    assert len(chunks) == 4


def test_transcribe_chunks():
    """Ensures that transcribe chunks works as expected"""
    audio_path = "resources/test_audio.mp3"
    chunks, chunk_duration = chunk_audio(audio_path)
    transcription = transcribe_chunks(chunks, chunk_duration)
    assert transcription != "No transcription"


def test_streaming():
    """Ensures that streaming works as expected"""
    audio_path = "resources/test_audio.mp3"
    processed_audio_path = "resources/test_audio_no_ads.mp3"

    with open(processed_audio_path, "wb") as out_f:
        byte_generator = stream_and_process_audio(audio_path)
        chunk_count = 0
        for audio_bytes in byte_generator:
            assert isinstance(audio_bytes, bytes)
            assert len(audio_bytes) > 0
            out_f.write(audio_bytes)
            chunk_count += 1
    assert chunk_count > 0

    audio = AudioSegment.from_mp3(processed_audio_path)
    logger.info(f"Streamed MP3 duration: {len(audio)/1000:.2f} seconds")

# pytest -v --log-cli-level=INFO tests/test_streaming.py::test_streaming


