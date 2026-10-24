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
import re
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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 (Compatible; TheCloudScraper/2.0; +https://github.com/aws-samples/the-cloud-scraper)"
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

def detect_page_incompatibility(html_content: str, status_code: int = 200) -> tuple:
    """
    Detect whether page cannot be scraped via static HTTP ingestion because it is:
    1. An active bot challenge / interstitial page (Akamai, Cloudflare, PerimeterX, etc.)
    2. An empty Single Page Application (SPA) skeleton requiring client-side JavaScript execution.
    Returns (is_incompatible: bool, diagnostic_reason: str).
    """
    if not html_content or len(html_content.strip()) == 0:
        return True, "Target returned an empty response body."

    lower = html_content.lower()

    # 1. Anti-bot interstitial challenge signatures
    challenge_signatures = [
        ("bm-verify=", "Akamai Bot Manager Challenge / Verification Interstitial"),
        ("_sec/verify?provider=", "Akamai Interstitial Security Challenge"),
        ("cf-chl-bypass", "Cloudflare Turnstile / Managed Challenge"),
        ("challenge-platform", "Cloudflare Anti-Bot Challenge Platform"),
        ("perimeterx", "HUMAN Security / PerimeterX Bot Defense Challenge"),
        ("datadome", "DataDome Anti-Bot Challenge"),
        ("enable javascript and cookies to continue", "Target requires active browser JavaScript and Cookie solving"),
        ("interstitial challenge", "Target displayed an interstitial verification screen"),
    ]
    for pattern, name in challenge_signatures:
        if pattern in lower:
            return (
                True,
                f"Interactive Anti-Bot Challenge Detected ({name}): Target website requires full browser "
                f"execution and challenge solving not supported in serverless HTTP pipeline.",
            )

    # 2. Client-side Single Page Application (SPA) empty skeleton signatures
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        for s in soup(["script", "style", "noscript"]):
            s.extract()
        visible_text = soup.get_text(" ", strip=True)

        # Check if the page contains extractable embedded hydration state or structured JSON-LD
        has_embedded_json = (
            "window.$preData" in html_content
            or "__NEXT_DATA__" in html_content
            or "application/ld+json" in lower
        )
        if has_embedded_json:
            return False, ""

        spa_markers = ['id="root"', 'id="app"', 'id="__next"']
        has_spa_mount = any(m in html_content for m in spa_markers)

        if has_spa_mount and len(visible_text) < 120:
            return (
                True,
                "JavaScript Rendering Required: Target is a Client-Side Single Page Application (SPA). "
                "Content is rendered dynamically in the browser via JavaScript and cannot be extracted from static server response.",
            )

        if len(visible_text) < 20 and len(html_content) > 500 and ("<script" in lower or "<noscript" in lower):
            return (
                True,
                "JavaScript Rendering Required: Static HTML response contains no readable textual content; page requires browser hydration.",
            )
    except Exception:
        pass

    return False, ""


def run_preflight_check(url: str, timeout: int = 8) -> dict:
    """
    Perform a bounded preflight assessment of a website URL before triggering a full scrape pipeline.
    Validates URL syntax, SSRF safety, reachability, HTTP status, robots.txt, and JavaScript rendering need.
    """
    if not url or not isinstance(url, str):
        return {
            "is_compatible": False,
            "status": "INVALID_URL",
            "url": url or "",
            "summary": "Target URL must be a non-empty string.",
            "warnings": ["Empty or invalid URL parameter"],
        }

    url = url.strip()
    is_safe, sec_err = validate_target_url_security(url)
    if not is_safe:
        return {
            "is_compatible": False,
            "status": "REJECTED_SSRF",
            "url": url,
            "summary": f"Security validation rejected target URL: {sec_err}",
            "warnings": ["Blocked by SSRF & Private Network Security Filter"],
        }

    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}/"
    robots_ok = check_robots_allowed(base_url, url)

    warnings = []
    if not robots_ok:
        warnings.append("Target path is disallowed by target website robots.txt policy.")

    # Execute bounded preflight GET request
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.exceptions.Timeout:
        return {
            "is_compatible": False,
            "status": "TIMEOUT",
            "url": url,
            "summary": f"Connection timed out after {timeout} seconds. Target host did not respond in time.",
            "warnings": warnings + ["Target host connection timed out"],
        }
    except requests.exceptions.SSLError as ssl_err:
        return {
            "is_compatible": False,
            "status": "SSL_ERROR",
            "url": url,
            "summary": f"SSL / TLS handshake failure: {str(ssl_err)}",
            "warnings": warnings + ["SSL certificate or protocol verification failed"],
        }
    except requests.exceptions.ConnectionError as conn_err:
        return {
            "is_compatible": False,
            "status": "CONNECTION_FAILED",
            "url": url,
            "summary": f"Target host connection failed or domain could not be resolved: {str(conn_err)}",
            "warnings": warnings + ["DNS or network connection error"],
        }
    except Exception as e:
        return {
            "is_compatible": False,
            "status": "REQUEST_ERROR",
            "url": url,
            "summary": f"HTTP request failed: {str(e)}",
            "warnings": warnings + [str(e)],
        }

    status_code = resp.status_code
    content_type = resp.headers.get("Content-Type", "")

    # Check status code
    if status_code in (401, 403):
        return {
            "is_compatible": False,
            "status": "ACCESS_DENIED",
            "url": url,
            "status_code": status_code,
            "content_type": content_type,
            "robots_allowed": robots_ok,
            "summary": f"Access Denied (HTTP {status_code}): Target host refused access. The page may require authentication or has active bot protection.",
            "warnings": warnings + [f"HTTP {status_code} Forbidden/Unauthorized response"],
        }

    if status_code == 404:
        return {
            "is_compatible": False,
            "status": "NOT_FOUND",
            "url": url,
            "status_code": 404,
            "content_type": content_type,
            "robots_allowed": robots_ok,
            "summary": "Target resource was not found (HTTP 404 Not Found).",
            "warnings": warnings + ["HTTP 404 Not Found"],
        }

    if status_code >= 400:
        return {
            "is_compatible": False,
            "status": f"HTTP_{status_code}",
            "url": url,
            "status_code": status_code,
            "content_type": content_type,
            "robots_allowed": robots_ok,
            "summary": f"Target host returned HTTP error status {status_code}.",
            "warnings": warnings + [f"HTTP {status_code}"],
        }

    # Check for content-type
    if "html" not in content_type.lower() and "text" not in content_type.lower():
        return {
            "is_compatible": False,
            "status": "UNSUPPORTED_MEDIA",
            "url": url,
            "status_code": status_code,
            "content_type": content_type,
            "robots_allowed": robots_ok,
            "summary": f"Unsupported media type '{content_type}'. The Cloud Scraper extracts data from HTML web pages.",
            "warnings": warnings + [f"Non-HTML Content-Type: {content_type}"],
        }

    # Check for anti-bot or SPA
    is_incompatible, diag_reason = detect_page_incompatibility(resp.text, status_code)
    if is_incompatible:
        return {
            "is_compatible": False,
            "status": "INCOMPATIBLE_STRUCTURE",
            "url": url,
            "status_code": status_code,
            "content_type": content_type,
            "robots_allowed": robots_ok,
            "requires_javascript": True,
            "summary": diag_reason,
            "warnings": warnings + [diag_reason],
        }

    # Check for usable content
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        page_title = soup.title.string.strip() if soup.title and soup.title.string else parsed.netloc

        soup_clean = BeautifulSoup(resp.text, "html.parser")
        for tag in soup_clean(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        headings_count = len(soup_clean.find_all(["h1", "h2", "h3"]))
        articles_count = len(soup_clean.select("article, div[class*='item'], div[class*='card'], tr, li"))
    except Exception:
        page_title = parsed.netloc
        headings_count = 0
        articles_count = 0

    recommended_mode = "generic"

    return {
        "is_compatible": True,
        "status": "COMPATIBLE",
        "url": url,
        "final_url": resp.url,
        "status_code": status_code,
        "content_type": content_type,
        "page_title": page_title,
        "robots_allowed": robots_ok,
        "requires_javascript": False,
        "recommended_mode": recommended_mode,
        "content_length_bytes": len(resp.content),
        "headings_found": headings_count,
        "summary": f"Preflight passed: Target is accessible (HTTP 200), returned valid HTML ({len(resp.content):,} bytes), and is compatible with generic extraction.",
        "warnings": warnings,
    }


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
    Excludes navigation chrome, detects repeated container patterns (cards, rows, articles),
    or extracts the primary document sections, headings, and semantic text.
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

    # Create a cleaned copy of soup without navigation, headers, footers, scripts, and styling
    try:
        soup_clean = BeautifulSoup(str(soup), "html.parser")
        for el in soup_clean(["script", "style", "nav", "header", "footer", "aside", "noscript", "svg"]):
            el.decompose()

        for el in soup_clean.select(".nav, .navbar, .menu, .sidebar, #sidebar, .header, .footer, .breadcrumbs, .pagination, .mw-navigation"):
            el.decompose()
    except Exception:
        soup_clean = soup

    # 2. Candidate container selectors for structured collections (scoped to main content if available)
    main_scope = soup_clean.find(["main", "article"]) or soup_clean.find(id=re.compile(r"content|main", re.I)) or soup_clean

    container_candidates = [
        "article",
        "div[class*='product']",
        "div[class*='card']",
        "div[class*='listing']",
        "div[class*='entry']",
        "div[class*='post']",
        "div[class*='result']",
        "tr.athing",
        "table tbody tr",
        "section[class*='item']",
        "div[class*='row'] > div",
        "div[class*='item']",
        "li[class*='item']",
    ]

    best_containers = []
    for cand in container_candidates:
        matches = main_scope.select(cand)
        # Filter matches that have at least 15 characters of substantive text
        substantive = [el for el in matches if len(el.get_text(strip=True)) >= 15]
        if 2 <= len(substantive) <= 150:
            best_containers = substantive
            logger.info("Generic extraction selected container pattern '%s' with %d items", cand, len(substantive))
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

            rec = {
                "title": title,
                "text": text_val,
                "detail_link": detail_link,
                "url": detail_link,
                "source_url": target_url,
                "item_index": idx + 1,
            }

            price_match = re.search(r"([£$€₹¥]\s*[\d,]+\.?\d*)", el.get_text(" ", strip=True))
            if price_match:
                rec["price_raw"] = price_match.group(1)

            records.append(rec)

    # If no repeating containers found, extract document sections (headings + paragraphs)
    if not records:
        sections = main_scope.find_all(["h1", "h2", "h3"])
        for idx, h in enumerate(sections[:25]):
            heading_text = h.get_text(strip=True)
            if not heading_text or len(heading_text) < 3:
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
        body_text = main_scope.get_text(" ", strip=True)[:400] or page_desc or "No text content found"
        records.append({
            "title": page_title or "Web Page Document",
            "text": body_text,
            "detail_link": target_url,
            "url": target_url,
            "source_url": target_url,
            "item_index": 1,
        })

    return records


def matches_content_type(record: dict, content_type: str) -> bool:
    """Check if record matches an optional content or product type filter."""
    if not content_type or not isinstance(content_type, str):
        return True

    ct = content_type.lower().strip()
    if not ct:
        return True

    title = str(record.get("title", "")).lower()
    desc = str(record.get("description", record.get("text", ""))).lower()
    rec_type = str(record.get("content_type", "")).lower()
    full_haystack = f"{title} {desc} {rec_type}"

    if ct in ("jeans", "denim"):
        keywords = ("jean", "denim")
        return any(k in full_haystack for k in keywords)
    elif ct in ("bottoms", "bottom"):
        keywords = ("bottom", "trouser", "pant", "skirt", "short", "jean", "jogger", "denim", "cargo", "legging")
        return any(k in full_haystack for k in keywords)
    elif ct in ("books", "book"):
        keywords = ("book", "novel", "author", "edition", "paperback", "hardcover", "volume", "literature")
        return any(k in full_haystack for k in keywords)
    elif ct in ("news", "article", "articles"):
        keywords = ("news", "article", "story", "report", "headline", "post", "update")
        return any(k in full_haystack for k in keywords)
    else:
        return ct in full_haystack


def extract_embedded_json_records(html_content: str, site_config: dict) -> list:
    """
    Extract structured records from modern client-side Single Page Application (SPA) JSON states:
    1. window.$preData (Savana ICE framework, goodsList, pagelist-activity, item detail)
    2. window.__NEXT_DATA__ (Next.js server-hydrated pages)
    3. application/ld+json (Schema.org Product, Article, ItemList)
    """
    records = []
    base_url = site_config.get("base_url", "")
    target_url = site_config.get("target_url", base_url)
    display_name = site_config.get("site_name", "")
    target_id = site_config.get("site_id", "")
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Parse Savana window.$preData
    prefix = "window.$preData = "
    pos = html_content.find(prefix)
    if pos != -1:
        try:
            decoder = json.JSONDecoder()
            pre_data, _ = decoder.raw_decode(html_content[pos + len(prefix):])
            if isinstance(pre_data, dict):
                # Check for single-product detail view
                detail_obj = None
                for k, v in pre_data.items():
                    if isinstance(v, dict) and ("goodsName" in v or "goodsId" in v):
                        detail_obj = v
                        break
                    elif isinstance(v, dict):
                        for sub_k, sub_v in v.items():
                            if isinstance(sub_v, dict) and ("goodsName" in sub_v or "goodsId" in sub_v):
                                detail_obj = sub_v
                                break

                # Check for listing / pagelist items
                goods_list = []
                for k, v in pre_data.items():
                    if isinstance(v, dict):
                        if "goodsList" in v and isinstance(v["goodsList"], list):
                            goods_list.extend(v["goodsList"])
                        elif "itemList" in v and isinstance(v["itemList"], list):
                            goods_list.extend(v["itemList"])
                    elif isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict) and ("goodsId" in v[0] or "goodsName" in v[0]):
                        goods_list.extend(v)

                if goods_list:
                    logger.info("Found %d items in embedded preData goods list", len(goods_list))
                    for idx, g in enumerate(goods_list):
                        if not isinstance(g, dict):
                            continue
                        gid = g.get("goodsId") or g.get("id")
                        gname = g.get("goodsName") or g.get("shortGoodsName") or g.get("title") or f"Product {gid}"
                        sale_p = g.get("promotePrice") or g.get("salePrice") or g.get("price")
                        sale_p_text = g.get("promotePriceText") or g.get("salePriceText") or str(sale_p or "")
                        g_url = urljoin(base_url, f"/details/{gid}") if gid else target_url
                        desc = g.get("copywritting") or g.get("goodsDesc") or gname
                        images = g.get("imageList") or []
                        thumb = ""
                        if images and isinstance(images, list) and isinstance(images[0], dict):
                            thumb = images[0].get("goodsThumb") or images[0].get("colorPic") or ""

                        rec = {
                            "target_id": target_id,
                            "display_name": display_name,
                            "title": gname,
                            "price": float(sale_p) if isinstance(sale_p, (int, float)) else 0.0,
                            "price_raw": sale_p_text,
                            "url": g_url,
                            "detail_link": g_url,
                            "description": desc,
                            "text": desc,
                            "content_type": "jeans" if "jean" in gname.lower() or "denim" in gname.lower() else "fashion",
                            "scraped_at": now_iso,
                            "metadata": {
                                "goods_id": gid,
                                "discount": g.get("discountValueText"),
                                "thumbnail": thumb,
                            }
                        }
                        records.append(rec)
                elif detail_obj:
                    gid = detail_obj.get("goodsId") or detail_obj.get("id")
                    gname = detail_obj.get("goodsName") or detail_obj.get("shortGoodsName") or detail_obj.get("title") or "Product Detail"
                    sale_p = detail_obj.get("promotePrice") or detail_obj.get("salesPrice") or detail_obj.get("price")
                    sale_p_text = detail_obj.get("promotePriceText") or detail_obj.get("salesPriceText") or str(sale_p or "")
                    g_url = target_url
                    desc = detail_obj.get("goodsDesc") or gname
                    records.append({
                        "target_id": target_id,
                        "display_name": display_name,
                        "title": gname,
                        "price": float(sale_p) if isinstance(sale_p, (int, float)) else 0.0,
                        "price_raw": sale_p_text,
                        "url": g_url,
                        "detail_link": g_url,
                        "description": desc,
                        "text": desc,
                        "content_type": "jeans" if "jean" in gname.lower() or "denim" in gname.lower() else "fashion",
                        "scraped_at": now_iso,
                        "metadata": {
                            "goods_id": gid,
                            "discount": detail_obj.get("discountValueText"),
                            "is_single_product": True,
                        }
                    })
        except Exception as e:
            logger.warning("Error parsing window.$preData: %s", str(e))

    # 2. Parse Next.js __NEXT_DATA__
    if not records and "__NEXT_DATA__" in html_content:
        m_next = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html_content, re.DOTALL)
        if m_next:
            try:
                next_json = json.loads(m_next.group(1))
                page_props = next_json.get("props", {}).get("pageProps", {})

                def find_items_array(obj):
                    if isinstance(obj, list) and len(obj) > 0 and isinstance(obj[0], dict):
                        sample = obj[0]
                        if any(k in sample for k in ("name", "title", "headline", "goodsName")):
                            return obj
                    elif isinstance(obj, dict):
                        for k, v in obj.items():
                            res = find_items_array(v)
                            if res:
                                return res
                    return None

                items_arr = find_items_array(page_props)
                if items_arr:
                    for idx, it in enumerate(items_arr[:100]):
                        t = it.get("title") or it.get("name") or it.get("headline") or f"Item {idx+1}"
                        p_val = it.get("price") or it.get("salePrice") or 0.0
                        u = it.get("url") or it.get("link") or target_url
                        records.append({
                            "target_id": target_id,
                            "display_name": display_name,
                            "title": t,
                            "price": float(p_val) if isinstance(p_val, (int, float)) else 0.0,
                            "price_raw": str(p_val),
                            "url": urljoin(base_url, str(u)),
                            "detail_link": urljoin(base_url, str(u)),
                            "description": it.get("description") or t,
                            "text": it.get("description") or t,
                            "content_type": it.get("type", "item"),
                            "scraped_at": now_iso,
                            "metadata": {k: v for k, v in it.items() if k not in ("title", "name", "price", "url")},
                        })
            except Exception as e:
                logger.warning("Error parsing __NEXT_DATA__: %s", str(e))

    # 3. Parse Schema.org JSON-LD
    if not records and "application/ld+json" in html_content:
        soup_ld = BeautifulSoup(html_content, "html.parser")
        ld_scripts = soup_ld.find_all("script", type="application/ld+json")
        for s in ld_scripts:
            try:
                ld_data = json.loads(s.string) if s.string else None
                if not ld_data:
                    continue
                items_to_eval = ld_data if isinstance(ld_data, list) else [ld_data]
                for item in items_to_eval:
                    item_type = str(item.get("@type", ""))
                    if "Product" in item_type or "Article" in item_type or "NewsArticle" in item_type:
                        t = item.get("name") or item.get("headline") or item.get("title")
                        if not t:
                            continue
                        desc = item.get("description") or t
                        p_val = 0.0
                        if "offers" in item and isinstance(item["offers"], dict):
                            p_val = item["offers"].get("price", 0.0)
                        u = item.get("url") or target_url
                        records.append({
                            "target_id": target_id,
                            "display_name": display_name,
                            "title": t,
                            "price": float(p_val) if isinstance(p_val, (int, float)) else 0.0,
                            "price_raw": str(p_val),
                            "url": urljoin(base_url, str(u)),
                            "detail_link": urljoin(base_url, str(u)),
                            "description": desc,
                            "text": desc,
                            "content_type": "product" if "Product" in item_type else "article",
                            "scraped_at": now_iso,
                            "metadata": item,
                        })
            except Exception:
                pass

    return records


def parse_html_records(html_content: str, site_config: dict) -> list:
    """Parse raw HTML content into extracted record dictionaries based on configured selectors, embedded JSON, or generic mode."""
    soup = BeautifulSoup(html_content, "html.parser")
    container_selector = site_config.get("container_selector")
    fields = site_config.get("fields", {})
    base_url = site_config.get("base_url", "")
    target_url = site_config.get("target_url", base_url)
    display_name = site_config.get("site_name", "")
    target_id = site_config.get("site_id", "")
    content_type_filter = site_config.get("content_type") or ""
    extraction_type = site_config.get("extraction_type", "custom" if container_selector else "generic")

    records = []

    # 1. If custom container selector specified and mode is custom, attempt selector extraction
    if container_selector and extraction_type == "custom":
        containers = soup.select(container_selector)
        logger.info("Found %d items matching container selector '%s'", len(containers), container_selector)
        if len(containers) > 0:
            for container in containers:
                record = {
                    "target_id": target_id,
                    "site_id": target_id,
                    "display_name": display_name,
                    "site_name": display_name,
                }
                for field_name, field_cfg in fields.items():
                    record[field_name] = extract_field_value(container, field_cfg, base_url)
                if "url" not in record and "detail_link" in record:
                    record["url"] = record["detail_link"]
                if "source_url" not in record:
                    record["source_url"] = target_url
                records.append(record)

    # 2. If no custom selectors or 0 matched, check for embedded SPA JSON (Savana, Next.js, JSON-LD)
    if not records:
        embedded = extract_embedded_json_records(html_content, site_config)
        if embedded:
            records = embedded
            logger.info("Extracted %d records via embedded JSON parser", len(records))

    # 3. If still no records, run generic heuristic HTML DOM extraction
    if not records:
        records = extract_generic_html_records(soup, base_url, target_url)
        for r in records:
            r["target_id"] = target_id
            r["site_id"] = target_id
            r["display_name"] = display_name
            r["site_name"] = display_name

    # 4. Apply content_type filtering if specified
    if content_type_filter and records:
        matching = [r for r in records if matches_content_type(r, content_type_filter)]
        logger.info(
            "Content-type filter '%s' matched %d of %d total extracted records",
            content_type_filter,
            len(matching),
            len(records),
        )
        if matching:
            records = matching
        else:
            logger.warning(
                "Filter '%s' matched 0 records. Retaining all %d records to prevent empty dataset failure.",
                content_type_filter,
                len(records),
            )

    return records



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

    # Support preflight check action directly through scraper handler
    if event.get("action") == "preflight" or event.get("preflight"):
        preflight_url = event.get("target_url") or event.get("url") or ""
        preflight_timeout = int(event.get("timeout_seconds", 8))
        return run_preflight_check(preflight_url, timeout=preflight_timeout)

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
    content_type = event.get("content_type") or event.get("product_type") or site_config.get("content_type", "")
    site_config["content_type"] = content_type
    site_config["site_name"] = event.get("display_name") or event.get("site_name") or site_config.get("site_name", site_id)
    site_config["site_id"] = site_id
    robots_ok = True

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
        robots_ok = check_robots_allowed(base_url, target_url)
        if not robots_ok:
            logger.warning("Scraping disallowed by robots.txt for URL: %s (Advisory warning for on-demand scrape)", target_url)
            if site_config.get("enforce_robots", False) or event.get("strict_robots", False):
                return {
                    "statusCode": 403,
                    "status": "FAILURE",
                    "site_id": site_id,
                    "target_url": target_url,
                    "error": "Scraping disallowed by target website robots.txt policy (Strict mode active).",
                    "error_type": "ROBOTS_DISALLOWED",
                    "is_retryable": False,
                }

        # 3. Fetch initial page with redirect SSRF validation
        try:
            response = fetch_page_content(target_url, timeout=timeout)
            html_content = response.text
            http_status = response.status_code
        except requests.exceptions.HTTPError as he:
            resp_status = he.response.status_code if getattr(he, "response", None) is not None else 500
            if resp_status in (401, 403):
                err_msg = (
                    f"HTTP {resp_status} Forbidden: Target server refused access (authentication required or anti-bot protection active). "
                    f"The website cannot be scraped via automated HTTP ingestion."
                )
                err_code = 403
                is_retryable = False
                err_type = "ACCESS_DENIED"
            elif resp_status == 404:
                err_msg = f"HTTP 404 Not Found: The requested URL was not found on remote server."
                err_code = 404
                is_retryable = False
                err_type = "NOT_FOUND"
            elif resp_status == 429:
                err_msg = f"HTTP 429 Too Many Requests: Rate limit exceeded on target host. Try again later."
                err_code = 429
                is_retryable = True
                err_type = "RATE_LIMITED"
            else:
                err_msg = f"HTTP {resp_status} Server Error: {str(he)}"
                err_code = 502
                is_retryable = True
                err_type = "SERVER_ERROR"

            logger.error("HTTP error for URL %s: %s", target_url, err_msg)
            return {
                "statusCode": err_code,
                "status": "FAILURE",
                "site_id": site_id,
                "target_url": target_url,
                "scraped_at": timestamp,
                "error": err_msg,
                "error_type": err_type,
                "is_retryable": is_retryable,
            }
        except requests.exceptions.Timeout as te:
            logger.error("Timeout fetching URL %s: %s", target_url, str(te))
            return {
                "statusCode": 504,
                "status": "FAILURE",
                "site_id": site_id,
                "target_url": target_url,
                "scraped_at": timestamp,
                "error": f"Connection timed out after {timeout} seconds: Target host did not respond in time.",
                "error_type": "TIMEOUT",
                "is_retryable": True,
            }
        except requests.exceptions.RequestException as e:
            logger.error("Scraping request failed for URL %s: %s", target_url, str(e))
            resp_code = e.response.status_code if getattr(e, "response", None) is not None else 502
            is_forbidden = resp_code in (401, 403) or "403" in str(e) or "401" in str(e)
            is_not_found = resp_code in (404, 410) or "404" in str(e)
            is_retryable = not is_forbidden and not is_not_found
            return {
                "statusCode": 403 if is_forbidden else (404 if is_not_found else 502),
                "status": "FAILURE",
                "site_id": site_id,
                "target_url": target_url,
                "scraped_at": timestamp,
                "error": f"HTTP request failed: {str(e)}",
                "error_type": "ACCESS_DENIED" if is_forbidden else "REQUEST_EXCEPTION",
                "is_retryable": is_retryable,
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
                "error_type": "UNHANDLED_EXCEPTION",
                "is_retryable": False,
            }

        # Check for active anti-bot challenge or client-side SPA rendering requirement
        is_incompatible, diag_reason = detect_page_incompatibility(html_content, http_status)
        if is_incompatible:
            logger.warning("Incompatible page structure detected for %s: %s", target_url, diag_reason)
            return {
                "statusCode": 422,
                "status": "FAILURE",
                "site_id": site_id,
                "target_url": target_url,
                "scraped_at": timestamp,
                "error": diag_reason,
                "error_type": "JS_RENDER_OR_CHALLENGE_REQUIRED",
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
        "robots_allowed": robots_ok,
        "content_type": content_type,
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
        "target_id": site_id,
        "site_name": site_config.get("site_name", site_id),
        "display_name": site_config.get("site_name", site_id),
        "target_url": target_url,
        "scraped_at": timestamp,
        "raw_s3_key": raw_s3_key,
        "records_count": len(records),
        "pages_scraped": pages_scraped,
        "records": records,
        "content_type": content_type,
        "robots_allowed": robots_ok,
        "config_override": site_config,
        "extraction_type": site_config.get("extraction_type", "generic"),
    }


if __name__ == "__main__":
    test_event = {"site_id": "books_toscrape"}
    result = lambda_handler(test_event)
    print(f"Scraped {result.get('records_count', 0)} records from {result.get('site_id')}")
    if result.get("records"):
        print("Sample record:", json.dumps(result["records"][0], indent=2))
