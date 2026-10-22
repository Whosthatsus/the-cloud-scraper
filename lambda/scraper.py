"""
The Cloud Scraper - Website Scraper Lambda Function
General-purpose web scraper supporting configurable extraction rules,
generic automatic HTML extraction, robots.txt compliance checking,
multi-page pagination, strict SSRF/redirect network security validation,
and Amazon S3 raw HTML snapshot archival.
"""

import os
import json
import time
import socket
import ipaddress
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

DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "ap-southeast-2"))
DEFAULT_USER_AGENT = (
    "TheCloudScraper/2.0 (+https://github.com/aws-samples/the-cloud-scraper; CAD-Course-Project)"
)

# SSRF Protection: Blocked hostnames and IP ranges
FORBIDDEN_HOSTNAMES = {"localhost", "metadata", "instance-data"}
BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # RFC1918 Private Class A
    ipaddress.ip_network("172.16.0.0/12"),    # RFC1918 Private Class B
    ipaddress.ip_network("192.168.0.0/16"),   # RFC1918 Private Class C
    ipaddress.ip_network("169.254.0.0/16"),   # Link-Local / AWS Metadata (169.254.169.254)
    ipaddress.ip_network("100.64.0.0/10"),    # Carrier-Grade NAT
    ipaddress.ip_network("0.0.0.0/8"),        # Current network
    ipaddress.ip_network("::1/128"),          # IPv6 Loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 Unique Local Address
    ipaddress.ip_network("fe80::/10"),        # IPv6 Link-Local
]


def is_running_in_aws() -> bool:
    """Detect whether code is running inside an active AWS Lambda execution environment."""
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or os.environ.get("AWS_EXECUTION_ENV"))


def validate_target_url_security(url: str) -> tuple:
    """
    Validate target URL to prevent SSRF, private network probing, and cloud metadata access.
    Returns (is_safe: bool, error_message: str).
    """
    if not url or not isinstance(url, str):
        return False, "Target URL must be a non-empty string."

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Malformed URL: {str(e)}"

    # 1. Enforce standard HTTP/HTTPS schemes only
    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported URL scheme '{parsed.scheme}'. Only http and https protocols are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL does not contain a valid hostname."

    hostname_lower = hostname.lower()

    # 2. Block forbidden hostnames
    if hostname_lower in FORBIDDEN_HOSTNAMES or hostname_lower.endswith(".local") or hostname_lower.endswith(".internal"):
        return False, f"Access to internal or loopback hostname '{hostname}' is blocked for security."

    # 3. Disallow dangerous non-web ports
    if parsed.port and parsed.port not in (80, 443, 8080):
        return False, f"Access to port {parsed.port} is not permitted. Only standard web ports (80, 443) are allowed."

    # 4. Check if hostname is a raw IP literal or resolves to private/metadata IP
    try:
        ip_obj = ipaddress.ip_address(hostname_lower)
        for net in BLOCKED_IP_NETWORKS:
            if ip_obj in net:
                return False, f"Direct access to private or restricted IP address ({hostname}) is forbidden (SSRF protection)."
    except ValueError:
        # Not a raw IP literal, attempt DNS resolution check
        try:
            ip_str = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip_str)
            for net in BLOCKED_IP_NETWORKS:
                if ip_obj in net:
                    return False, f"Target hostname '{hostname}' resolves to private/restricted IP ({ip_str}). Request blocked for SSRF prevention."
        except socket.gaierror:
            # Unresolvable hostname in real DNS: block if it looks like loopback
            if hostname_lower in ("localhost", "127.0.0.1", "0.0.0.0"):
                return False, f"Access to '{hostname}' is blocked."
        except Exception as e:
            logger.debug("DNS check skipped for %s: %s", hostname, str(e))

    return True, ""


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


def fetch_page_content(
    url: str,
    timeout: int = 15,
    user_agent: str = DEFAULT_USER_AGENT,
    max_redirects: int = 3,
    max_bytes: int = 5 * 1024 * 1024,
) -> requests.Response:
    """
    Fetch website HTML content with timeouts, custom User-Agent, strict SSRF redirect re-validation,
    content-type validation, and error handling.
    """
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    current_url = url

    for hop in range(max_redirects + 1):
        is_safe, sec_err = validate_target_url_security(current_url)
        if not is_safe:
            raise requests.exceptions.RequestException(
                f"SSRF Security Violation on URL hop {hop}: {sec_err}"
            )

        logger.info("Fetching target URL: %s (timeout=%ds, hop=%d)", current_url, timeout, hop)
        response = requests.get(
            current_url,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
        )

        # Handle redirects manually to validate the target of every hop
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            if not location:
                break
            redirect_url = urljoin(current_url, location)
            logger.info("Redirect detected: %s -> %s", current_url, redirect_url)
            current_url = redirect_url
            continue

        response.raise_for_status()

        # Validate content type if headers present
        raw_ct = response.headers.get("Content-Type", "")
        if isinstance(raw_ct, str) and raw_ct:
            content_type = raw_ct.lower()
            allowed_types = (
                "text/html",
                "application/xhtml+xml",
                "text/plain",
                "application/xml",
                "text/xml",
                "application/json",
            )
            if not any(allowed in content_type for allowed in allowed_types):
                raise ValueError(
                    f"Unsupported content type '{content_type}'. The Cloud Scraper only processes HTML and text web content."
                )

        # Enforce response body size limit
        content_bytes = getattr(response, "content", b"")
        if isinstance(content_bytes, (bytes, bytearray)) and len(content_bytes) > max_bytes:
            raise ValueError(
                f"Response body exceeded maximum safety size limit ({max_bytes / (1024 * 1024):.1f} MB)."
            )

        return response

    raise requests.exceptions.TooManyRedirects(
        f"Exceeded maximum permitted redirects ({max_redirects})."
    )


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

    val = None
    if attribute:
        if attribute == "class" and isinstance(element.get("class"), list):
            val = " ".join(element.get("class"))
        else:
            val = element.get(attribute)
        # If attribute was empty or missing on element, fallback to text content
        if not val:
            val = element.get_text(strip=True)
    else:
        val = element.get_text(strip=True)

    if val and field_config.get("type") == "url":
        val = urljoin(base_url, str(val).strip())

    return val


def extract_generic_html_records(soup: BeautifulSoup, base_url: str, target_url: str) -> list:
    """
    Intelligently extract structured records from arbitrary HTML web pages.
    Detects repeated container patterns (cards, rows, articles, list items) or extracts
    the primary content sections, headings, and document metadata.
    """
    records = []

    # 1. Page-level metadata
    page_title = ""
    if soup.title and soup.title.string:
        page_title = soup.title.string.strip()
    elif soup.select_one("meta[property='og:title']"):
        page_title = soup.select_one("meta[property='og:title']").get("content", "").strip()
    elif soup.find("h1"):
        page_title = soup.find("h1").get_text(strip=True)

    page_desc = ""
    desc_tag = soup.select_one("meta[name='description']") or soup.select_one("meta[property='og:description']")
    if desc_tag and desc_tag.get("content"):
        page_desc = desc_tag["content"].strip()

    # 2. Candidate container selectors for structured collections
    container_candidates = [
        "article",
        "div[class*='card']",
        "div[class*='item']",
        "div[class*='product']",
        "div[class*='post']",
        "div[class*='entry']",
        "div[class*='listing']",
        "div[class*='result']",
        "div[class*='row'] > div",
        "li[class*='item']",
        "tr.athing",
        "table tbody tr",
        "section[class*='item']",
        "main article",
    ]

    best_containers = []
    for cand in container_candidates:
        matches = soup.select(cand)
        # Check for a reasonable set of structured elements (between 2 and 150)
        if 2 <= len(matches) <= 150:
            has_substance = any(len(el.get_text(strip=True)) > 5 for el in matches[:5])
            if has_substance:
                best_containers = matches
                logger.info("Generic extraction selected container pattern '%s' with %d items", cand, len(matches))
                break

    # If repeating containers found, extract item records
    if best_containers:
        for idx, el in enumerate(best_containers):
            # Extract heading / title
            heading_el = el.find(["h1", "h2", "h3", "h4", "h5", "a"])
            title = heading_el.get_text(strip=True) if heading_el else ""
            if not title:
                title = f"{page_title or 'Record'} #{idx + 1}"

            # Extract link
            link_el = el.find("a", href=True)
            detail_link = urljoin(base_url, link_el["href"].strip()) if link_el else target_url

            # Extract body text / description
            para_el = el.find(["p", "span", "div[class*='desc']", "div[class*='text']"])
            text_val = para_el.get_text(strip=True) if para_el else el.get_text(strip=True)
            if len(text_val) > 400:
                text_val = text_val[:397] + "..."

            records.append({
                "title": title,
                "text": text_val,
                "detail_link": detail_link,
                "url": detail_link,
                "source_url": target_url,
                "item_index": idx + 1,
            })

    # If no repeating containers found, extract document sections (headings + paragraphs)
    if not records:
        sections = soup.find_all(["h1", "h2", "h3"])
        for idx, h in enumerate(sections[:20]):
            heading_text = h.get_text(strip=True)
            if not heading_text or len(heading_text) < 2:
                continue

            p_text = ""
            sibling = h.find_next_sibling(["p", "div"])
            if sibling:
                p_text = sibling.get_text(strip=True)
            if len(p_text) > 400:
                p_text = p_text[:397] + "..."

            link_el = h.find("a", href=True) or (sibling.find("a", href=True) if sibling else None)
            detail_link = urljoin(base_url, link_el["href"].strip()) if link_el else target_url

            records.append({
                "title": heading_text,
                "text": p_text or page_desc or heading_text,
                "detail_link": detail_link,
                "url": detail_link,
                "source_url": target_url,
                "item_index": idx + 1,
            })

    # Ultimate fallback: Page-level document record
    if not records:
        records.append({
            "title": page_title or "Web Page Document",
            "text": page_desc or soup.get_text(" ", strip=True)[:400] or "No text content found",
            "detail_link": target_url,
            "url": target_url,
            "source_url": target_url,
            "item_index": 1,
        })

    return records


def parse_html_records(html_content: str, site_config: dict) -> list:
    """Parse raw HTML content into extracted record dictionaries based on configured selectors or generic mode."""
    soup = BeautifulSoup(html_content, "html.parser")
    container_selector = site_config.get("container_selector")
    fields = site_config.get("fields", {})
    base_url = site_config.get("base_url", "")
    target_url = site_config.get("target_url", base_url)
    extraction_type = site_config.get("extraction_type", "custom" if container_selector else "generic")

    # If generic extraction requested or no container selector specified, run generic extraction
    if extraction_type == "generic" or not container_selector:
        return extract_generic_html_records(soup, base_url, target_url)

    # Custom selector extraction
    containers = soup.select(container_selector)
    logger.info("Found %d items matching container selector '%s'", len(containers), container_selector)

    # If custom container matched 0 items, gracefully fall back to generic extraction rather than empty result
    if len(containers) == 0:
        logger.warning(
            "Custom container selector '%s' matched 0 items. Falling back to generic HTML extraction.",
            container_selector,
        )
        return extract_generic_html_records(soup, base_url, target_url)

    extracted_records = []
    for container in containers:
        record = {}
        for field_name, field_cfg in fields.items():
            record[field_name] = extract_field_value(container, field_cfg, base_url)
        if "url" not in record and "detail_link" in record:
            record["url"] = record["detail_link"]
        if "source_url" not in record:
            record["source_url"] = target_url
        extracted_records.append(record)

    return extracted_records


def load_site_config(site_id: str, config_override: dict = None, dynamodb_table: str = None) -> dict:
    """
    Load configuration for a target website.
    Checks:
    1. Direct config_override dictionary.
    2. Amazon DynamoDB configuration store (table-name: the-cloud-scraper-records).
    3. Local config/sites_config.json.
    Raises ValueError if not found.
    """
    if config_override and isinstance(config_override, dict):
        if config_override.get("site_id") == site_id or config_override.get("target_url"):
            return config_override

    # Check DynamoDB configuration store
    table_name = dynamodb_table or os.environ.get("DYNAMODB_TABLE_NAME")
    if table_name:
        try:
            ddb = boto3.resource("dynamodb", region_name=DEFAULT_REGION)
            table = ddb.Table(table_name)
            resp = table.get_item(Key={"site_id": f"CONFIG#{site_id}", "record_id": "TARGET_CONFIG"})
            if "Item" in resp:
                item = resp["Item"]
                logger.info("Loaded target configuration for '%s' from DynamoDB", site_id)
                fields_val = item.get("fields", {})
                if isinstance(item.get("fields_json"), str):
                    try:
                        fields_val = json.loads(item["fields_json"])
                    except Exception:
                        pass
                val_rules = item.get("validation_rules", {})
                if isinstance(item.get("validation_json"), str):
                    try:
                        val_rules = json.loads(item["validation_json"])
                    except Exception:
                        pass
                return {
                    "site_id": item.get("target_id", site_id),
                    "site_name": item.get("site_name", site_id),
                    "base_url": item.get("base_url", item.get("target_url")),
                    "target_url": item.get("target_url"),
                    "extraction_type": item.get("extraction_type", "generic"),
                    "container_selector": item.get("container_selector"),
                    "next_page_selector": item.get("next_page_selector"),
                    "fields": fields_val,
                    "validation_rules": val_rules,
                    "timeout_seconds": int(item.get("timeout_seconds", 15)),
                    "page_limit": int(item.get("page_limit", 1)),
                    "enabled": bool(item.get("enabled", True)),
                }
        except Exception as e:
            logger.debug("DynamoDB target lookup skipped: %s", str(e))

    # Check local configuration files
    candidate_paths = [
        os.environ.get("SITES_CONFIG_PATH"),
        os.path.join(os.path.dirname(__file__), "config", "sites_config.json"),
        os.path.join(os.path.dirname(__file__), "..", "config", "sites_config.json"),
        os.path.join(os.getcwd(), "config", "sites_config.json"),
    ]
    for cp in candidate_paths:
        if cp and os.path.exists(cp):
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    all_configs = json.load(f)
                    for site in all_configs.get("sites", []):
                        if site.get("site_id") == site_id:
                            return site
            except Exception as e:
                logger.warning("Could not read config at %s: %s", cp, str(e))

    raise ValueError(f"Configuration for site_id '{site_id}' not found in candidate paths: {candidate_paths}")


def build_dynamic_site_config(site_id: str, event: dict) -> dict:
    """Build a fully dynamic target configuration for an arbitrary user-submitted URL."""
    target_url = event.get("target_url")
    parsed_u = urlparse(target_url)
    base_url = f"{parsed_u.scheme}://{parsed_u.netloc}/"
    site_name = event.get("site_name") or parsed_u.netloc

    return {
        "site_id": site_id,
        "site_name": site_name,
        "base_url": base_url,
        "target_url": target_url,
        "extraction_type": event.get("extraction_type", "generic"),
        "container_selector": event.get("container_selector"),
        "next_page_selector": event.get("next_page_selector"),
        "fields": event.get("fields", {}),
        "validation_rules": event.get("validation_rules", {}),
        "timeout_seconds": int(event.get("timeout_seconds", 15)),
        "page_limit": int(event.get("page_limit", 1)),
        "rate_limit_delay_seconds": 1.0,
        "enabled": True,
    }


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
    Receives site_id, optional target_url override, custom extraction config,
    page_limit, timeout_seconds, or mock_html.
    Scrapes the target(s), enforces robots.txt and SSRF security, stores raw HTML to S3, and returns records.
    """
    logger.info("Received scraper event: %s", json.dumps(event))

    site_id = event.get("site_id", "books_toscrape")
    config_override = event.get("config_override")
    bucket_name = event.get("bucket_name") or os.environ.get("RAW_S3_BUCKET", "")
    dynamodb_table = event.get("dynamodb_table") or os.environ.get("DYNAMODB_TABLE_NAME")

    # Load configuration from override, DynamoDB, or config files
    try:
        site_config = load_site_config(site_id, config_override, dynamodb_table=dynamodb_table)
    except ValueError as ve:
        # If site_id is unknown but target_url is provided, build dynamic configuration on the fly!
        if event.get("target_url"):
            site_config = build_dynamic_site_config(site_id, event)
            logger.info("Created dynamic site configuration for custom URL: %s", event.get("target_url"))
        else:
            return {
                "statusCode": 400,
                "status": "FAILURE",
                "site_id": site_id,
                "error": f"Configuration error: {str(ve)}",
            }

    target_url = event.get("target_url") or site_config.get("target_url")
    base_url = site_config.get("base_url", target_url)

    # Validate timeout with safe bounds (3 to 30 seconds)
    try:
        requested_timeout = int(event.get("timeout_seconds", site_config.get("timeout_seconds", 15)))
        timeout = min(max(requested_timeout, 3), 30)
    except (ValueError, TypeError):
        timeout = 15

    # Validate page limit with safe bounds (1 to 5 pages)
    try:
        requested_pages = int(event.get("page_limit", site_config.get("page_limit", 1)))
        page_limit = min(max(requested_pages, 1), 5)
    except (ValueError, TypeError):
        page_limit = 1

    rate_limit_delay = float(site_config.get("rate_limit_delay_seconds", 1.0))
    timestamp = datetime.now(timezone.utc).isoformat()
    timestamp_folder = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Support deterministic local fixture testing via event parameter 'mock_html'
    mock_html = event.get("mock_html")

    if event.get("simulate_failure"):
        logger.info("Simulated network fault requested by test harness")
        return {
            "statusCode": 502,
            "status": "FAILURE",
            "site_id": site_id,
            "target_url": target_url,
            "scraped_at": timestamp,
            "error": "HTTP connection timed out / target host unreachable (Simulated Network Fault)",
            "is_retryable": True,
        }

    if mock_html:
        html_content = mock_html
        http_status = 200
        logger.info("Using provided mock_html fixture (%d bytes)", len(html_content))
        records = parse_html_records(html_content, site_config)
        pages_scraped = 1
    else:
        # 1. Enforce strict SSRF & URL security validation
        is_safe, sec_err = validate_target_url_security(target_url)
        if not is_safe:
            logger.warning("SSRF/Security validation failed for URL: %s (%s)", target_url, sec_err)
            return {
                "statusCode": 400,
                "status": "FAILURE",
                "site_id": site_id,
                "target_url": target_url,
                "error": f"Security validation rejected target URL: {sec_err}",
                "is_retryable": False,
            }

        # 2. Check robots.txt compliance before fetching
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

        # 3. Fetch initial page with redirect SSRF validation
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
        except Exception as e:
            logger.error("Content processing error for URL %s: %s", target_url, str(e))
            return {
                "statusCode": 400,
                "status": "FAILURE",
                "site_id": site_id,
                "target_url": target_url,
                "scraped_at": timestamp,
                "error": str(e),
                "is_retryable": False,
            }

        records = parse_html_records(html_content, site_config)
        pages_scraped = 1

        # 4. Multi-page pagination loop (if page_limit > 1 and next_page_selector defined)
        next_page_sel = site_config.get("next_page_selector")
        current_url = target_url
        current_soup = BeautifulSoup(html_content, "html.parser")

        while pages_scraped < page_limit and next_page_sel:
            next_link_el = current_soup.select_one(next_page_sel)
            if not next_link_el or not next_link_el.get("href"):
                logger.info("No further pages found via next_page_selector '%s'", next_page_sel)
                break

            next_url = urljoin(current_url, next_link_el["href"].strip())

            # Validate security & robots.txt on paginated URL
            is_next_safe, _ = validate_target_url_security(next_url)
            if not is_next_safe or not check_robots_allowed(base_url, next_url):
                logger.warning("Pagination stopped: next URL failed security or robots.txt check: %s", next_url)
                break

            # Polite delay between page requests
            time.sleep(rate_limit_delay)

            try:
                next_resp = fetch_page_content(next_url, timeout=timeout)
                next_records = parse_html_records(next_resp.text, site_config)
                records.extend(next_records)
                pages_scraped += 1
                current_url = next_url
                current_soup = BeautifulSoup(next_resp.text, "html.parser")
                logger.info("Paginated to page %d: +%d records from %s", pages_scraped, len(next_records), next_url)
            except Exception as e:
                logger.warning("Pagination fetch failed for page %d (%s): %s", pages_scraped + 1, next_url, str(e))
                break

    metadata = {
        "site_id": site_id,
        "target_url": target_url,
        "scraped_at": timestamp,
        "http_status": http_status,
        "records_count": len(records),
        "pages_scraped": pages_scraped,
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
        "pages_scraped": pages_scraped,
        "records": records,
        "config_override": site_config,
        "extraction_type": site_config.get("extraction_type", "generic"),
    }


if __name__ == "__main__":
    test_event = {"site_id": "books_toscrape"}
    result = lambda_handler(test_event)
    print(f"Scraped {result.get('records_count', 0)} records from {result.get('site_id')}")
    if result.get("records"):
        print("Sample record:", json.dumps(result["records"][0], indent=2))
