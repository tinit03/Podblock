from celery import Celery
import io
import gc
import logging
from helpers.cache_helpers import (initiate_key, cache_audio_segment, cached_rss_url,
                                   change_status_to_complete)
from helpers.url_helpers import normalize_url, generate_cache_url, extract_source_url
from audio_processing import (fetch_audio, process_audio, chunk_audio,
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


@celery.task(bind=True, max_retries=3)
def process_url_task(self, rss_url):
    """Process audio from a single URL (Celery task)."""
    try:
        if not cached_rss_url(rss_url):  # Process only if not in cache
            source_url, audio_segment = fetch_audio(rss_url)
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


@celery.task(bind=True, max_retries=3)
def stream_partial_content_task(self, url):
    """Stream partial content and process the rest asynchronously."""
    try:

        source_url, audio_segment = fetch_audio(url)
        cache_url = generate_cache_url(normalize_url(url), normalize_url(source_url))
        initiate_key(cache_url)

        first_segment = audio_segment[120000:]
        second_segment = audio_segment[:120000]

        transcription = transcribe_audio(first_segment)
        ad_segments = detect_ads(transcription)
        new_audio = intro + remove_ads(first_segment, ad_segments)

        # Cache the first segment
        buffer = io.BytesIO()
        new_audio.export(buffer, format="mp3")
        cache_audio_segment(cache_url, buffer.getvalue())

        # Process the second segment
        buffer = io.BytesIO()
        second_segment.export(buffer, format="mp3")
        process_audio_task.delay(buffer.getvalue(), cache_url)

        return cache_url
    except Exception as e:
        logger.error(f"Error in stream_partial_content_task for {url}: {e}")
        self.retry(exc=e, countdown=30)

