"""
The Cloud Scraper - Data Validation and Cleaning Lambda Function
Validates scraped records against declarative schema rules, filters
malformed records, supports generic HTML record validation,
and enforces data quality standards before transformation.
"""

import os
import json
import logging
from typing import Dict, List, Any, Tuple
from urllib.parse import urlparse

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def load_validation_rules(site_id: str) -> dict:
    """Load validation rules for site from config."""
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
                    data = json.load(f)
                    for site in data.get("sites", []):
                        if site.get("site_id") == site_id:
                            return site.get("validation_rules", {})
            except Exception as e:
                logger.warning("Could not read config at %s: %s", cp, str(e))
    return {}


def is_valid_url(url: Any) -> bool:
    """Check if value is a valid HTTP/HTTPS URL."""
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def validate_single_record(
    record: Dict[str, Any], validation_rules: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """
    Validate an individual record against declarative rules or generic criteria.
    Returns (is_valid, list_of_error_reasons).
    """
    errors = []

    if not isinstance(record, dict) or not record:
        return False, ["Record is empty or not a dictionary"]

    # 1. Required fields check
    required_fields = validation_rules.get("required_fields", [])
    if required_fields:
        for field in required_fields:
            val = record.get(field)
            if val is None or (isinstance(val, str) and not val.strip()) or (isinstance(val, list) and len(val) == 0):
                errors.append(f"Missing or empty required field: '{field}'")
    else:
        # Generic record validation: check that record has at least one meaningful field
        has_substance = any(
            bool(record.get(k))
            for k in ("title", "text", "summary", "quote", "url", "detail_link", "name", "author")
        )
        if not has_substance:
            errors.append("Record contains no identifiable content, title, text, or URL.")

    # 2. URL fields validation
    for key, val in record.items():
        if "link" in key.lower() or "url" in key.lower():
            if val is not None and not is_valid_url(val):
                errors.append(f"Invalid URL format for '{key}': '{val}'")

    # 3. Text length validation
    min_quote_length = validation_rules.get("min_quote_length")
    if min_quote_length and "quote" in record and isinstance(record["quote"], str):
        if len(record["quote"].strip()) < int(min_quote_length):
            errors.append(
                f"Quote text too short ({len(record['quote'].strip())} < {min_quote_length})"
            )

    min_title_length = validation_rules.get("min_title_length", 2)
    if "title" in record and isinstance(record["title"], str):
        if len(record["title"].strip()) < int(min_title_length):
            errors.append(f"Title text too short ({len(record['title'].strip())} < {min_title_length})")

    # 4. Price presence and structure check
    if "price" in record and record["price"] is not None:
        price_val = str(record["price"])
        if not any(char.isdigit() for char in price_val):
            errors.append(f"Price field contains no numeric digits: '{price_val}'")

    return (len(errors) == 0, errors)


def filter_and_validate_records(
    records: List[Dict[str, Any]], validation_rules: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Iterate through records, validating each and partitioning into valid and invalid sets.
    """
    valid_records = []
    invalid_records = []

    for idx, r in enumerate(records):
        is_valid, errors = validate_single_record(r, validation_rules)
        if is_valid:
            valid_records.append(r)
        else:
            invalid_entry = {
                "record_index": idx,
                "record": r,
                "errors": errors,
            }
            invalid_records.append(invalid_entry)
            logger.warning("Record %d validation failed: %s", idx, ", ".join(errors))

    return valid_records, invalid_records


def lambda_handler(event, context=None):
    """
    AWS Lambda Handler for Validation.
    Receives output from the scraper Lambda:
    {
      "site_id": "...",
      "records": [...],
      ...
    }
    """
    logger.info("Validation handler received event for site: %s", event.get("site_id"))

    site_id = event.get("site_id", "unknown_site")
    raw_records = event.get("records", [])
    config_override = event.get("config_override")

    target_id = event.get("target_id") or site_id
    display_name = event.get("display_name") or event.get("site_name", site_id)
    content_type = event.get("content_type", "")

    if not raw_records:
        logger.error("No records received in validation event for site: %s", site_id)
        return {
            "statusCode": 422,
            "status": "FAILURE",
            "Validation": "FAILURE",
            "site_id": site_id,
            "target_id": target_id,
            "site_name": display_name,
            "display_name": display_name,
            "content_type": content_type,
            "error": "No records found in scraper output to validate",
            "error_type": "ZERO_RECORDS_EXTRACTED",
            "total_scraped": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "records": [],
            "invalid_records": [],
            "config_override": config_override,
        }

    # Load validation rules from config_override or local config
    validation_rules = {}
    if config_override and isinstance(config_override, dict):
        validation_rules = dict(config_override.get("validation_rules", {}))
    if not validation_rules:
        validation_rules = load_validation_rules(site_id)
    if "validation_rules" in event and isinstance(event["validation_rules"], dict):
        validation_rules.update(event["validation_rules"])

    valid_records, invalid_records = filter_and_validate_records(raw_records, validation_rules)

    total_count = len(raw_records)
    valid_count = len(valid_records)
    invalid_count = len(invalid_records)

    logger.info(
        "Validation complete for %s: %d total, %d valid, %d invalid",
        site_id,
        total_count,
        valid_count,
        invalid_count,
    )

    # If all records are invalid, treat as pipeline failure
    if valid_count == 0:
        return {
            "statusCode": 422,
            "status": "FAILURE",
            "Validation": "FAILURE",
            "site_id": site_id,
            "target_id": target_id,
            "site_name": display_name,
            "display_name": display_name,
            "target_url": event.get("target_url", ""),
            "scraped_at": event.get("scraped_at", ""),
            "raw_s3_key": event.get("raw_s3_key", ""),
            "error": "All scraped records failed schema validation",
            "error_type": "VALIDATION_FAILED",
            "content_type": content_type,
            "total_scraped": total_count,
            "valid_count": 0,
            "invalid_count": invalid_count,
            "records": [],
            "invalid_records": invalid_records,
            "config_override": config_override,
            "extraction_type": event.get("extraction_type", "generic"),
        }

    return {
        "statusCode": 200,
        "status": "SUCCESS",
        "Validation": "SUCCESS",
        "site_id": site_id,
        "target_id": target_id,
        "site_name": display_name,
        "display_name": display_name,
        "target_url": event.get("target_url", ""),
        "scraped_at": event.get("scraped_at", ""),
        "raw_s3_key": event.get("raw_s3_key", ""),
        "content_type": content_type,
        "total_scraped": total_count,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "records": valid_records,
        "invalid_records": invalid_records,
        "config_override": config_override,
        "extraction_type": event.get("extraction_type", "generic"),
    }


if __name__ == "__main__":
    sample_records = [
        {
            "title": "A Light in the Attic",
            "price": "£51.77",
            "detail_link": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        },
        {
            "title": "",
            "price": "N/A",
            "detail_link": "not-a-valid-url",
        },
    ]
    res = lambda_handler({"site_id": "books_toscrape", "records": sample_records})
    print(f"Validation result: {res['Validation']} - {res['valid_count']} valid, {res['invalid_count']} invalid")
    print(json.dumps(res, indent=2))
