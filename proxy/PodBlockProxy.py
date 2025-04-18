import requests
import uuid
import os
from mitmproxy import http


# python3 -m venv .venv
# source .venv/bin/activate
# pip install -r requirements.txt

"""
Script for mitmproxy to work with PodBlock.

- 1. Intercepts RSS XML responses and forwards them to the PodBlock server for processing.
- 2. Redirects podcast audio stream requests to the PodBlock server.
"""


class XMLForwarder:
    def __init__(self):

        base = os.getenv("PODBLOCK_SERVER", "http://127.0.0.1:5000")

        self.server_xml_endpoint = f'{base}/rss'
        self.server_podcast_endpoint = f'{base}/podcast'


    def request(self, flow):
        if not any(pattern in flow.request.url for pattern in ["redirect.mp3"]):
            return

        if any(pattern in flow.request.url for pattern in [self.server_podcast_endpoint]):
            return

        print(f"Intercepted initial podcast request: {flow.request.url}")
        redirect_url = f"{self.server_podcast_endpoint}?url={flow.request.url}"

        flow.response = http.Response.make(
            302,
            b"Redirecting to test stream",
            {
                "Location": redirect_url,
            }
        )
        return

    def response(self, flow):
        content_type = flow.response.headers.get("Content-Type", "").lower()
        if content_type != "application/xml":
            return

        print(f" Intercepted XML from: {flow.request.url}")
        try:
            rrss_xml = flow.response.content
            self.send_xml_to_server(rrss_xml)

        except requests.exceptions.RequestException as e:
            print(f" Error sending extracting xml from response: {e}")
        return

    def send_xml_to_server(self, rss_xml):
        request_id = uuid.uuid4()
        print(f"[{request_id}] Forwarding to {self.server_xml_endpoint}")

        try:
            with requests.Session() as session:
                response = session.post(
                    self.server_xml_endpoint,
                    files={'file': ('rss_feed.xml', rss_xml, 'application/xml')},
                    timeout=10
                )

                if response.status_code == 200:
                    print(f" [{request_id}] Successfully forwarded XML!")
                    print(f" Response code: {response.status_code}")
                else:
                    print(f" [{request_id}] Failed to forward XML. Status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"[{request_id}] Error sending XML to server: {e}")


addons = [
    XMLForwarder()
]