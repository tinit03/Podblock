import os
import re
import logging
import json

import time
import openai
import pytest
import textwrap

from pathlib import Path
from dotenv import load_dotenv
from time import perf_counter
from io import BytesIO

from pydub import AudioSegment
from faster_whisper import WhisperModel, BatchedInferencePipeline

env_path = Path(__file__).parents[2] / "api.env"
load_dotenv(dotenv_path=env_path)

client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

NORWEGIAN_AUDIO_PATH = Path(__file__).parent / "resources" / "norwegian.mp3"
ENGLISH_AUDIO_PATH = Path(__file__).parent / "resources" / "english.mp3"

WHISPER_MODELS = ["tiny", "base", "small"]
GPT_MODELS = ["gpt-4o-mini", "gpt-4o"]

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True, parents=True)


def test_transcribe_and_save():
    if not NORWEGIAN_AUDIO_PATH.exists():
        pytest.skip(f"Audio file not found: {NORWEGIAN_AUDIO_PATH}")

    if not ENGLISH_AUDIO_PATH.exists():
        pytest.skip(f"Audio file not found: {ENGLISH_AUDIO_PATH}")

    audio_segment_norwegian = AudioSegment.from_mp3(NORWEGIAN_AUDIO_PATH)
    chunks_norwegian = chunk_audio(audio_segment_norwegian)

    audio_segment_english = AudioSegment.from_mp3(ENGLISH_AUDIO_PATH)
    chunks_english = chunk_audio(audio_segment_english)

    if not chunks_norwegian:
        pytest.skip(f"Audio could not be chunked: {NORWEGIAN_AUDIO_PATH}")

    if not chunks_english:
        pytest.skip(f"Audio could not be chunked: {ENGLISH_AUDIO_PATH}")

    process_chunks(chunks_norwegian, audio_segment_norwegian, NORWEGIAN_AUDIO_PATH, 'norwegian')
    process_chunks(chunks_english, audio_segment_english, ENGLISH_AUDIO_PATH, 'english')


def process_chunks(chunks, audio_segment, audio_path, language):
    for whisper_name in WHISPER_MODELS:
        try:
            logger.info("Loading model %s", whisper_name)
            whisper_model = WhisperModel(whisper_name, device="cpu", compute_type="int8")
            batched_model = BatchedInferencePipeline(model=whisper_model)

            times = []
            ads_results = []
            transcripts = []

            logger.info(f"Transcribing {audio_path} with {whisper_name}!")
            for i, chunk in enumerate(chunks):
                logger.info(f'Processing chunk {i + 1}/{len(chunks)} with model: {whisper_name}')
                duration = chunk.duration_seconds
                chunk_start = perf_counter()
                transcription = transcribe_audio(chunk, batched_model)
                chunk_end = perf_counter()

                transcription_time = chunk_end - chunk_start
                times.append({
                    "chunk_id": i,
                    "duration": duration,
                    "transcription_time": transcription_time
                })

                transcripts.append({
                    "chunk_id": i,
                    "transcription": transcription
                })

                for gpt_name in GPT_MODELS:
                    logger.info(f'Detecting ads with {gpt_name}')
                    ad_detection, usage = detect_ads(transcription, gpt_name)
                    ads_results.append({
                        "model": gpt_name,
                        "usage": usage,
                        "ads": {
                            "chunk_id": i,
                            "ads": ad_detection
                        }
                    })
                logger.info(
                    f'Processed chunk {i + 1}/{len(chunks)} with model: {whisper_name} in {transcription_time:.2f} seconds')

            save_result(language, whisper_name, times, ads_results, transcripts, RESULTS_DIR)
            logger.info(f"Completed benchmark for model {whisper_name}")
            time_file = RESULTS_DIR / language / whisper_name / "time.json"
            assert time_file.exists(), f"{whisper_name} did not produce time.json"

        except Exception as e:
            logger.error(f"Error processing model {whisper_name}: {str(e)}")


def save_result(language, model_name, times, ads, transcripts, output_dir):
    model_dir = output_dir / language /model_name
    model_dir.mkdir(exist_ok=True, parents=True)

    # Save  timing information
    time_file = model_dir / "time.json"
    with open(time_file, "w") as f:
        time_data = {
            "model": model_name,
            "total_time": sum(item["transcription_time"] for item in times),
            "chunk_times": times
        }
        json.dump(time_data, f, indent=2)

    # Save ad detection results
    ads_file = model_dir / "ads.json"
    with open(ads_file, "w") as f:
        ads_data = {
            "model": model_name,
            "ads": ads
        }
        json.dump(ads_data, f, indent=2)

    # Save plain text transcription
    text_file = model_dir / "transcription.txt"
    with open(text_file, "w") as f:
        for chunk in transcripts:
            f.write(f"--- Chunk {chunk['chunk_id']} ---\n")
            # Extract all words and join them
            if chunk["transcription"]:
                if isinstance(chunk["transcription"], str):
                    # Handle already formatted string
                    f.write(f"{chunk['transcription']}\n\n")
                else:
                    # Handle structured transcription
                    full_text = " ".join(item["text"] for item in chunk["transcription"])
                    f.write(f"{full_text}\n\n")

    no_ts_file = model_dir / "transcript_plain.txt"
    with open(no_ts_file, "w") as f_plain:
        for chunk in transcripts:
            raw = chunk["transcription"]
            cleaned = re.sub(r"\[\d+\.\d+-\d+\.\d+\]\s*", "", raw)
            paragraph = " ".join(cleaned.split())
            wrapped = textwrap.fill(paragraph, width=80)
            f_plain.write(f"--- Chunk {chunk['chunk_id']} ---\n")
            f_plain.write(wrapped + "\n\n")

    logger.info(f"Results for model {model_name} saved to {model_dir}")


def chunk_audio(audio, chunk_duration_seconds=240, chunk_duration_ms=240000):
    duration_seconds = audio.duration_seconds
    if duration_seconds <= chunk_duration_seconds:
        chunks = [audio]
    else:
        chunks = [audio[i:i + chunk_duration_ms] for i in range(0, len(audio), chunk_duration_ms)]
    return chunks


def detect_ads(transcript, llm_model):
    try:
        completion = \
            client.chat.completions.create(
                model=llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a system that detects ads in audio transcriptions from podcasts. "
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
        usage = completion.usage
        usage_dict = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens
        }

        classification = completion.choices[0].message.content.strip()
        logger.info(classification)
        pattern = r"start:\s*([\d.]+).*?end:\s*([\d.]+).*?summary:\s*['\"]?([^'\"]+)['\"]?"
        ad_segments = [{"start": float(m[0]), "end": float(m[1]), "summary": m[2].strip()} for m in
                       re.findall(pattern, classification)]
        logger.info(f"Detected ad-segments: {ad_segments}")
        return ad_segments, usage_dict

    except Exception as e:
        raise


def transcribe_audio(audio_segment, batched_model):
    try:
        buffer = BytesIO()
        audio_segment.export(buffer, format="wav")
        buffer.seek(0)

        segments, _ = batched_model.transcribe(buffer, word_timestamps=True)

        # Convert generator to list to avoid issues with it being consumed
        segments_list = list(segments)

        # Create structured transcription
        transcription = [
            {
                "start": word.start,
                "end": word.end,
                "text": word.word
            }
            for segment in segments_list
            for word in segment.words
        ]

        formatted_transcription = "\n".join(
            [f"[{w['start']:.2f}-{w['end']:.2f}] {w['text']}" for w in transcription]
        )
        return formatted_transcription
    except Exception as e:
        logger.error(f"Error during transcription: {str(e)}")
        return None
