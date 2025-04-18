import threading
import requests
import time
import os
import re

from enums.status import AudioStatus
from tasks import process_urls_task

from audio_processing import (remove_ads, detect_ads, process_audio, stream_and_process_audio, stream_partial_content)
from helpers.rss_helpers import extract_urls_from_rss
from helpers.file_helpers import allowed_file, save_file
from helpers.cache_helpers import (initiate_key, cached_rss_url, cached_source_url,
                                   retrieve_status_and_audio_source_url, poll_audio_beginning,
                                   retrieve_status_source_url, poll_and_stream_audio)
from helpers.url_helpers import normalize_url, generate_cache_url
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
        most recent podcasts in the RSS feed (if not already processed and caches).
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files['file']
    if 'application/xml' not in file.content_type:
        return jsonify({"error": "Wrong file format. Expected application/xml"}), 400
    try:
        rss_feed = file.read()
        urls = extract_urls_from_rss(rss_feed, limit=1)
        logger.info(f"Retrieved the lists of urls:{urls}")
        process_urls_task.delay(urls)
        return "retrieved", 200
    except Exception as e:
        logger.error(e)
        return jsonify({"error": str(e)}), 500


@audio_bp.route('/podcast', methods=['GET'])
def request_podcast():
    """
    This route is used to retrieve podcasts from the server. If the podcast is processed and complete in cache,
    this route will return the entire podcast. If else the route imitate streaming with a test-file.
    """
    podcast_url = request.args.get('url')
    if not podcast_url:
        return jsonify({"error": "No url provided"}), 400
    try:
        result = retrieve_status_rss_url(podcast_url)

        # If result is none, start streaming and redirect
        if result is None:
            # stream_and_process_audio(podcast_url)
            return "Redirect", 302

        status, podcast = result

        if status == AudioStatus.PROCESSING:
            return "Redirect", 302

        if podcast and status == AudioStatus.COMPLETE:
            return podcast, 200

        return jsonify({"error": "Unexpected state"}), 500

    except Exception as e:
        logger.error(e)
        return jsonify({"error": str(e)}), 500


@audio_bp.route('/stream_podcast', methods=['GET'])
def stream_while_processing_podcast():
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


chunk_size = 4 * 1024 * 1024  # 4MB chunks

# Global dictionary to track processed chunks for each file
processed_chunks = {}


@audio_bp.route("/stream-test")
def stream_test():
    """
    Progressive streaming with chunked transfer encoding or partial content:
    - Requests without Range header get chunked transfer encoding
    - Range requests get partial content responses
    """
    file_path = 'test.mp3'
    if not os.path.exists(file_path):
        return "Test file not found", 404

    file_size = os.path.getsize(file_path)
    file_key = f"{file_path}_{os.path.getmtime(file_path)}"

    # Start background processing if needed
    if file_key not in processed_chunks:
        processed_chunks[file_key] = {
            'chunks': [],
            'processing_complete': False,
            'total_chunks': (file_size + chunk_size - 1) // chunk_size
        }
        threading.Thread(
            target=process_chunks_in_background,
            args=(file_path, file_key)
        ).start()

    # Get the range header
    range_header = request.headers.get('Range')

    # For requests without Range header, use chunked transfer encoding
    if not range_header:
        print(f"No range header, using chunked transfer encoding")

        # Create headers for chunked streaming
        headers = {
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache"
        }

        # Create generator function for chunked streaming
        def generate():
            for chunk_index in range(processed_chunks[file_key]['total_chunks']):
                # Wait for this chunk to be "processed"
                wait_for_chunk(file_key, chunk_index)

                # Calculate chunk bounds
                start = chunk_index * chunk_size
                end = min((chunk_index + 1) * chunk_size - 1, file_size - 1)

                # Read and yield the chunk
                with open(file_path, 'rb') as f:
                    f.seek(start)
                    chunk_data = f.read(end - start + 1)
                    print(f"Streaming chunk {chunk_index}, bytes {start}-{end}")
                    yield chunk_data

        # Return a streaming response
        return Response(
            generate(),
            status=200,  # OK status for streaming
            mimetype="audio/mpeg",
            headers=headers
        )

    else:
        # Parse the range header for partial content requests
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if not match:
            return "Invalid range header", 400

        start_byte = int(match.group(1))
        requested_end = match.group(2)
        end_byte = int(requested_end) if requested_end else file_size - 1
        print(f"Range request for bytes {start_byte}-{end_byte}")

        # Calculate which chunk this corresponds to
        chunk_index = start_byte // chunk_size

        # Wait for this chunk to be "processed"
        wait_for_chunk(file_key, chunk_index)

        # Calculate the actual range to serve based on chunk boundaries
        chunk_start = chunk_index * chunk_size
        next_chunk_start = (chunk_index + 1) * chunk_size
        real_end = min(end_byte, next_chunk_start - 1, file_size - 1)

        # Read the requested range
        with open(file_path, 'rb') as f:
            f.seek(start_byte)
            data = f.read(real_end - start_byte + 1)

        print(f"Serving bytes {start_byte}-{real_end} from chunk {chunk_index}")

        # Build response headers for partial content
        headers = {
            "Content-Range": f"bytes {start_byte}-{real_end}/{file_size}",
            "Content-Length": str(real_end - start_byte + 1),
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache"
        }
        # Return the requested range as partial content
        return Response(
            data,
            status=206,  # Partial Content for range requests
            mimetype="audio/mpeg",
            headers=headers
        )

def process_chunks_in_background(file_path, file_key):
    """Simulates processing chunks with delays"""
    try:
        file_size = os.path.getsize(file_path)
        total_chunks = (file_size + chunk_size - 1) // chunk_size

        print(f"Starting processing of {total_chunks} chunks for {file_path}")
        print(f"Each chunk is approximately 4 minutes of audio (~{chunk_size / 1024 / 1024:.1f}MB)")

        for i in range(total_chunks):
            # Simulate processing delay (except for first chunk)
            if i > 0:
                processing_time = 10  # 10 seconds per chunk (increased for better visibility)
                print(f"Processing chunk {i}/{total_chunks}...")
                time.sleep(processing_time)

            # Mark this chunk as processed
            processed_chunks[file_key]['chunks'].append(i)
            print(f"Chunk {i}/{total_chunks} processed")

        # Mark processing as complete
        processed_chunks[file_key]['processing_complete'] = True
        print(f"All {total_chunks} chunks processed for {file_path}")

    except Exception as e:
        print(f"Error processing chunks: {e}")
        processed_chunks[file_key]['processing_complete'] = True


def wait_for_chunk(file_key, chunk_index):
    """Wait until the specified chunk is processed, with a shorter timeout for early chunks."""
    # Use a shorter max wait for early chunks to allow the stream to continue
    max_wait = 5 if chunk_index < 2 else 10  # allow a 5-second wait for the first 2 chunks
    wait_time = 0
    wait_interval = 0.1

    # For the first chunk, make it available immediately
    if chunk_index == 0:
        if chunk_index not in processed_chunks[file_key]['chunks']:
            processed_chunks[file_key]['chunks'].append(0)
        return

    print(f"Waiting for chunk {chunk_index} to be processed...")
    while wait_time < max_wait:
        if chunk_index in processed_chunks[file_key]['chunks']:
            print(f"Chunk {chunk_index} is ready")
            return
        time.sleep(wait_interval)
        wait_time += wait_interval

    # If not processed in time, log and continue to avoid blocking playback
    print(f"Warning: Chunk {chunk_index} not processed after {max_wait} seconds. Proceeding anyway.")

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