import io
import logging
import time
import redis
from enums.status import AudioStatus
from helpers.audio_helpers import convert_audio_segment_to_bytes
from config import Config

redis_client = redis.Redis.from_url(Config.REDIS_URL)


def initiate_key(key):
    try:
        redis_client.hset(key, mapping={
            "status": "PROCESSING",
            "audio": "NULL"
        })
    except Exception as e:
        logging.error(f"Error initializing key in cache: {e}")


def cache_audio_segment(key, audio_segment):
    """Caching audio segment as raw bytes."""
    try:
        audio_bytes = convert_audio_segment_to_bytes(audio_segment)
        audio = redis_client.hget(key, "audio")
        if audio == b"NULL":
            logging.info('Adding first chunk to cache with size: ' + str(len(audio_bytes)))
            audio = audio_bytes
        else:
            logging.info('Adding another chunk to cache with size: ' + str(len(audio_bytes)))
            audio = audio + audio_bytes
        redis_client.hset(key, "audio", audio)
    except Exception as e:
        logging.error(f"Error: {e}")


def change_status_to_complete(key):
    """Changes the status of the audio segment saved in cache to complete"""
    redis_client.hset(key, "status", AudioStatus.Complete.value)


def change_status_to_processing(key):
    """Changes the status of the audio segment saved in cache to processing"""
    redis_client.hset(key, "status", AudioStatus.Processing.value)


def retrieve_audio_cache_key(key):
    """Retrieve audio bytes from cache with cache-key."""
    status = redis_client.hget(key, "status")
    audio_bytes = redis_client.hget(key, "audio")
    return status, audio_bytes


def retrieve_status_and_audio_source_url(source_url):
    """Retrieve status and audio from cache with source-url."""
    if cached_source_url(source_url):
        key = next(redis_client.scan_iter(f"*::{source_url}"))
        status = redis_client.hget(key, "status").decode("utf-8")
        audio_bytes = redis_client.hget(key, "audio")
        logging.info(f"Status: {status}")
        return status, audio_bytes
    else:
        logging.info(f"Audio does not exist in cache {source_url}")
        return None


def retrieve_status_source_url(source_url):
    """Retrieve status from cache with source-url."""
    if cached_source_url(source_url):
        key = next(redis_client.scan_iter(f"*::{source_url}"))
        status = redis_client.hget(key, "status").decode("utf-8")
        return status
    else:
        logging.info(f"Status does not exist in cache {source_url}")
        return None


def retrieve_audio_source_url(source_url):
    """Retrieve audio from cache with source-url."""
    if cached_source_url(source_url):
        key = next(redis_client.scan_iter(f"*::{source_url}"))
        audio_bytes = redis_client.hget(key, "audio")
        return audio_bytes
    else:
        logging.info(f"Audio does not exist in cache {source_url}")
        return None


def retrieve_status_and_audio_rss_url(rss_url):
    """Retrieve status and audio from cache with rss-url."""
    if cached_rss_url(rss_url):
        key = next(redis_client.scan_iter(f"{rss_url}::*"))
        status = redis_client.hget(key, "status").decode("utf-8")
        audio_bytes = redis_client.hget(key, "audio")
        logging.info(f"Status: {status}")
        return status, audio_bytes
    else:
        logging.info(f"Audio does not exist in cache {source_url}")
        return None


def retrieve_status_rss_url(rss_url):
    """Retrieve status from cache with rss-url."""
    if cached_rss_url(rss_url):
        key = next(redis_client.scan_iter(f"{rss_url}::*"))
        status = redis_client.hget(key, "status").decode("utf-8")
        return status
    else:
        logging.info(f"Status does not exist in cache {rss_url}")
        return None


def retrieve_audio_rss_url(rss_url):
    """Retrieve audio from cache with rss-url."""
    if cached_rss_url(rss_url):
        key = next(redis_client.scan_iter(f"{rss_url}::*"))
        audio_bytes = redis_client.hget(key, "audio")
        return audio_bytes
    else:
        logging.info(f"Audio does not exist in cache {rss_url}")
        return None


def poll_audio_beginning(source_url):
    logging.info(f"Poll audio")
    max_wait = 180
    interval = 30
    waited = 0

    status, audio_bytes = retrieve_status_and_audio_source_url(source_url)

    while audio_bytes == b'NULL' and waited < max_wait:
        time.sleep(interval)
        waited += interval
        status, audio_bytes = retrieve_status_and_audio_source_url(source_url)

    return status, audio_bytes


def poll_and_stream_audio(source_url):
    """Polling and streaming audio from cache"""
    logging.info(f"Polling and streaming from cache: {source_url}")
    interval = 15

    status, audio_bytes = retrieve_status_and_audio_source_url(source_url)

    if audio_bytes == b'NULL':
        logging.info(f"Audio is not processed, polling the beginning")
        status, audio_bytes = poll_audio_beginning(source_url)
        logging.info(f"FIRST BYTES ARE STREAMING")
        logging.info(f"Status: {status}")

    previous_offset = len(audio_bytes)
    yield audio_bytes

    while status == "PROCESSING":
        logging.info(f"Waiting for NEXT BYTES")
        time.sleep(interval)

        status, audio_bytes = retrieve_status_and_audio_source_url(source_url)
        current_offset = len(audio_bytes)
        logging.info(f"Previous offset: {previous_offset}| Current offset: {current_offset}")

        if current_offset > previous_offset:
            logging.info(f"NEW BYTES ARE STREAMING: {source_url}")
            yield audio_bytes[previous_offset:current_offset]
            previous_offset = len(audio_bytes)

    if status == "COMPLETE":
        logging.info(f"Caching complete, ensuring that the last part is included")
        status, audio_bytes = retrieve_status_and_audio_source_url(source_url)
        current_offset = len(audio_bytes)
        if current_offset > previous_offset:
            yield audio_bytes[previous_offset:current_offset]


def download_audio_cache_key(file_path, cache_key):
    """Retrieve and download audio from cache with cache-key"""
    status, audio_bytes = retrieve_audio_cache_key(cache_key)
    if audio_bytes:
        with open(file_path, "wb") as audio_file:
            audio_file.write(audio_bytes)
            logging.info(f"Audio with size {len(audio_bytes)} saved to {file_path}")
    else:
        logging.info(f"No audio file found for this {cache_key}")


def cached_rss_url(rss_url):
    """Checking if rss-url exists in cache, returning true or false"""
    return any(redis_client.scan_iter(f"{rss_url}::*"))


def cached_source_url(source_url):
    """Checking if source-url exists in cache, returning true or false"""
    return any(redis_client.scan_iter(f"*::{source_url}")) or redis_client.get(f"{source_url}")


