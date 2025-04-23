import concurrent.futures
import io
import threading
from io import BytesIO
import gc
import requests
from pydub import AudioSegment
import os
from faster_whisper import WhisperModel, BatchedInferencePipeline
from urllib.parse import urlparse, unquote
import openai
import re
from dotenv import load_dotenv
from helpers.cache_helpers import (initiate_key, cache_audio_segment, cached_rss_url, cached_source_url,
                                   change_status_to_complete, download_audio_cache_key)
from helpers.file_helpers import allowed_file, save_file, sanitize_filename
from helpers.audio_helpers import convert_audio_segment_to_bytes
import logging
from helpers.url_helpers import normalize_url, generate_cache_url, extract_name, extract_title, extract_source_url

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'wav', 'mp3', 'flac'}


load_dotenv("api.env")
# Initialize the whisper model
model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
batched_model = BatchedInferencePipeline(model=model)
client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
intro = AudioSegment.from_file('resources/intro.mp3')


def chunk_audio(audio_segment, chunk_duration_seconds=240, chunk_duration_ms=240000):
    """Splits an audio file into smaller chunks."""
    audio = audio_segment
    duration_seconds = audio.duration_seconds

    if duration_seconds <= chunk_duration_seconds:
        chunks = [(audio, duration_seconds)]
    else:
        chunks = [audio[i:i + chunk_duration_ms] for i in range(0, len(audio), chunk_duration_ms)]

    return chunks, chunk_duration_seconds


def transcribe_audio(audio_segment):
    buffer = BytesIO()
    audio_segment.export(buffer, format="wav")
    buffer.seek(0)
    segments, _ = batched_model.transcribe(buffer, word_timestamps=True)
    # Extract word-level timestamps
    transcription = [
        {
            "start": word.start,
            "end": word.end,
            "text": word.word
        }
        for segment in segments
        for word in segment.words
    ]
    # Format the data to send to ChatGPT
    formatted_transcription = "\n".join(
        [f"[{w['start']}-{w['end']}] {w['text']}" for w in transcription]
    )
    return formatted_transcription


def detect_ads(transcript):
    logger.info('Trying to detect ads')
    try:
        completion = \
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a system that detects ads in audio transcriptions. "
                                   "Based on the word-level timestamps provided, determine the start and end times of any ad segments. "
                                   "For each ad segment, provide a 5-word summary of the ad. "
                                   "Provide ad segments in the format: start: <time>, end: <time>, summary: '<summary>'. "
                                   "If no ad is found, return 'No ad detected.'"
                    },
                    {
                        "role": "user",
                        "content": f"Here is the transcription with word-level timestamps:\n{transcript}"
                    }
                ]
            )

        classification = completion.choices[0].message.content.strip()
        logger.info(classification)
        pattern = r"start:\s*([\d.]+).*?end:\s*([\d.]+).*?summary:\s*['\"]?([^'\"]+)['\"]?"
        ad_segments = [{"start": float(m[0]), "end": float(m[1]), "summary": m[2].strip()} for m in
                       re.findall(pattern, classification)]
        logger.info(f"Detected ad-segments: {ad_segments}")
        return ad_segments

    except Exception as e:
        logger.error("Error in detect_ads (attempt %d/%d): %s", attempt + 1, retries, str(e))
        raise


def remove_ads(audio, ad_segments):
    """Removes ad segments from the audio file with optimized processing."""
    if not ad_segments:
        print("No ads to remove.")
        return audio

    total_duration = len(audio)

    # Ensure ad segments are sorted
    ad_segments.sort(key=lambda x: x["start"])

    # Merge close ad segments (≤ 5 seconds apart)
    merged_ads = []
    for segment in ad_segments:
        start, end = segment["start"] * 1000, segment["end"] * 1000  # Convert to milliseconds

        # Edge Case 1: Adjust ads in the first 5 seconds
        if start <= 5000:
            start = max(0, start - 1000)

        # Edge Case 2: Merge close ads
        if merged_ads and start - merged_ads[-1]["end"] <= 5000:
            merged_ads[-1]["end"] = max(merged_ads[-1]["end"], end)
        else:
            merged_ads.append({"start": start, "end": end})

    # Edge Case 3: Remove everything from the last ad if it's near the end
    if merged_ads and merged_ads[-1]["end"] >= total_duration - 10000:
        merged_ads[-1]["end"] = total_duration

    # Extract non-ad sections with proper updating of previous_end
    non_ad_sections = []
    previous_end = 0
    for ad in merged_ads:
        start, end = ad["start"], ad["end"]
        if start > previous_end:
            non_ad_sections.append(audio[previous_end:start])
        previous_end = end

    # Add remaining audio after last ad if any
    if previous_end < total_duration:
        non_ad_sections.append(audio[previous_end:])

    # Concatenate non-ad sections
    new_audio = AudioSegment.empty()
    for segment in non_ad_sections:
        new_audio += segment  # Avoids sum([]) error

    return new_audio


def fetch_audio_segment(url):
    """
    Fetch audiofile (mp3) from rss-url.
    Returns audio-segment and source-url.
    """
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            if extract_name(url) not in ALLOWED_EXTENSIONS:
                raise Exception(f"The requested file type is not allowed: {file_name}")
            source_url = response.url
            buffer = io.BytesIO(response.content)
            audio_segment = AudioSegment.from_file(buffer, format="mp3")
            return source_url, audio_segment
        else:
            raise Exception(f"Failed to fetch file: {url}")
    except Exception as e:
        logger.error(f"Error fetching file: {e}")
        raise


def fetch_audio_bytes(url):
    """
    Fetch audio from rss-url.
    :param url: rss-url
    :return: audio bytes
    """
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            if extract_name(url) not in ALLOWED_EXTENSIONS:
                raise Exception(f"The requested file type is not allowed: {file_name}")
            return response.content
        else:
            raise Exception(f"Failed to fetch file: {url}")
    except Exception as e:
        logger.error(f"Error fetching file: {e}")
        raise


def process_audio(audio_segment, cache_url):
    """Download and process an audio file."""
    source_url = extract_source_url(cache_url)
    try:
        frame_rate = audio_segment.frame_rate
        chunks, chunk_duration = chunk_audio(audio_segment)
        logger.info(f"Chunking complete: {source_url}")

        for i,  chunk in enumerate(chunks):
            transcription = transcribe_audio(chunk)
            logger.info(f"Transcription complete for chunk {i+1}/{len(chunks)}: {source_url}")

            ad_segments = detect_ads(transcription)
            logger.info(f"Ad-analysis complete for chunk {i+1}/{len(chunks)}: {source_url}")

            processed_chunk = remove_ads(chunk, ad_segments)
            logger.info(f"Processing complete for chunk {i+1}/{len(chunks)}: {source_url}")

            if i == 0:
                processed_chunk = intro + processed_chunk
            processed_chunk.set_frame_rate(frame_rate)

            cache_audio_segment(cache_url, processed_chunk)
            logger.info(f"Caching complete for chunk {i + 1}/{len(chunks)}:{source_url}")

        change_status_to_complete(cache_url)
        logger.info(f"Processing complete for {source_url}")

    except Exception as e:
        print(f"Error processing {source_url}: {str(e)}")
        raise


