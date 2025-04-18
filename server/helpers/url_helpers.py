from urllib.parse import urlparse, unquote, urlunparse
import os


def normalize_url(url):
    return url.split(".mp3")[0] + ".mp3"


def generate_cache_url(rss_url, source_url):
    return f"{rss_url}::{source_url}"


def extract_rss_url(cache_url):
    """Retrieve the rss-url from the cache-url."""
    return cache_url.split("::")[0]


def extract_source_url(cache_url):
    """Retrieve the source-url from the cache-url"""
    return cache_url.split("::")[1]


def extract_name(url):
    """Extracts the filename from the given URL."""
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)  # Extracts "NPR3418472865.mp3"
    file_extension = os.path.splitext(filename)[1][1:].lower()  # Extract extension, remove dot
    return file_extension  # Return only "mp3", "wav", etc.


def extract_title(path):
    """Extracts the title from the directory path."""
    base, ext = os.path.splitext(path)
    return base


def extract_extension(url):
    """Extracts the extension from the given URL."""
    return os.path.splitext(url)[1].lower()


