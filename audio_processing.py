import concurrent.futures
from io import BytesIO

import requests
from pydub import AudioSegment
import os
from faster_whisper import WhisperModel, BatchedInferencePipeline
from urllib.parse import urlparse, unquote
import openai
import re
from dotenv import load_dotenv
from helpers.cache_helpers import cache, initiate_key, cache_audio, cached_rss_url, cached_source_url
from helpers.file_helpers import allowed_file, save_file, sanitize_filename
import logging
from helpers.url_helpers import normalize_url, generate_cache_url, extract_name, extract_title

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'wav', 'mp3', 'flac'}


load_dotenv("api.env")
# Initialize the whisper model
model = WhisperModel("small.en", device="cpu", compute_type="int8")
batched_model = BatchedInferencePipeline(model=model)
api_key = os.getenv('OPENAI_API_KEY')
client = openai.OpenAI(api_key=api_key)


def chunk_audio(file_path, chunk_length_ms=360000):
    """Splits an audio file into smaller chunks."""
    audio = AudioSegment.from_file(file_path)
    chunks = [(audio[i:i + chunk_length_ms], len(audio[i:i + chunk_length_ms]) / 1000)
              for i in range(0, len(audio), chunk_length_ms)]
    return chunks  # Returns chunks in memory instead of saving files


def transcribe(audio_name):
    audio = AudioSegment.from_file(audio_name)  # Access the audio
    duration = audio.duration_seconds
    if duration < 360:  # Less than 6 minutes (360 seconds)
        logger.info("Audio file is less than 6 minutes, skipping chunking.")
        chunk_files = [(audio_name, duration)]  # No chunking, just use the original file
    else:
        # Split the audio file into chunks if it's longer than 6
        chunk_files = chunk_audio(audio_name)
    total_duration = 0  # This variable is used to track the total duration of the chunks
    all_transcriptions = []

    for i, (chunk, chunk_duration) in enumerate(chunk_files):
        logger.info(f"[INFO] Processing chunk {i+1}/{len(chunk_files)} - Duration: {chunk_duration:.2f} seconds")

        buffer = BytesIO()
        chunk.export(buffer, format="mp3")
        buffer.seek(0)
        segments, _ = batched_model.transcribe(buffer, word_timestamps=True, batch_size=8)
        # Extract word-level timestamps
        word_timestamps = [
            {
                "start": word.start + total_duration,
                "end": word.end + total_duration,
                "text": word.word
            }
            for segment in segments
            for word in segment.words
        ]
        # Format the data to send to ChatGPT
        words_with_timestamps = "\n".join(
            [f"[{w['start']}-{w['end']}] {w['text']}" for w in word_timestamps]
        )
        all_transcriptions.append(words_with_timestamps)
        logger.info(f"[INFO] Finished transcribing chunk {i+1}/{len(chunk_files)}")

        total_duration += chunk_duration

    logger.info(f"[INFO] Transcription complete for {audio_name}")
    return "\n".join(all_transcriptions)


def detect_ads(transcript):

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
        logger.info(ad_segments)
        return ad_segments

    except Expeception as e:
        logger.error("Error in detect_ads (attempt %d/%d): %s", attempt + 1, retries, str(e))
        raise


def remove_ads(file_path, ad_segments):
    """Removes ad segments from the audio file with optimized processing."""
    if not ad_segments:
        print("There are no ads.")
        return file_path

    # Load the original audio file
    audio = AudioSegment.from_file(file_path)
    total_duration = len(audio)  # Get total duration in milliseconds
    logger.error(total_duration)
    logger.error(audio.frame_rate)

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

    duration = len(new_audio)
    logger.error(duration)

    new_audio = new_audio.set_frame_rate(audio.frame_rate)
    # Save the new audio file
    file_title = extract_title(file_path)
    new_audio_path = f"{file_title}_no_ads.mp3"
    new_audio.export(new_audio_path, format="mp3")
    return new_audio_path


def process_urls_in_background(rss_urls):
    """Runs the URL processing in the background."""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        for rss_url in rss_urls:
            if not cached_rss_url(rss_url[1]):  # Process only if not in cache
                source_url, file_path = fetch_and_save_audio(rss_url[0],rss_url[1])
                if source_url and file_path:
                    cache_url = generate_cache_url(rss_url[1], normalize_url(source_url))
                    initiate_key(cache_url)
                    executor.submit(process_audio_from_file, file_path, cache_url)
                else:
                    logger.error(f"Unable to process audio from {rss_url}")
            else:
                logger.info(f"{rss_url} is already in the cache. Skip process")


def fetch_and_save_audio(title, url):
    """Fetch and save audiofile from url."""
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            file_name = sanitize_filename(title.replace(" ", "_")) + ".mp3"
            if extract_name(url) not in ALLOWED_EXTENSIONS:
                logger.error(f"File format not allowed: {file_name}")
                return None, None
            file_path = save_file(file_name, './uploads')
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            source_url = response.url
            logger.info(f"Original audio saved as {file_path}")
            return source_url, file_path
        else:
            logger.error(f"Failed to fetch file: {url}")
            return None, None
    except Exception as e:
        logger.error(f"Error fetching file: {e}")


def process_audio_from_file(file_path, cache_url):
    """Download and process an audio file."""
    try:
        logger.info(f"Started processing audio {file_path}")

        transcription = transcribe(file_path)    # Transcribe audio
        logger.info(f"Transcription complete {file_path}")

        ad_segments = detect_ads(transcription)   # Detect ads in transcription
        logger.info(f"Ad-analysis complete {file_path}")
        result = remove_ads(file_path, ad_segments)  # Cut ads from audio
        logger.info(f"Ad-removal complete {file_path}")

        cache_audio(cache_url, result)  # Store processed file in cache

        logger.info(f"Processing complete for {cache_url}")

    except Exception as e:
        print(f"Error processing {cache_url}: {str(e)}")