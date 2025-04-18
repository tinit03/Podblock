from server.helpers.url_helpers import (
    normalize_url, generate_cache_url,
    extract_name, extract_title, extract_extension
)


def test_normalize_url():
    """Ensures that URLs are normalized to end with .mp3."""
    assert normalize_url("https://example.com/audio.mp3?param=value") == "https://example.com/audio.mp3"


def test_generate_cache_url():
    """Tests that the cache URL is generated correctly."""
    assert generate_cache_url("rss_url", "source_url") == "rss_url::source_url"


def test_extract_name():
    """Tests that the file extension is extracted correctly from the URL."""
    assert extract_name("https://example.com/audio.mp3") == "mp3"
    assert extract_name("https://example.com/path/to/song.wav") == "wav"
    assert extract_name("https://example.com/no-extension") == ""


def test_extract_title():
    """Tests that the title (filename without extension) is correctly extracted."""
    assert extract_title("./uploads/audio.mp3") == "./uploads/audio"
    assert extract_title("./uploads/song.wav") == "./uploads/song"
    assert extract_title("./uploads/no-extension") == "./uploads/no-extension"


def test_extract_extension():
    """Tests that the file extension is extracted correctly."""
    assert extract_extension("https://example.com/audio.mp3") == ".mp3"
    assert extract_extension("https://example.com/song.WAV") == ".wav"
    assert extract_extension("https://example.com/no-extension") == ""