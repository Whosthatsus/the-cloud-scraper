"""
The Cloud Scraper - Data Transformation and Cleaning Lambda Function
Cleans raw scraped records, normalizes fields (prices, ratings, URLs, text),
performs deterministic deduplication via SHA-256 hashing, and structures
standardized JSON records for storage.
"""

import re
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

WORD_TO_NUMBER_RATING = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
}


def clean_text(text: Any) -> Any:
    """Trim whitespace, normalize unicode characters, and clean strings."""
    if not isinstance(text, str):
        return text
    # Clean mojibake currency symbols like 'Â£' -> '£'
    cleaned = text.replace("\u00c2\u00a3", "£").replace("Â£", "£")
    # Replace non-breaking spaces and redundant whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def parse_price(price_raw: Any) -> float:
    """Extract numeric float value from a price string (e.g., '£51.77' -> 51.77)."""
    if price_raw is None:
        return 0.0
    if isinstance(price_raw, (int, float)):
        return float(price_raw)
    price_str = clean_text(str(price_raw))
    # Extract digits and decimal point
    match = re.search(r"(\d+(?:\.\d+)?)", price_str)
    if match:
        return float(match.group(1))
    return 0.0


def parse_rating(rating_raw: Any) -> int:
    """Normalize rating strings (e.g., 'star-rating Three' -> 3)."""
    if rating_raw is None:
        return 0
    if isinstance(rating_raw, int):
        return rating_raw
    text = clean_text(str(rating_raw)).lower()
    for word, number in WORD_TO_NUMBER_RATING.items():
        if word in text:
            return number
    # Check for direct numeric digit
    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1))
    return 0


def generate_content_hash(record: Dict[str, Any], site_id: str) -> str:
    """
    Generate a deterministic SHA-256 fingerprint hash of record identifying fields.
    Prevents duplicate storage across scraping runs.
    """
    id_parts = [site_id]
    if "detail_link" in record and record["detail_link"]:
        id_parts.append(str(record["detail_link"]).strip().lower())
    elif "url" in record and record["url"]:
        id_parts.append(str(record["url"]).strip().lower())
    elif "quote" in record and record["quote"]:
        id_parts.append(str(record["quote"]).strip().lower())
        id_parts.append(str(record.get("author", "")).strip().lower())
    elif "title" in record and record["title"]:
        id_parts.append(str(record["title"]).strip().lower())
        if "text" in record and record["text"]:
            id_parts.append(str(record["text"])[:60].strip().lower())
    else:
        # Fallback to sorted key-value string
        sorted_items = sorted((k, str(v)) for k, v in record.items() if v is not None and k not in ("scraped_at", "transformed_at"))
        id_parts.extend([f"{k}:{v}" for k, v in sorted_items])

    composite_key = "|".join(id_parts)
    return hashlib.sha256(composite_key.encode("utf-8")).hexdigest()


def clean_and_normalize_record(
    raw_record: Dict[str, Any], site_id: str, source_url: str, scraped_at: str
) -> Dict[str, Any]:
    """Clean and normalize individual record fields into standard structure."""
    transformed = {}
    for key, val in raw_record.items():
        if key == "price":
            transformed["price"] = parse_price(val)
            transformed["price_raw"] = clean_text(val)
        elif key == "rating":
            transformed["rating"] = parse_rating(val)
            transformed["rating_raw"] = clean_text(val)
        elif isinstance(val, list):
            transformed[key] = [clean_text(item) for item in val if item]
        else:
            transformed[key] = clean_text(val)

    # Compute deduplication hash and record metadata
    content_hash = generate_content_hash(transformed, site_id)
    record_id = f"{site_id}#{content_hash[:16]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    transformed["record_id"] = record_id
    transformed["content_hash"] = content_hash
    transformed["site_id"] = site_id
    transformed["source_url"] = source_url or transformed.get("url") or transformed.get("detail_link", "")
    transformed["scraped_at"] = scraped_at or now_iso
    transformed["transformed_at"] = now_iso

    return transformed


def deduplicate_records(
    records: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Remove duplicates within the current batch using content hash.
    Returns (unique_records, duplicate_records).
    """
    seen_hashes = set()
    unique = []
    duplicates = []

    for r in records:
        c_hash = r.get("content_hash")
        if c_hash in seen_hashes:
            duplicates.append(r)
        else:
            seen_hashes.add(c_hash)
            unique.append(r)

    return unique, duplicates


def lambda_handler(event, context=None):
    """
    Lambda Handler for Data Transformation and Deduplication.
    Receives raw records output from scraper / validation Lambda.
    """
    logger.info("Transformation handler received event with status: %s", event.get("status"))

    raw_records = event.get("records", [])
    site_id = event.get("site_id", "unknown_site")
    source_url = event.get("target_url", "")
    scraped_at = event.get("scraped_at", "")
    config_override = event.get("config_override")

    if not raw_records:
        return {
            "statusCode": 200,
            "status": "SUCCESS",
            "site_id": site_id,
            "total_raw": 0,
            "total_transformed": 0,
            "duplicates_removed": 0,
            "records": [],
            "message": "No records to transform",
            "config_override": config_override,
        }

    # Transform and clean each record
    transformed_records = [
        clean_and_normalize_record(r, site_id, source_url, scraped_at) for r in raw_records
    ]

    # Deduplicate
    unique_records, duplicate_records = deduplicate_records(transformed_records)

    logger.info(
        "Transformation complete: %d raw -> %d unique (%d duplicates removed)",
        len(raw_records),
        len(unique_records),
        len(duplicate_records),
    )

    return {
        "statusCode": 200,
        "status": "SUCCESS",
        "site_id": site_id,
        "site_name": event.get("site_name", site_id),
        "target_url": source_url,
        "scraped_at": scraped_at,
        "raw_s3_key": event.get("raw_s3_key", ""),
        "total_raw": len(raw_records),
        "total_transformed": len(unique_records),
        "duplicates_removed": len(duplicate_records),
        "records": unique_records,
        "config_override": config_override,
        "extraction_type": event.get("extraction_type", "generic"),
    }


if __name__ == "__main__":
    sample_raw = [
        {
            "title": "  A Light in the Attic  ",
            "price": "Â£51.77",
            "availability": "In stock",
            "rating": "star-rating Three",
            "detail_link": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        },
        {
            "title": "A Light in the Attic",
            "price": "£51.77",
            "availability": "In stock",
            "rating": "Three",
            "detail_link": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        },
    ]
    res = lambda_handler(
        {
            "site_id": "books_toscrape",
            "target_url": "https://books.toscrape.com/",
            "records": sample_raw,
        }
    )
    print("Transformed:", json.dumps(res, indent=2))
