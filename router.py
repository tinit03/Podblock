import threading
import requests
from audio_processing import (remove_ads, detect_ads, process_urls_in_background, process_audio, stream_and_process_audio,
                              stream_partial_content)
from helpers.file_helpers import allowed_file, save_file
from helpers.cache_helpers import (initiate_key, cached_rss_url, cached_source_url, retrieve_status_and_audio_source_url,
                                   poll_audio_beginning, retrieve_status_source_url, poll_and_stream_audio)
from helpers.url_helpers import normalize_url, generate_cache_url
from flask import Response

from flask import Blueprint, request, jsonify, send_file, Response, stream_with_context
import xml.etree.ElementTree as ET
import logging
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'flac'}
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

audio_bp = Blueprint('audio', __name__)


@audio_bp.route('/request_podcast', methods=['GET'])
def request_podcast():
    podcast_url = request.args.get('url')
    if not podcast_url:
        return jsonify({"error": "No url provided"}), 400
    try:
        normalized_url = normalize_url(podcast_url)
        result = retrieve_status_and_audio_source_url(normalized_url)

        # If result is none, start streaming and redirect
        if result is None:
            stream_and_process_audio(podcast_url)
            return "Redirect", 302

        status, podcast = result

        if status == "PROCESSING":
            return "Redirect", 302

        if podcast and status == "COMPLETE":
            return podcast, 200

        return jsonify({"error": "Unexpected state"}), 500

    except Exception as e:
        logger.error(e)
        return jsonify({"error": str(e)}), 500


@audio_bp.route('/partial_content', methods=['GET'])
def stream_podcast():
    podcast_url = request.args.get('url')
    if not podcast_url:
        return jsonify({"error": "No url provided"}), 400
    try:
        normalized_url = normalize_url(podcast_url)
        result = retrieve_status_and_audio_source_url(normalized_url)

        if result is None:
            return stream_partial_content(podcast_url), 206

        if status == "PROCESSING":
            return Response(
                stream_with_context(poll_and_stream_audio(normalized_url)),
                mimetype="audio/mpeg",
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
        else:
            return retrieve_status_and_audio_source_url(normalized_url), 200
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


@audio_bp.route('/stream_podcast', methods=['GET'])
def stream_podcast():
    podcast_url = request.args.get('url')
    if not podcast_url:
        return jsonify({"error": "No url provided"}), 400
    try:
        normalized_url = normalize_url(podcast_url)
        status = retrieve_status_source_url(normalized_url)
        if status is None:
            return jsonify({"error": "Podcast does not exist in cache"}), 400

        if status == "PROCESSING":
            return Response(
                stream_with_context(poll_and_stream_audio(normalized_url)),
                mimetype="audio/mpeg",
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
        else:
            return retrieve_status_and_audio_source_url(normalized_url), 200
    except Exception as e:
        logger.error(f"Error: {e}")
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
                if len(urls) == 1:  # Stop after 2
                    break
        logger.info(f"Retrieved the lists of urls:{urls}")

        threading.Thread(target=process_urls_in_background, args=(urls,)).start()
        return "retrieved", 200
    except Exception as e:
        print(e)
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