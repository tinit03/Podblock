from flask_caching import Cache

cache = Cache()


def setup_cache(app):
    """Sets up the cache configuration for the app."""
    cache.init_app(app)


def cache_audio(filename):
    """Cache the audio file after processing."""
    cache.add(filename)
