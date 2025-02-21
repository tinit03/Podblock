from pydub import AudioSegment
import os
from faster_whisper import WhisperModel, BatchedInferencePipeline
import openai
import re
from dotenv import load_dotenv

load_dotenv("api.env")
# Initialize the whisper model
model = WhisperModel("small", device="cpu", compute_type="int8")
batched_model = BatchedInferencePipeline(model=model)
api_key = os.getenv('OPENAI_API_KEY')
client = openai.OpenAI(api_key=api_key)


def chunk_audio(file_path, chunk_length_ms=240000):
    """Splits an audio file into smaller chunks."""
    audio = AudioSegment.from_file(file_path)
    chunks = [audio[i:i + chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)]
    chunk_files = []
    for idx, chunk in enumerate(chunks):
        chunk_filename = f"{file_path}_chunk_{idx}.mp3"
        chunk.export(chunk_filename, format="mp3")
        chunk_files.append(chunk_filename)
    return chunk_files


def transcribe(audio_name):
    try:
        audio = AudioSegment.from_file(audio_name)  # Access the audio
        duration = audio.duration_seconds
        if duration < 240:  # Less than 4 minutes (240 seconds)
            print("Audio file is less than 4 minutes, skipping chunking.")
            chunk_files = [audio_name]  # No chunking, just use the original file
        else:
            # Split the audio file into chunks if it's longer than 4 minutes
            chunk_files = chunk_audio(audio_name)
        total_duration = 0  # This variable is used to track the total duration of the chunks


        for chunk_file in chunk_files:
            segments, _ = batched_model.transcribe(chunk_file, word_timestamps=True, batch_size=8)

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
            total_duration += AudioSegment.from_file(chunk_file).duration_seconds

            for segment in segments:
                print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))
            # Format the data to send to ChatGPT
            words_with_timestamps = "\n".join(
                [f"[{w['start']}-{w['end']}] {w['text']}" for w in word_timestamps]
            )
            return words_with_timestamps
    except Exception as e:
        return e


def detect_ads(words):
    completion = \
        client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a system that detects ads in audio transcriptions. Based on the word-level timestamps provided, determine the start and end times of any ad segments. For each ad segment, provide a 5-word summary of the ad. Return the start and end times for each ad segment in this format start:,end:.(e.g., start: 13.12, end:13.2), followed by a 5-word summary (e.g. summary:'Ad about buying light food'). If no ad is found, return 'No ad detected.'"
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
    matches = re.findall(pattern, classification, re.DOTALL)

    for match in matches:
        try:
            start = float(match[0])  # Extract start time
            end = float(match[1])  # Extract end time
            summary = match[2].strip()  # Extract summary text

            segment = {"start": start, "end": end, "summary": summary}
            ad_segments.append(segment)
        except ValueError:
            continue  # Skip if extraction fails

    print(ad_segments)
    if ad_segments:
        return ad_segments
    else:
        return {
            "ad_detection": "No ad detected"
        }


def cut_out_ads(audio_name, ad_segments):
    """Removes ad segments from the audio file with special handling for edge cases."""
    # Load the original audio file
    audio = AudioSegment.from_file(audio_name)
    total_duration = len(audio)  # Get total duration in milliseconds

    # Sort ad segments by start time
    ad_segments = sorted(ad_segments, key=lambda x: x["start"])

    # Initialize a list to hold the non-ad sections
    non_ad_sections = []
    previous_end = 0

    # Process each ad segment with special handling
    adjusted_ad_segments = []
    for i, segment in enumerate(ad_segments):
        start, end = segment["start"] * 1000, segment["end"] * 1000  # Convert to milliseconds

        # **Edge Case 1: Remove an extra 1 second for ads in the first 5 seconds**
        if start <= 5000:
            start = max(0, start - 1000)  # Ensure start is not negative

        # **Edge Case 2: Merge close ad segments (less than 5 seconds apart)**
        if i > 0:
            prev_end = adjusted_ad_segments[-1]["end"]  # End of the last processed ad
            if start - prev_end <= 5000:  # If the gap is ≤ 5 seconds, merge them
                adjusted_ad_segments[-1]["end"] = max(end,
                                                      prev_end)  # Extend the last segment instead of adding a new one
                continue

        # **Edge Case 3: Remove everything to the end if ad is near the end**
        if end >= total_duration - 10000:  # If the ad ends in the last 10 seconds
            adjusted_ad_segments.append({"start": start, "end": total_duration})
            break

        adjusted_ad_segments.append({"start": start, "end": end})

    # Iterate through adjusted ad segments and remove them
    for segment in adjusted_ad_segments:
        start, end = segment["start"], segment["end"]

        # Extract the part of the audio before the ad
        if start > previous_end:
            non_ad_sections.append(audio[previous_end:start])

        # Update the previous end to be after the ad
        previous_end = end

    # Add any remaining audio after the last ad
    if previous_end < total_duration:
        non_ad_sections.append(audio[previous_end:])

    # Concatenate the non-ad sections together
    new_audio = sum(non_ad_sections)

    # Save the new audio without the ads
    new_audio_path = f"{audio_name}_no_ads.mp3"
    new_audio.export(new_audio_path, format="mp3")
    os.remove(audio_name)
    return new_audio_path
