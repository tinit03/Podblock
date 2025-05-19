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
import logging

from dotenv import load_dotenv
from helpers.cache_helpers import cache_chunk, update_total_number_of_chunks, update_status_to_complete
from helpers.file_helpers import allowed_file, save_file, sanitize_filename
from helpers.audio_helpers import convert_audio_segment_to_bytes
from helpers.url_helpers import extract_name

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'wav', 'mp3', 'flac'}

load_dotenv("api.env")

# Initialize the whisper model
model = WhisperModel("base", device="cpu", compute_type="int8")
batched_model = BatchedInferencePipeline(model=model)

client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
intro = AudioSegment.from_file('resources/intro.mp3')


def chunk_audio(audio, chunk_duration_seconds=240, chunk_duration_ms=240000):
    """Splits an audio file into smaller chunks."""
    duration_seconds = audio.duration_seconds
    if duration_seconds <= chunk_duration_seconds:
        chunks = [audio]
    else:
        chunks = [audio[i:i + chunk_duration_ms] for i in range(0, len(audio), chunk_duration_ms)]
    return chunks


def transcribe_audio(audio_segment):
    try:
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
    except Exception as e:
        logger.error(e)


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


def remove_ads(audio, ad_segments, flag=None):
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
        if start <= 5000 and flag=="first":
            start = max(0, start - 1000)

        # Edge Case 2: Merge close ads
        if merged_ads and start - merged_ads[-1]["end"] <= 5000:
            merged_ads[-1]["end"] = max(merged_ads[-1]["end"], end)
        else:
            merged_ads.append({"start": start, "end": end})

    # Edge Case 3: Remove everything from the last ad if it's near the end
    if merged_ads and merged_ads[-1]["end"] >= total_duration - 10000 and flag=="last":
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


def fetch_audio(url):
    """
    Fetch audio from url.
    """
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            if extract_name(response.url) not in ALLOWED_EXTENSIONS:
                raise Exception(f"The requested file type is not allowed: {file_name}")
            buffer = io.BytesIO(response.content)
            audio_segment = AudioSegment.from_file(buffer, format="mp3")
            return audio_segment
        else:
            raise Exception(f"Failed to fetch file: {url}")
    except Exception as e:
        logger.error(f"Error fetching file: {e}")
        raise


def process_audio(audio_segment, url, streaming):
    """
        Process audio from url.
    """
    try:
        frame_rate = audio_segment.frame_rate
        chunks = chunk_audio(audio_segment)
        update_total_number_of_chunks(url, len(chunks))
        logger.info(f"Chunking complete: {url}")

        for i, chunk in enumerate(chunks):
            transcription = transcribe_audio(chunk)
            logger.info(f"Transcription complete for chunk {i + 1}/{len(chunks)}: {url}")

            ad_segments = detect_ads(transcription)
            logger.info(f"Ad-analysis complete for chunk {i+1}/{len(chunks)}: {url}")
            flag = None
            if i == 0:
                flag = "first"
            elif i == len(chunks) - 1:
                flag = "last"
            processed_chunk = remove_ads(chunk, ad_segments, flag=flag)
            logger.info(f"Processing complete for chunk {i+1}/{len(chunks)}: {url}")

            if i == 0 and not streaming:
                processed_chunk = intro + processed_chunk
            processed_chunk.set_frame_rate(frame_rate)

            cache_chunk(processed_chunk, url)
            logger.info(f"Caching complete for chunk {i + 1}/{len(chunks)}:{url}")

        update_status_to_complete(url)
        logger.info(f"Processing complete for {url}")

    except Exception as e:
        print(f"Error processing {url}: {e}")
        raise


def retrieve_timestamps(mp3, name):
    try:
        audio = AudioSegment.from_mp3(mp3)

        duration = audio.duration_seconds
        logger.info(f'Duration: {duration}')

        transcription = transcribe_audio(audio)
        logger.info(f"Transcription complete: {name}")

        added_segments = detect_ads(transcription)
        logger.info(f"Ad-analysis complete: {name}")
        return added_segments, duration

    except Exception as e:
        print(f"Error processing: {e}")
        raise
