import io
from io import BytesIO


def convert_audio_segment_to_bytes(audio_segment):
    buffer = io.BytesIO()
    audio_segment.export(buffer, format="mp3", parameters=["-write_xing", "0", "-id3v2_version", "0"])
    buffer.seek(0)
    return buffer.read()
