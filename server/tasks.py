from celery import Celery
import io
import gc
import logging
from helpers.cache_helpers import (initiate_key, cache_audio_segment, cached_rss_url,
                                   change_status_to_complete)
from helpers.url_helpers import normalize_url, generate_cache_url, extract_source_url
from audio_processing import (fetch_audio_segment, process_audio, chunk_audio,
                              transcribe_audio, detect_ads, remove_ads, intro)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Create Celery instance
celery = Celery('podblock')
celery.config_from_object('config.Config', namespace='CELERY')


@celery.task
def process_urls_task(rss_urls):
    """Process audio urls from rss."""
    for rss_url in rss_urls:
        process_url_task.delay(rss_url)
    logger.info(f"Queued {len(rss_urls)} URLs for processing")


@celery.task(
    bind=True,
    queue='background',
    priority=1,
    max_retries=3
)
def process_url_task(self, rss_url):
    """Process audio from a single URL (Celery task)."""
    try:
        if not cached_rss_url(rss_url):  # Process only if not in cache
            source_url, audio_segment = fetch_audio_segment(rss_url)
            cache_url = generate_cache_url(rss_url, normalize_url(source_url))
            initiate_key(cache_url)

            process_audio(audio_segment, cache_url)
            return f"Processing complete for: {rss_url}"
        else:
            logger.info(f"{rss_url} is already in the cache. Skip process")
            return f"{rss_url} already cached"
    except Exception as e:
        logger.error(f"Unable to process audio from {rss_url}: {e}")
        self.retry(exc=e, countdown=60)  # Retry after 1 minute


@celery.task(
    bind=True,
    queue='stream',
    priority=0,
    max_retries=3
)
def process_stream_url_task(self, rss_url):
    """Process audio from a single URL for streaming."""
    try:
        if not cached_rss_url(rss_url): # Process only if not in cache
            source_url, audio_segment = fetch_audio_segment(rss_url)
            cache_url = generate_cache_url(url, normalize_url(source_url))
            initiate_key(cache_url),

            first_segment = audio_segment[120000:]
            second_segment = audio_segment[:120000]

            # Processing initial chunk of 2 minutes to ensure faster playback time.
            transcription = transcribe_audio(first_segment)
            ad_segments = detect_ads(transcription)
            new_audio = intro + remove_ads(first_segment, ad_segments)
            cache_audio_segment(cache_url, new_audio)

            logger.info(f'Processing complete for initial chunk: {rss_url}')
            # Processing remaining chunks
            process_audio(second_segment, cache_url)
            return (f"Processing complete for: {rss_url}")
        else:
            logger.info(f"{rss_url} is already in the cache. Skip process")
            return f"{rss_url} already cached"

    except Exception as e:
        logger.error(f"(Unable to process audio from {rss_url}: {e})")
        self.retry(exc=e, countdown=60)




