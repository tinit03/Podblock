from pydub import AudioSegment
import os
from faster_whisper import WhisperModel, BatchedInferencePipeline
from urllib.parse import urlparse, unquote
import openai
import re
from dotenv import load_dotenv
from cache_helpers import cache, cache_audio
from file_helpers import allowed_file, save_file
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'flac'}
def extract_mp3_name(url):
    """Extracts the MP3 filename from the given URL."""
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)  # Extracts "NPR3418472865.mp3"
    return unquote(filename)  # Decode any URL-encoded characters

load_dotenv("api.env")
# Initialize the whisper model
model = WhisperModel("tiny", device="cpu", compute_type="int8")
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
    try:
        audio = AudioSegment.from_file(audio_name)  # Access the audio
        duration = audio.duration_seconds
        if duration < 360:  # Less than 6 minutes (360 seconds)
            print("Audio file is less than 6 minutes, skipping chunking.")
            chunk_files = [(audio_name, duration)]  # No chunking, just use the original file
        else:
            # Split the audio file into chunks if it's longer than 6
            chunk_files = chunk_audio(audio_name)
        total_duration = 0  # This variable is used to track the total duration of the chunks
        all_transcriptions = []

        for i, (chunk, chunk_duration) in enumerate(chunk_files):
            print(f"[INFO] Processing chunk {i+1}/{len(chunk_files)} - Duration: {chunk_duration:.2f} seconds")

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
            print(f"[INFO] Finished transcribing chunk {i+1}/{len(chunk_files)}")

            total_duration += chunk_duration

        print(f"[INFO] Transcription complete for {audio_name}")
        return "\n".join(all_transcriptions)
    except Exception as e:
        return str(e)


def detect_ads(words):
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
                    "content": f"Here is the transcription with word-level timestamps:\n{words}"
                }
            ]
        )
    ad_segments = []
    classification = completion.choices[0].message.content.strip()

    print(classification)
    pattern = r"start:\s*([\d.]+).*?end:\s*([\d.]+).*?summary:\s*['\"]?([^'\"]+)['\"]?"
    ad_segments = [{"start": float(m[0]), "end": float(m[1]), "summary": m[2].strip()} for m in
                   re.findall(pattern, classification)]
    print(ad_segments)
    if ad_segments:
        return ad_segments
    else:
        return {
            "ad_detection": "No ad detected"
        }


def cut_out_ads(audio_name, ad_segments):
    """Removes ad segments from the audio file with optimized processing."""
    if not ad_segments:
        print("There are no ads.")
        return audio_name

    # Load the original audio file
    audio = AudioSegment.from_file(audio_name)
    total_duration = len(audio)  # Get total duration in milliseconds
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

    # Extract non-ad sections
    previous_end = 0
    non_ad_sections = [audio[previous_end:start] for start, end in [(ad["start"], ad["end"]) for ad in merged_ads] if
                       start > previous_end]

    # Add remaining audio after last ad
    if merged_ads and merged_ads[-1]["end"] < total_duration:
        non_ad_sections.append(audio[merged_ads[-1]["end"]:])

    # Concatenate non-ad sections
    new_audio = sum(non_ad_sections, AudioSegment.silent(duration=0))  # Avoids sum([]) error

    # Save the new audio file
    new_audio_path = f"{audio_name}_no_ads.mp3"
    new_audio.export(new_audio_path, format="mp3")
    os.remove(audio_name)
    return new_audio_path


def process_urls_in_background(urls):
    """Runs the URL processing in the background."""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        for url in urls:
            if not cache.get(url):  # Process only if not in cache
                executor.submit(process_audio_from_url, url)
def process_audio_from_url(url):
    """Download and process an audio file if not already cached."""
    if cache.get(url):  # Skip if already processed
        print(f"Skipping {url}, already in cache.")
        return
    try:
        print("I REACHED HERE")
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            print(f"Failed to download {url}")
            return
        filename = extract_mp3_name(url)  # Extract filename from URL
        if not allowed_file(filename, ALLOWED_EXTENSIONS):
            print(f"File format not allowed: {filename}")
            return
        file_path = save_file(filename, './uploads')
        print(f"File saved at: {file_path}")
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        transcription = transcribe(file_path)
        ad_segments = detect_ads(transcription)
        result = cut_out_ads(file_path, ad_segments)
        cache_audio(url, result)  # Store processed file in cache
        print(f"Processing complete for {url}")

    except Exception as e:
        print(f"Error processing {url}: {str(e)}")