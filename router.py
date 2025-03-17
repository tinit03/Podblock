import threading
import requests
from audio_processing import remove_ads, detect_ads, transcribe, process_urls_in_background
from helpers.file_helpers import allowed_file, save_file
from helpers.cache_helpers import initiate_key, cached_rss_url, cached_source_url, retrieve_audio
from helpers.url_helpers import normalize_url
from flask import Response

from flask import Blueprint, request, jsonify, send_file
import xml.etree.ElementTree as ET
import logging
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'flac'}
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

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
        result = remove_ads(file_path, ad_segments)
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
        result = remove_ads(file_path, ad_segments)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@audio_bp.route('/request_podcast', methods=['GET'])
def request_podcast():
    podcast_url = request.args.get('url')
    if not podcast_url:
        return jsonify({"error": "No url provided"}), 400
    try:
        podcast = retrieve_audio(normalize_url(podcast_url))
        if podcast:
            if podcast == "INIT":
                mp3_file_path = "resources/test.mp3"
                logger.info("Returning test mp3 file")
            else:
                mp3_file_path = podcast
                logger.info("Returning real mp3 file")

            logger.info(mp3_file_path)

            with open(mp3_file_path, "rb") as f:
                audio_bytes = f.read()
            return Response(audio_bytes, mimetype='audio/mpeg')
        else:
            return jsonify({"error": "podcast is not processed"}), 400

    except Exception as e:
        logger.error(e)
        return jsonify({"error": str(e)}), 500


@audio_bp.route('/upload_rss', methods=['POST'])
def check_rss():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files['file']
    if 'application/xml' not in file.content_type:
        return jsonify({"error": "Wrong file format. Expected application/xml"}), 400
    try:
        # Read file content as bytes
        rss_feed = file.read()
        # Check for empty file
        if len(rss_feed) == 0:
            logger.error("Uploaded file is empty")
            return jsonify({"error": "Uploaded file is empty"}), 400
        # Decode bytes to string
        xml_string = rss_feed.decode('utf-8')

        root = ET.fromstring(xml_string)

        urls = []
        for item in root.findall("./channel/item"):
            if item.find("enclosure") is not None:
                urls.append(item.find("enclosure").attrib["url"])
                if len(urls) == 2:  # Stop after 2
                    break
        logger.info(f"Retrieved the lists of urls:{urls}")

        threading.Thread(target=process_urls_in_background, args=(urls,)).start()
        return "retrieved", 200
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500


@audio_bp.route('/cache_test', methods=['POST'])
def cache_test():
    key = "hei::rss"
    source_url = "nei"
    rss_url = "nei"

    initiate_key(key)

    print(cached_source_url(source_url))
    print(cached_rss_url(rss_url))

    return "complete", 200



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