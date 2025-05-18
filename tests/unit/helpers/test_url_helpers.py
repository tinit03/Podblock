from server.helpers.url_helpers import extract_name, extract_title, extract_extension

def test_extract_name():
    url = "https://example.com/podcast/audiofile.mp3"
    assert extract_name(url) == "mp3"

def test_extract_title():
    path = "episode001.mp3"
    assert extract_title(path) == "episode001"

def test_extract_extension():
    url = "https://example.com/audio.wav"
    assert extract_extension(url) == ".wav"
