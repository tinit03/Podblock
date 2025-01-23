from flask import Flask, request, jsonify
import os
import openai
import json
import whisper
client = openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'])
model = whisper.load_model("tiny.en")

app = Flask(__name__)
if __name__ == '__main__':
    app.run(host='0.0.0.0')

ALLOWED_EXTENSIONS = {'wav','mp3','flac'}
app.config['UPLOAD_FOLDER'] = './uploads'
#app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"

@app.route('/hello', methods=['GET'])
def login():
    return "hello world", 200

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
        result = process(file_path)
        return jsonify(result), 200
    except Exception as e:
        return f"An error occured, {str(e)}", 500


def process(audio_name):
    try:
        result=model.transcribe(word_timestamps=True
                                ,audio=audio_name)

        # Extract word-level timestamps
        word_timestamps = [
            {
                "start": word["start"],
                "end": word["end"],
                "text": word["word"]
            }
            for segment in result.get("segments", [])
            for word in segment["words"]
        ]

        # Format the data to send to ChatGPT
        words_with_timestamps = "\n".join(
            [f"[{w['start']}-{w['end']}] {w['text']}" for w in word_timestamps]
        )

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
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
