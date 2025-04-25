import threading
import requests
import time
import os
import re

from flask import Response
from enums.status import AudioStatus
from tasks import process_urls_task, initiate_streaming_task

from audio_processing import fetch_audio
from helpers.rss_helpers import extract_urls_from_rss
from helpers.file_helpers import allowed_file, save_file
from helpers.cache_helpers import retrieve_status, retrieve_audio, cached_url, initiate_key

from flask import Blueprint, request, jsonify, send_file, Response, stream_with_context
import xml.etree.ElementTree as ET
import logging
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'flac'}
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

audio_bp = Blueprint('audio', __name__)


@audio_bp.route('/rss', methods=['POST'])
def check_rss():
    """
        This route is used to upload RSS feeds to the server. The server will process and cache the
        most recent urls in the RSS feed (if not already processed and caches).
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files['file']
    if 'application/xml' not in file.content_type:
        return jsonify({"error": "Wrong file format. Expected application/xml"}), 400
    try:
        rss = file.read()
        urls = extract_urls_from_rss(rss, limit=3)  # Number of urls to retrieve
        logger.info(f"Retrieved the lists of urls:{urls}")
        process_urls_task.delay(urls)
        return "retrieved", 200
    except Exception as e:
        logger.error(e)
        return jsonify({"error": str(e)}), 500


@audio_bp.route('/podcast', methods=['GET'])
def request_podcast():
    """
    Retrieve a podcast by URL:
      - If it's not processed: enqueue and stream as it’s processed.
      - If it’s still processing: stream as it's processed.
      - If it’s complete: return the entire podcast.
    """
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No url provided"}), 400
    try:
        saved = cached_url(url)
        # 1) Not saved in cache -> start processing and streaming
        if not saved:
            logger.info('Url is NOT SAVED in cache!')
            initiated = initiate_key(url)
            if initiated:
                initiate_streaming_task.delay(url)
            podcast = retrieve_audio(url)
            return Response(
                podcast,
                status=200,
                mimetype='audio/mpeg'
            )
        # 3) Saved in cache → start streaming
        if saved:
            logger.info('Url is SAVED in cache!.')
            podcast = retrieve_audio(url)
            return Response(
                podcast,
                status=200,
                mimetype='audio/mpeg'
            )
        # 4) Fallback for any other status
        return jsonify({"error": f"Unexpected status: {status}"}), 500
    except Exception as e:
        logger.exception("Error in /podcast")
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