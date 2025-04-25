from celery import Celery
import io
import gc
import logging
from helpers.cache_helpers import (initiate_key, cached_url, cache_chunk, update_total_number_of_chunks)
from audio_processing import (fetch_audio, process_audio, chunk_audio,
                              transcribe_audio, detect_ads, remove_ads, intro)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Create Celery instance
celery = Celery('podblock')
celery.config_from_object('config.Config', namespace='CELERY')


@celery.task
def process_urls_task(urls):
    """
    Process audio urls from rss.
    """
    for url in urls:
        process_url_task.delay(url)
    logger.info(f"Queued {len(urls)} URLs for processing")


@celery.task(
    bind=True,
    queue='background',
    priority=1,
    max_retries=3
)
def process_url_task(self, url):
    """
    Process audio from a single URL (Celery task).
    """
    try:
        if not cached_url(url):  # Process only if not in cache
            audio = fetch_audio(url)
            initiate_key(url)
            process_audio(audio, url, False)
            return f"Processing complete for: {url}"
        else:
            logger.info(f"{url} is already in the cache. Skip process")
            return f"{url} already cached"
    except Exception as e:
        logger.error(f"Unable to process audio from {url}: {e}")
        self.retry(exc=e, countdown=60)  # Retry after 1 minute


@celery.task(
    bind=True,
    queue='stream',
    priority=0,
    max_retries=3
)
def initiate_streaming_task(self, url):
    """
    Process audio from a single URL for streaming.
    """
    try:
        audio = fetch_audio(url)
        first_segment = audio[:120000]
        second_segment = audio[120000:]

        # Processing initial chunk of 2 minutes to ensure faster playback time.
        transcription = transcribe_audio(first_segment)
        logger.info(f'Transcription complete for initial chunk: {url}')
        ad_segments = detect_ads(transcription)
        logger.info(f"Ad-analysis complete for initial chunk: {url}")
        processed_segment = intro + remove_ads(first_segment, ad_segments)
        cache_chunk(processed_segment, url)
        update_total_number_of_chunks(url, 1)
        logger.info(f'Processing complete for initial chunk: {url}')

        # Processing remaining chunks
        process_audio(second_segment, url, True)
        return f"Processing complete for: {url}"

    except Exception as e:
        logger.error(f"(Unable to process audio from {url}: {e})")
        self.retry(exc=e, countdown=60)
