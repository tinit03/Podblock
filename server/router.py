import threading
import requests
import time
import os
import re

from enums.status import AudioStatus
from tasks import process_urls_task

from audio_processing import fetch_audio_segment, fetch_audio_bytes
from helpers.rss_helpers import extract_urls_from_rss
from helpers.file_helpers import allowed_file, save_file
from helpers.cache_helpers import retrieve_audio_rss_url, retrieve_status_rss_url, poll_and_stream_audio
from helpers.url_helpers import normalize_url
from flask import Response

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
        rss_feed = file.read()
        urls = extract_urls_from_rss(rss_feed, limit=3) #Number of urls to process
        logger.info(f"Retrieved the lists of urls:{urls}")
        process_urls_task.delay(urls)
        return "retrieved", 200
    except Exception as e:
        logger.error(e)
        return jsonify({"error": str(e)}), 500


@audio_bp.route('/podcast', methods=['GET'])
def request_podcast():
    """
    This route is used to retrieve podcasts. If the podcast is processed and complete in cache,
    this route will return the entire podcast. If else the route will return the original podcast
    """
    podcast_url = request.args.get('url')
    if not podcast_url:
        return jsonify({"error": "No url provided"}), 400
    try:
        status = retrieve_status_rss_url(podcast_url)
        # If status is none, process and stream podcast.
        if status is None:
            podcast = fetch_audio_bytes(podcast_url)
            return podcast, 200 # Streaming is not implemented yet, returning original podcast

        podcast = retrieve_audio_rss_url(podcast_url)

        # If status is processing, stream podcast.
        if status == AudioStatus.Processing:
            podcast = fetch_audio_bytes(podcast_url)
            return podcast, 200 # Streaming is not implemented yet, returning original podcast

        # If status is complete, return podcast.
        if podcast and status == AudioStatus.Complete:
            return Response(podcast,
                            status=200,
                            mimetype="audio/mpeg")

        return jsonify({"error": "Unexpected state"}), 500

    except Exception as e:
        logger.error(e)
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