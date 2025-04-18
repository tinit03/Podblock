import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger(__name__)


def extract_urls_from_rss(rss_content, limit=1):
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
