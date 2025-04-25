import xml.etree.ElementTree as ET
import logging
import requests

logger = logging.getLogger(__name__)

def fetch_rss(url):
    """
    Fetch rss from url.
    """
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            content_type = response.headers.get("Content-Type", "")
            if "application/xml" not in content_type:
                raise Exception(f"Unexpected content type: {content_type}")
            return response.content
        else:
            raise Exception(f"Failed to fetch RSS feed. Status code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching RSS from {url}: {e}")
        raise

def extract_rss_urls(rss_content, limit=1):
    """
    Extract audio URLs from RSS XML.
    """
    # Check for empty content
    if len(rss_content) == 0:
        logger.error("RSS content is empty")
        raise ValueError("RSS content is empty")
    # Decode bytes to string
    xml_string = rss_content.decode('utf-8')
    # Parse XML
    root = ET.fromstring(xml_string)
    # Extract URLs
    urls = []
    for item in root.findall("./channel/item"):
        if item.find("enclosure") is not None:
            urls.append(item.find("enclosure").attrib["url"])
            if len(urls) >= limit:
                break

    logger.info(f"Retrieved {len(urls)} audio URLs from RSS feed")
    return urls
