import threading
import requests
import time
import os
import re

from flask import Response
from enums.status import AudioStatus
from tasks import process_urls_task, initiate_streaming_task

from audio_processing import fetch_audio, retrieve_timestamps
from helpers.rss_helpers import extract_rss_urls, fetch_rss
from helpers.file_helpers import allowed_file, save_file
from helpers.cache_helpers import retrieve_status, retrieve_audio, cached_url, initiate_key

from flask import Blueprint, request, jsonify, send_file, Response, stream_with_context, current_app
import xml.etree.ElementTree as ET
import logging
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'flac'}
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

audio_bp = Blueprint('audio', __name__)


@audio_bp.route('/rss', methods=['POST'])
def process_rss():
    """
        This route is used to upload RSS feeds to the server. The server will process and cache the
        most recent urls in the RSS feed (if not already processed and caches).
    """
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No url provided"}), 400
    try:
        rss = fetch_rss(url)
        urls = extract_rss_urls(rss, limit=3)  # Number of urls to retrieve
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
            logger.info('Url is not saved in cache!')
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
            logger.info('Url is saved in cache!.')
            podcast = retrieve_audio(url)
            return Response(
                retrieve_audio(url),
                status=200,
                mimetype='audio/mpeg'
            )
        # 4) Fallback for any other status
        return jsonify({"error": f"Unexpected status: {status}"}), 500
    except Exception as e:
        logger.exception("Error in /podcast")
        return jsonify({"error": str(e)}), 500


@audio_bp.route('/extension', methods=['POST'])
def extension():
    if 'file' not in request.files:
        return "No file found", 400
    file = request.files['file']
    name = file.filename
    logger.info(f'Processing {name}!')
    try:

        timestamps, duration = retrieve_timestamps(file, name)
        return jsonify({
            "timestamps": timestamps,
            "duration": duration
        }), 200
    except Exception as e:
        logger.error(f'Error retrieving timestamps: {e}')
        return jsonify({"error": str(e)}), 500