from flask_caching import Cache

cache = Cache()


def setup_cache(app):
    """Sets up the cache configuration for the app."""
    cache.init_app(app)


def cache_audio(url, result_path, timeout=18000):
    """Cache the audio file after processing."""
    cache.set(url, result_path, timeout=timeout)