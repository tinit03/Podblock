import io
import logging
import time
import redis
from enums.status import AudioStatus
from helpers.audio_helpers import convert_audio_segment_to_bytes
from config import Config

r = redis.Redis.from_url(Config.REDIS_URL)


def initiate_key(key):
    """
        Initiates key in cache
    """
    meta_key = f'meta::{key}'
    lock_key = f'lock::{key}'

    lock = r.lock(lock_key, timeout=60)
    try:
        if not lock.acquire(blocking=False):
            logging.info(f"Key {key} is already being initialized")
            return False

        logging.info('No lock! Initiating key.')
        r.hset(meta_key, mapping={
            "status": AudioStatus.Processing.value,
            "chunks": 0
        })
        return True
    except Exception as e:
        logging.error(f"Error initializing key in cache for {key}: {e}")


def update_total_number_of_chunks(key, chunks):
    """
        Changes total number of chunks for key in cache
    """
    meta_key = f'meta::{key}'
    try:
        r.hincrby(meta_key, "total_chunks", chunks)
    except Exception as e:
        logging.error(f"Error updating total number of chunks for {key}: {e}")
        raise


def update_status_to_complete(key):
    """
        Changes the status to complete for key in cache
    """
    meta_key = f'meta::{key}'
    try:
        r.hset(meta_key, "status", AudioStatus.Complete.value)
    except Exception as e:
        logging.error(f"Error updating status to complete for {key}: {e}")
        raise


def retrieve_total_number_of_chunks(key):
    """
        Retrieves total number of chunks for key in cache
    """
    meta_key = f'meta::{key}'
    try:
        return r.hget(meta_key, "chunks")
    except Exeption as e:
        logging.error(f"Error retrieving total number of chunks for {key}: {e}")
        raise


def retrieve_status(key):
    """
        Retrieves status for key in cache
    """
    try:
        status = r.hget(f'meta::{key}', "status")
        if status is not None:
            return status.decode("utf-8")
        return None
    except Exeption as e:
        logging.error(f"Error retrieving status for {key}: {e}")
        raise


def cache_chunk(audio, key):
    """
        Caching audio segment as raw bytes.
    """
    try:
        bytes = convert_audio_segment_to_bytes(audio)
        r.xadd(f'stream::{key}', fields={"audio": bytes})
    except Exception as e:
        logging.error(f"Error saving chunk to cache for {key}: {e}")
        raise


def retrieve_audio(key):
    """
        Retrieve audio bytes from cache with cache-key.
    """
    try:
        logging.info('Retrieving audio from cache!')
        status = retrieve_status(key)
        total_chunks = retrieve_total_number_of_chunks(key)
        if status == AudioStatus.Complete.value:
            logging.info("Audio is complete. Streaming complete audio.")
            return retrieve_complete_audio(key, total_chunks)

        if status == AudioStatus.Processing.value:
            logging.info("Audio is processing. Streaming audio while processing.")
            return retrieve_processing_audio(key, total_chunks)

    except Exception as e:
        logging.error(f"Error retrieving audio for {key}: {e}")


def retrieve_complete_audio(key, total_chunks):
    """
        Retrieve and assemble all audio chunks for complete.
    """
    stream_key = f'stream::{key}'
    try:
        entries = r.xrange(stream_key, min='-', max='+')
        total_entries = len(entries)

        if total_entries != total_chunks:
            logging.error(f"Chunk count mismatch for: {key}")
            raise RuntimeError(f"Expected {total_chunks} chunks but found {num_entries}.")
        chunks = [
            fields.get(b'audio') or fields.get('audio')
            for _, fields in entries
        ]
        audio_bytes = b"".join(filter(None, chunks))
        return audio_bytes
    except Exception as e:
        logging.error(f"Error retrieving complete audio for {key}: {e}")
        raise


def retrieve_processing_audio(key, total_chunks, yielded = 0, last_id = '0-0'):
    """
        Retrieve and assemble all audio chunks for complete.
    """
    stream_key = f'stream::{key}'
    try:
        while yielded < total_chunks:
            resp = r.xread(
                streams={stream_key: last_id},
                block=10000,
                count=1
            )
            if entry:
                _, messages = resp[0]
                msg_id, fields = messages[0]
                last_id = msg_id
                chunk = fields.get(b"audio") or fields.get("audio")
                if chunk:
                    yield chunk
                    yielded += 1
    except Exception as e:
        logging.error(f"Error streaming audio for {key}: {e}")
        raise


def cached_url(key: str) -> bool:
    """
        Retrieve and assemble all audio chunks for complete.
    """
    meta_key = f'meta::{key}'
    try:
        return r.exists(meta_key) > 0
    except Exception as e:
        logging.error(f"Error checking cached audio for {key}: {e}")
        raise

