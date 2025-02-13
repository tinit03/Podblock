import requests
from flask import Flask, request, jsonify
import os
import openai
#import whisper
from faster_whisper import WhisperModel, BatchedInferencePipeline
from dotenv import load_dotenv
from flask_cors import CORS
from pydub import AudioSegment
# Load environment variables from the .env file
load_dotenv()

# Access the API key from environment variables
api_key = os.environ.get('OPENAI_API_KEY')
#model = whisper.load_model("base.en")
model = WhisperModel("turbo", device="cpu", compute_type="int8")
batched_model = BatchedInferencePipeline(model=model)

client=openai.OpenAI(api_key=api_key)
app = Flask(__name__)
if __name__ == '__main__':
    app.run(host='0.0.0.0')
CORS(app)
ALLOWED_EXTENSIONS = {'wav','mp3','flac'}
app.config['UPLOAD_FOLDER'] = './uploads'
#app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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



@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"

@app.route('/hello', methods=['GET'])
def login():
    return "hello world", 200


@app.route('/upload_from_extension', methods=['POST'])
def upload_audio():
    if 'file' not in request.files:
        return "No file found", 400

    file = request.files['file']

    if not allowed_file(file.filename):
        return "Filetype not allowed", 400
    if file.filename == '':
        return "No file found"

    # Access file details
    print(f"Filename: {file.filename}")
    print(f"Content-Type: {file.content_type}")
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        # Process the uploaded audio file
        result = process(file_path)
        return jsonify(result), 200
    except Exception as e:
        return f"An error occured, {str(e)}", 500

@app.route('/upload', methods=['POST'])
def upload_audio():
    if 'file' not in request.files:
        return "No file found", 400

    file = request.files['file']

    if not allowed_file(file.filename):
        return "Filetype not allowed", 400
    if file.filename == '':
        return "No file found"

    # Access file details
    print(f"Filename: {file.filename}")
    print(f"Content-Type: {file.content_type}")
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        # Process the uploaded audio file
        result = process_proxy(file_path)
        return jsonify(result), 200
    except Exception as e:
        return f"An error occured, {str(e)}", 500

@app.route('/download', methods=['POST'])
def post_url():
    data = request.json
    if not data or 'url' not in data:
        return jsonify({"error": "No URL provided"}), 400

    url=data['url']

    try:
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            return jsonify({"error": "Failed to download file"}), 400
        filename = url.split("/")[-1].split('?')[0]
        if not allowed_file(filename):
            return jsonify({"error": "actually, we don't support this format"})
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Process the downloaded audio file
        result = process_proxy(file_path)
        return jsonify(result), 200
    except Exception as e:
            return jsonify({"error": str(e)}), 500

def process(audio_name):
    try:
        # result=model.transcribe(word_timestamps=True
        #                         ,audio=audio_name)
        segments, _ = batched_model.transcribe(audio_name, word_timestamps=True,batch_size=8)

        # Extract word-level timestamps
        word_timestamps = [
            {
                "start": word.start,
                "end": word.end,
                "text": word.word
            }
            for segment in segments
            for word in segment.words
        ]

        for segment in segments:
            print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))
        print(word_timestamps)
        # Format the data to send to ChatGPT
        words_with_timestamps = "\n".join(
            [f"[{w['start']}-{w['end']}] {w['text']}" for w in word_timestamps]
        )
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a system that detects ads in audio transcriptions. Based on the word-level timestamps provided, determine the start and end times of any ad segments. For each ad segment, provide a 5-word summary of the ad. Return the start and end times for each ad segment in this format start:,end:.(e.g., start: 13.12, end:13.2), followed by a 5-word summary (e.g. summary:'Ad about buying light food'). If no ad is found, return 'No ad detected.'"
                },
                {
                    "role": "user",
                    "content": f"Here is the transcription with word-level timestamps:\n{words_with_timestamps}"
                }
            ]
        )

        classification = completion.choices[0].message.content.strip()
        # Check if no ad was detected
        if classification.lower() == "no ad detected.":
            return {
                "ad_detection": "No ad detected"
            }
        print(classification)
        # Parse the formatted ad segments into a structured dictionary
        ad_segments = []
        ad_lines = classification.split("\n")
        for line in ad_lines:
            # Extract start, end, and summary from the format "start:xxx, end:xxx, summary: 'xxxx'"
            parts = line.split(", ")
            if len(parts) == 3:
                try:
                    start = float(parts[0].split(":")[1].strip())
                    end = float(parts[1].split(":")[1].strip())
                    summary = parts[2].split(":")[1].strip().strip("'")
                    segment = {
                        "start": start,
                        "end": end,
                        "summary": summary,
                    }
                    ad_segments.append(segment)
                except ValueError:
                    continue  # In case of formatting issues, skip line

        # Return the ad segments as JSON
        return {
            "ad_detection": ad_segments
        }

    finally:
        os.remove(audio_name)
def process_proxy(audio_name):
    try:
        audio = AudioSegment.from_file(audio_name) # Access the audio
        duration = audio.duration_seconds
        if duration < 240:  # Less than 4 minutes (240 seconds)
            print("Audio file is less than 4 minutes, skipping chunking.")
            chunk_files = [audio_name]  # No chunking, just use the original file
        else:
            # Split the audio file into chunks if it's longer than 4 minutes
            chunk_files = chunk_audio(audio_name)
        total_duration=0 # This variable is used to track the total duration of the chunks

        ad_segments = []

        for chunk_file in chunk_files:
            segments, _ = batched_model.transcribe(chunk_file, word_timestamps=True,batch_size=8)

            # Extract word-level timestamps
            word_timestamps = [
                {
                    "start": word.start+total_duration,
                    "end": word.end+total_duration,
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
            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a system that detects ads in audio transcriptions. Based on the word-level timestamps provided, determine the start and end times of any ad segments. For each ad segment, provide a 5-word summary of the ad. Return the start and end times for each ad segment in this format start:,end:.(e.g., start: 13.12, end:13.2), followed by a 5-word summary (e.g. summary:'Ad about buying light food'). If no ad is found, return 'No ad detected.'"
                    },
                    {
                        "role": "user",
                        "content": f"Here is the transcription with word-level timestamps:\n{words_with_timestamps}"
                    }
                ]
            )
            classification = completion.choices[0].message.content.strip()
            if classification.lower() == "no ad detected.":
                return {
                    "ad_detection": "No ad detected"
                }
            print(classification)
            # Parse the formatted ad segments into a structured dictionary
            ad_lines = classification.split("\n")
            for line in ad_lines:
                # Extract start, end, and summary from the format "start:xxx, end:xxx, summary: 'xxxx'"
                parts = line.split(", ")
                if len(parts) == 3:
                    try:
                        start = float(parts[0].split(":")[1].strip())
                        end = float(parts[1].split(":")[1].strip())
                        summary = parts[2].split(":")[1].strip().strip("'")
                        segment = {
                            "start": start,
                            "end": end,
                            "summary": summary,
                        }
                        ad_segments.append(segment)
                    except ValueError:
                        continue  # In case of formatting issues, skip line

        if ad_segments:
            new_audio_path = cut_out_ads(audio_name, ad_segments)
            return {
                "ad_detection": ad_segments,
                "audio_file": new_audio_path
            }
        else:
            return {
                "ad_detection": "No ad detected"
            }
    finally:
        os.remove(audio_name)


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
                adjusted_ad_segments[-1]["end"] = max(end, prev_end)  # Extend the last segment instead of adding a new one
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

    return new_audio_path