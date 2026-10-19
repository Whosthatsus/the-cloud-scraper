"""
The Cloud Scraper - Website Scraper Lambda Function
Extracts structured data from static websites using Requests and BeautifulSoup.
Supports configurable extraction rules, robots.txt compliance checking,
and archives raw HTML to Amazon S3.
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, NoRegionError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))
DEFAULT_USER_AGENT = (
    "TheCloudScraper/1.0 (+https://github.com/aws-samples/the-cloud-scraper; CAD-Course-Project)"
)


def is_running_in_aws() -> bool:
    """Detect whether code is running inside an active AWS Lambda execution environment."""
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or os.environ.get("AWS_EXECUTION_ENV"))


def check_robots_allowed(base_url: str, target_url: str, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """
    Check if target URL access is permitted by site's robots.txt.
    Returns True if allowed or if robots.txt is unavailable/not present.
    """
    try:
        parsed_base = urlparse(base_url)
        robots_url = f"{parsed_base.scheme}://{parsed_base.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        # Fast timeout for robots.txt check (3 seconds)
        resp = requests.get(robots_url, headers={"User-Agent": user_agent}, timeout=3)
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
            return rp.can_fetch(user_agent, target_url)
        elif resp.status_code in (404, 410):
            # No robots.txt means all paths permitted
            return True
        return True
    except Exception as e:
        logger.debug("Robots.txt check skipped or timed out (%s): defaulting to allow", str(e))
        return True


def load_site_config(site_id: str, config_override: dict = None) -> dict:
    """Load configuration for a specific target website."""
    if config_override and config_override.get("site_id") == site_id:
        return config_override

    config_path = os.environ.get(
        "SITES_CONFIG_PATH",
        os.path.join(os.path.dirname(__file__), "..", "config", "sites_config.json"),
    )

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            all_configs = json.load(f)
            for site in all_configs.get("sites", []):
                if site.get("site_id") == site_id:
                    return site

    raise ValueError(f"Configuration for site_id '{site_id}' not found at {config_path}")


def fetch_page_content(url: str, timeout: int = 15, user_agent: str = DEFAULT_USER_AGENT) -> requests.Response:
    """Fetch website HTML content with timeouts, custom User-Agent, and error handling."""
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    logger.info("Fetching target URL: %s (timeout=%ds)", url, timeout)
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response


def extract_field_value(container, field_config: dict, base_url: str):
    """Extract a single field value from a BeautifulSoup HTML container."""
    selector = field_config.get("selector")
    attribute = field_config.get("attribute")
    is_list = field_config.get("is_list", False)

    if not selector:
        return None

    if is_list:
        elements = container.select(selector)
        results = []
        for el in elements:
            if attribute:
                val = el.get(attribute)
            else:
                val = el.get_text(strip=True)
            if val:
                results.append(val)
        return results

    element = container.select_one(selector)
    if not element:
        fallback = field_config.get("fallback_selector")
        if fallback:
            element = container.select_one(fallback)
        if not element:
            return None

    if attribute:
        if attribute == "class" and isinstance(element.get("class"), list):
            val = " ".join(element.get("class"))
        else:
            val = element.get(attribute)
    else:
        val = element.get_text(strip=True)

    if val and field_config.get("type") == "url":
        val = urljoin(base_url, val.strip())

    return val


def parse_html_records(html_content: str, site_config: dict) -> list:
    """Parse raw HTML content into extracted record dictionaries based on configured selectors."""
    soup = BeautifulSoup(html_content, "html.parser")
    container_selector = site_config.get("container_selector")
    fields = site_config.get("fields", {})
    base_url = site_config.get("base_url", "")

    containers = soup.select(container_selector) if container_selector else [soup]
    logger.info("Found %d items matching container selector '%s'", len(containers), container_selector)

    extracted_records = []
    for container in containers:
        record = {}
        for field_name, field_cfg in fields.items():
            record[field_name] = extract_field_value(container, field_cfg, base_url)
        extracted_records.append(record)

    return extracted_records


def save_raw_snapshot_to_s3(
    bucket_name: str, site_id: str, timestamp_str: str, html_content: str, metadata: dict
) -> tuple:
    """
    Persist raw HTML snapshot and audit metadata to Amazon S3.
    Returns (html_key, error_message).
    """
    if not bucket_name:
        return "", None

    try:
        s3_client = boto3.client("s3", region_name=DEFAULT_REGION)
        html_key = f"raw/{site_id}/{timestamp_str}/page.html"
        meta_key = f"raw/{site_id}/{timestamp_str}/metadata.json"

        s3_client.put_object(
            Bucket=bucket_name,
            Key=html_key,
            Body=html_content.encode("utf-8"),
            ContentType="text/html",
            ServerSideEncryption="AES256",
        )
        s3_client.put_object(
            Bucket=bucket_name,
            Key=meta_key,
            Body=json.dumps(metadata, indent=2).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        logger.info("Archived raw HTML to s3://%s/%s", bucket_name, html_key)
        return html_key, None
    except Exception as e:
        if is_running_in_aws():
            logger.error("AWS S3 put_object for raw snapshot failed: %s", str(e))
            return "", f"S3 snapshot save failed: {str(e)}"
        else:
            logger.info("Local offline mode: Raw HTML S3 snapshot skipped (%s)", str(e))
            return "", None


def lambda_handler(event, context=None):
    """
    Lambda Handler for Website Scraping.
    Receives site_id and optional target_url override or mock_html for testing.
    Scrapes the target, stores raw HTML to S3, and returns records.
    """
    logger.info("Received scraper event: %s", json.dumps(event))

    site_id = event.get("site_id", "books_toscrape")
    config_override = event.get("config_override")
    bucket_name = event.get("bucket_name") or os.environ.get("RAW_S3_BUCKET", "")

    try:
        site_config = load_site_config(site_id, config_override)
    except Exception as e:
        return {
            "statusCode": 400,
            "status": "FAILURE",
            "site_id": site_id,
            "error": f"Configuration error: {str(e)}",
        }

    target_url = event.get("target_url") or site_config.get("target_url")
    base_url = site_config.get("base_url", target_url)
    timeout = int(site_config.get("timeout_seconds", 15))
    timestamp = datetime.now(timezone.utc).isoformat()
    timestamp_folder = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Support deterministic local fixture testing via event parameter 'mock_html'
    mock_html = event.get("mock_html")

    if mock_html:
        html_content = mock_html
        http_status = 200
        logger.info("Using provided mock_html fixture (%d bytes)", len(html_content))
    else:
        # Check robots.txt compliance before fetching
        if not check_robots_allowed(base_url, target_url):
            logger.warning("Scraping disallowed by robots.txt for URL: %s", target_url)
            return {
                "statusCode": 403,
                "status": "FAILURE",
                "site_id": site_id,
                "target_url": target_url,
                "error": "Scraping disallowed by target website robots.txt policy.",
                "is_retryable": False,
            }

        try:
            response = fetch_page_content(target_url, timeout=timeout)
            html_content = response.text
            http_status = response.status_code
        except requests.exceptions.RequestException as e:
            logger.error("Scraping request failed for URL %s: %s", target_url, str(e))
            return {
                "statusCode": 502,
                "status": "FAILURE",
                "site_id": site_id,
                "target_url": target_url,
                "scraped_at": timestamp,
                "error": f"HTTP request failed: {str(e)}",
                "is_retryable": True,
            }

    records = parse_html_records(html_content, site_config)

    metadata = {
        "site_id": site_id,
        "target_url": target_url,
        "scraped_at": timestamp,
        "http_status": http_status,
        "records_count": len(records),
        "response_bytes": len(html_content.encode("utf-8")),
    }

    raw_s3_key, s3_err = "", None
    if bucket_name:
        raw_s3_key, s3_err = save_raw_snapshot_to_s3(
            bucket_name=bucket_name,
            site_id=site_id,
            timestamp_str=timestamp_folder,
            html_content=html_content,
            metadata=metadata,
        )

    # In production AWS, if S3 snapshot storage fails, report the error
    if is_running_in_aws() and s3_err:
        return {
            "statusCode": 500,
            "status": "FAILURE",
            "site_id": site_id,
            "target_url": target_url,
            "error": s3_err,
        }

    return {
        "statusCode": 200,
        "status": "SUCCESS",
        "site_id": site_id,
        "site_name": site_config.get("site_name", site_id),
        "target_url": target_url,
        "scraped_at": timestamp,
        "raw_s3_key": raw_s3_key,
        "records_count": len(records),
        "records": records,
    }


if __name__ == "__main__":
    test_event = {"site_id": "books_toscrape"}
    result = lambda_handler(test_event)
    print(f"Scraped {result.get('records_count', 0)} records from {result.get('site_id')}")
    if result.get("records"):
        print("Sample record:", json.dumps(result["records"][0], indent=2))
