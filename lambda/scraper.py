"""
The Cloud Scraper - Website Scraper Lambda Function
Extracts structured data from static websites using Requests and BeautifulSoup.
Supports configurable extraction rules and archives raw HTML to Amazon S3.
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin
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
) -> str:
    """Persist raw HTML snapshot and audit metadata to Amazon S3."""
    if not bucket_name:
        logger.warning("No S3 bucket specified. Skipping raw HTML snapshot save.")
        return ""

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
        return html_key
    except (ClientError, NoCredentialsError, NoRegionError) as e:
        logger.warning("Could not archive raw HTML to S3 (dry-run/credentials required): %s", str(e))
        return ""


def lambda_handler(event, context=None):
    """
    Lambda Handler for Website Scraping.
    Receives site_id and optional target_url override.
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
    timeout = int(site_config.get("timeout_seconds", 15))
    timestamp = datetime.now(timezone.utc).isoformat()
    timestamp_folder = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

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

    raw_s3_key = ""
    if bucket_name:
        raw_s3_key = save_raw_snapshot_to_s3(
            bucket_name=bucket_name,
            site_id=site_id,
            timestamp_str=timestamp_folder,
            html_content=html_content,
            metadata=metadata,
        )

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
    # Local test execution
    test_event = {"site_id": "books_toscrape"}
    result = lambda_handler(test_event)
    print(f"Scraped {result.get('records_count', 0)} records from {result.get('site_id')}")
    if result.get("records"):
        print("Sample record:", json.dumps(result["records"][0], indent=2))
