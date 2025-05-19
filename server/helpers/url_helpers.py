from urllib.parse import urlparse, unquote, urlunparse
import os


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


