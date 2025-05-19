import os
from server.helpers.file_helpers import allowed_file, sanitize_filename, save_file

def test_allowed_file():
    assert allowed_file("test.mp3", {"mp3", "wav"}) is True
    assert allowed_file("test.txt", {"mp3", "wav"}) is False

def test_sanitize_filename():
    unsafe = 'file<name>|wrong?.mp3'
    safe = sanitize_filename(unsafe)
    assert safe == 'file_name__wrong_.mp3'

def test_save_file(tmp_path):
    path = save_file("audio.mp3", str(tmp_path))
    assert path == os.path.join(str(tmp_path), "audio.mp3")
