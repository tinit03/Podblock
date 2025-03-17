import logging
from flask_caching import Cache

cache = Cache()
redis_client = None


def setup_cache(app, redis_instance):
    """Sets up the cache configuration for the app."""
    global redis_client
    redis_client = redis_instance
    cache.init_app(app)


def initiate_key(key):
    try:
        redis_client.set(key, "INIT")
    except Exception as e:
        logging.error(f"Error initializing key in cache: {e}")


def cache_audio(key, result_path):
    """Cache the audio file after processing."""
    logging.info(f"Cache path: {result_path}")
    redis_client.set(key, result_path)


def retrieve_audio(source_url):
    """Retrieve the audio from cache."""
    if cached_source_url(source_url):
        key = next(redis_client.scan_iter(f"*::{source_url}"))
        logging.info(f"Value: {redis_client.get(key)}")
        return redis_client.get(key)
    else:
        logging.info(f"Audio does not exist in cache {source_url}")
        return None


def cached_rss_url(rss_url):
    return any(redis_client.scan_iter(f"{rss_url}::*"))


def cached_source_url(source_url):
    return any(redis_client.scan_iter(f"*::{source_url}"))

