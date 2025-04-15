import threading
import requests
import time
import os
import re

from enums.status import AudioStatus

from audio_processing import (remove_ads, detect_ads, process_urls_in_background, process_audio,
                              stream_and_process_audio, stream_partial_content)

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
    """
    This route is used to request podcasts from the server. If the podcast is processed,
    this route will return the entire podcast. If else the route will initiate processing of the podcast
    and redirect the client to another endpoint for streaming while the podcast is processing.
    """
    podcast_url = request.args.get('url')
    if not podcast_url:
        return jsonify({"error": "No url provided"}), 400
    try:
        normalized_url = normalize_url(podcast_url)
        result = retrieve_status_and_audio_source_url(normalized_url)

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


@audio_bp.route('/upload_rss', methods=['POST'])
def check_rss():
    """
        This route is used to upload an RSS feed to the server. The server will look at the three most recent urls
        in the feed and see if they are already process and cached.
    """

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


processed_chunks = {}
processing_threads = {}


@audio_bp.route("/stream-test")
def stream_test():
    """
    ExoPlayer-compatible test endpoint that streams a static MP3 file.
    This endpoint simulates processing by releasing chunks over time,
    perfect for testing client-side streaming behavior.
    """
    # Path to your static test MP3 file
    file_path = 'test.mp3'

    if not os.path.exists(file_path):
        return Response("Test file not found", status=404)

    file_size = os.path.getsize(file_path)
    request_id = str(time.time())  # Unique ID for this streaming session
    content_type = 'audio/mpeg'

    # Handle range requests (critical for ExoPlayer)
    range_header = request.headers.get('Range', None)

    if range_header:
        # Parse range header
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            byte_start = int(match.group(1))
            byte_end = int(match.group(2)) if match.group(2) else file_size - 1
        else:
            byte_start = 0
            byte_end = file_size - 1

        # Validate range
        if byte_start >= file_size:
            return Response(
                "Invalid range",
                status=416,  # Range Not Satisfiable
                headers={"Content-Range": f"bytes */{file_size}"}
            )

        byte_end = min(byte_end, file_size - 1)
        content_length = byte_end - byte_start + 1

        # Handle range request directly without processing
        def generate_range():
            with open(file_path, 'rb') as f:
                f.seek(byte_start)
                data = f.read(content_length)
                yield data

        headers = {
            'Content-Type': content_type,
            'Content-Length': str(content_length),
            'Content-Range': f'bytes {byte_start}-{byte_end}/{file_size}',
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'no-cache'
        }

        return Response(generate_range(), 206, headers=headers)

    else:
        # For non-range requests, simulate processing with delayed chunks

        # Background function that simulates processing
        def simulate_processing(file_path, request_id):
            try:
                # Create a buffer for processed chunks
                processed_chunks[request_id] = []

                # Open the file
                with open(file_path, 'rb') as f:
                    # First chunk - immediately available (header data)
                    first_chunk = f.read(256 * 1024)  # 256KB first chunk
                    processed_chunks[request_id].append(first_chunk)

                    # Read the rest of the file in chunks with simulated processing delay
                    chunk_size = 128 * 1024  # 128KB chunks for the rest

                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break

                        # Simulate processing delay (shorter for testing)
                        time.sleep(1)  # 1 second delay between chunks

                        # Add the processed chunk
                        processed_chunks[request_id].append(chunk)

                # Mark the end of file
                processed_chunks[request_id].append(None)

            except Exception as e:
                print(f"Error in processing thread: {e}")
                # Clean up in case of error
                if request_id in processed_chunks:
                    del processed_chunks[request_id]

        # Start the processing thread
        thread = threading.Thread(
            target=simulate_processing,
            args=(file_path, request_id)
        )
        thread.daemon = True
        thread.start()
        processing_threads[request_id] = thread

        # Generator function to stream chunks as they become available
        def stream_chunks():
            chunk_index = 0

            # Wait briefly for first chunk (should be almost immediate)
            max_wait = 1  # Maximum 1 second to wait for first chunk
            wait_time = 0
            wait_interval = 0.1

            while wait_time < max_wait and (
                    request_id not in processed_chunks or
                    len(processed_chunks[request_id]) == 0):
                time.sleep(wait_interval)
                wait_time += wait_interval

            # Stream chunks as they become available
            while True:
                # Wait for the next chunk if it's not ready yet
                while (chunk_index >= len(processed_chunks.get(request_id, [])) and
                       request_id in processed_chunks and
                       processed_chunks[request_id] and
                       processed_chunks[request_id][-1] is not None):
                    time.sleep(0.2)  # Short sleep while waiting for next chunk

                # Check if we've reached the end
                if (request_id not in processed_chunks or
                        chunk_index >= len(processed_chunks[request_id])):
                    break

                chunk = processed_chunks[request_id][chunk_index]
                if chunk is None:
                    break  # End of file marker

                yield chunk
                chunk_index += 1

            # Clean up when done
            if request_id in processed_chunks:
                del processed_chunks[request_id]
            if request_id in processing_threads:
                del processing_threads[request_id]

        # Return a streaming response
        headers = {
            'Content-Type': content_type,
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'no-store, no-cache, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'Transfer-Encoding': 'chunked'  # Important for streaming!
        }

        return Response(
            stream_with_context(stream_chunks()),
            headers=headers
        )

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