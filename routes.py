import requests
from audio_processing import cut_out_ads, detect_ads, transcribe
from file_helpers import allowed_file, save_file
from flask import Blueprint, request, jsonify, send_file
import xml.etree.ElementTree as ET

ALLOWED_EXTENSIONS = {'wav', 'mp3', 'flac'}

audio_bp = Blueprint('audio', __name__)

@audio_bp.route('/upload', methods=['POST'])
def upload_audio():
    if 'file' not in request.files:
        return "No file found", 400

    file = request.files['file']

    if not allowed_file(file.filename, ALLOWED_EXTENSIONS):
        return "Filetype not allowed", 400
    if file.filename == '':
        return "No file found"

    # Access file details
    print(f"Filename: {file.filename}")
    print(f"Content-Type: {file.content_type}")
    try:
        file_path = save_file(file, './uploads')
        # Process the uploaded audio file
        transcription = transcribe(file_path)
        ad_segments = detect_ads(transcription)
        result = cut_out_ads(file_path, ad_segments)
        return send_file(result, as_attachment=True)
    except Exception as e:
        return f"An error occured, {str(e)}", 500


@audio_bp.route('/download', methods=['POST'])
def post_url():
    data = request.json
    if not data or 'url' not in data:
        return jsonify({"error": "No URL provided"}), 400
    url = data['url']
    try:
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            return jsonify({"error": "Failed to download file"}), 400
        filename = url.split("/")[-1].split('?')[0]
        if not allowed_file(filename, ALLOWED_EXTENSIONS):
            return jsonify({"error": "actually, we don't support this format"})
        file_path = save_file(filename, './uploads')
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        # Process the downloaded audio file
        transcription = transcribe(file_path)
        ad_segments = detect_ads(transcription)
        result = cut_out_ads(file_path, ad_segments)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@audio_bp.route('/check_rss', methods=['POST'])
def check_rss():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty file"}), 400
    try:
        tree = ET.parse(file)
        root = tree.getroot()
        # urls = [item.find("enclosure").attrib["url"] for item in root.findall("./channel/item") if
        #         item.find("enclosure") is not None]
        urls = []
        for item in root.findall("./channel/item"):
            if item.find("enclosure") is not None:
                urls.append(item.find("enclosure").attrib["url"])
                if len(urls) == 3:  # Stop after 2
                    break
        print(urls)
        #Extract URLs from the RSS feed
        threading.Thread(target=process_urls_in_background, args=(urls,)).start()
        return "retrieved", 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# @audio_bp.route('/upload_from_extension', methods=['POST'])
# def extension():
#     if 'file' not in request.files:
#         return "No file found", 400
#
#     file = request.files['file']
#
#     if not allowed_file(file.filename, ALLOWED_EXTENSIONS):
#         return "Filetype not allowed", 400
#     if file.filename == '':
#         return "No file found"
#
#     # Access file details
#     print(f"Filename: {file.filename}")
#     print(f"Content-Type: {file.content_type}")
#     try:
#         file_path= save_file(file, './uploads')
#         # Process the uploaded audio file
#         result = process(file_path)
#         return jsonify(result), 200
#     except Exception as e:
#         return f"An error occured, {str(e)}", 500