"""
The Cloud Scraper - DynamoDB & S3 Storage Lambda Function
Persists cleaned, structured records and metadata to Amazon DynamoDB
and archives transformed JSON dataset into Amazon S3.

Includes conditional writes for deduplication in DynamoDB,
target configuration persistence and retrieval, and distinguishes
between live AWS execution and local offline development testing.
"""

import os
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, NoRegionError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "ap-southeast-2"))


def is_running_in_aws() -> bool:
    """Detect whether code is running inside an active AWS Lambda execution environment."""
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or os.environ.get("AWS_EXECUTION_ENV"))


def convert_floats_to_decimals(obj):
    """DynamoDB requires Decimal for floating point numbers."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_floats_to_decimals(v) for v in obj]
    return obj


def convert_decimals_to_floats(obj):
    """Helper to convert Decimals back to standard floats for JSON serialization."""
    if isinstance(obj, Decimal):
        # Convert integers if no fractional part
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    if isinstance(obj, dict):
        return {k: convert_decimals_to_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_decimals_to_floats(v) for v in obj]
    return obj


def save_transformed_json_to_s3(
    bucket_name: str, site_id: str, timestamp_str: str, records: list, metadata: dict
) -> tuple:
    """
    Save transformed structured JSON dataset to S3 under transform/ folder.
    Returns (s3_key, error_message).
    """
    if not bucket_name:
        return "", None

    try:
        s3_client = boto3.client("s3", region_name=DEFAULT_REGION)
        s3_key = f"transform/{site_id}/{timestamp_str}/records.json"
        meta_key = f"transform/{site_id}/{timestamp_str}/metadata.json"

        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json.dumps(records, indent=2).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        s3_client.put_object(
            Bucket=bucket_name,
            Key=meta_key,
            Body=json.dumps(metadata, indent=2).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        logger.info("Archived transformed JSON to s3://%s/%s", bucket_name, s3_key)
        return s3_key, None
    except Exception as e:
        if is_running_in_aws():
            logger.error("AWS S3 put_object failed in production: %s", str(e))
            return "", f"S3 put_object failed: {str(e)}"
        else:
            logger.info("Local offline mode: S3 storage skipped (%s)", str(e))
            return "", None


def store_records_in_dynamodb(table_name: str, records: list) -> tuple:
    """
    Store records in Amazon DynamoDB using conditional writes to safeguard
    against overwriting existing records.
    Returns (new_stored_count, existing_count, error_message).
    """
    if not table_name:
        return 0, 0, "No DynamoDB table name specified."

    new_stored_count = 0
    existing_count = 0

    try:
        dynamodb = boto3.resource("dynamodb", region_name=DEFAULT_REGION)
        table = dynamodb.Table(table_name)

        for r in records:
            item = convert_floats_to_decimals(r)
            try:
                # Conditional write: only put item if record_id does not already exist
                table.put_item(
                    Item=item,
                    ConditionExpression="attribute_not_exists(record_id)",
                )
                new_stored_count += 1
            except ClientError as ce:
                error_code = ce.response.get("Error", {}).get("Code", "")
                if error_code == "ConditionalCheckFailedException":
                    # Item already exists in table; duplicate prevented
                    existing_count += 1
                    logger.debug("Record already exists in DynamoDB: %s", r.get("record_id"))
                else:
                    if is_running_in_aws():
                        logger.error("DynamoDB put_item ClientError in AWS: %s", str(ce))
                        return new_stored_count, existing_count, f"DynamoDB error: {str(ce)}"
                    else:
                        logger.warning("Local test ClientError: %s", str(ce))

        logger.info(
            "DynamoDB storage summary: %d new inserted, %d already existing in table %s",
            new_stored_count,
            existing_count,
            table_name,
        )
        return new_stored_count, existing_count, None

    except (NoCredentialsError, NoRegionError) as nce:
        if is_running_in_aws():
            logger.error("Missing AWS credentials in Lambda execution environment: %s", str(nce))
            return 0, 0, f"Credentials error in AWS: {str(nce)}"
        else:
            logger.info("Local offline mode: DynamoDB storage simulated (%s)", str(nce))
            return 0, 0, None
    except Exception as e:
        if is_running_in_aws():
            logger.error("Unexpected error storing records in DynamoDB: %s", str(e))
            return new_stored_count, existing_count, str(e)
        else:
            logger.info("Local offline mode: %s", str(e))
            return 0, 0, None


def save_target_config(table_name: str, target_config: dict) -> tuple:
    """Save or update a target configuration in the DynamoDB configuration store."""
    if not table_name:
        return False, "No DynamoDB table name specified."

    target_id = target_config.get("site_id") or target_config.get("target_id")
    if not target_id:
        return False, "Target configuration requires a valid site_id or target_id."

    try:
        dynamodb = boto3.resource("dynamodb", region_name=DEFAULT_REGION)
        table = dynamodb.Table(table_name)
        now_iso = datetime.now(timezone.utc).isoformat()

        item = {
            "site_id": f"CONFIG#{target_id}",
            "record_id": "TARGET_CONFIG",
            "target_id": target_id,
            "site_name": target_config.get("site_name", target_id),
            "target_url": target_config.get("target_url", ""),
            "base_url": target_config.get("base_url", target_config.get("target_url", "")),
            "extraction_type": target_config.get("extraction_type", "generic"),
            "container_selector": target_config.get("container_selector", ""),
            "next_page_selector": target_config.get("next_page_selector", ""),
            "fields_json": json.dumps(target_config.get("fields", {})),
            "validation_json": json.dumps(target_config.get("validation_rules", {})),
            "timeout_seconds": int(target_config.get("timeout_seconds", 15)),
            "page_limit": int(target_config.get("page_limit", 1)),
            "enabled": bool(target_config.get("enabled", True)),
            "updated_at": now_iso,
        }
        table.put_item(Item=convert_floats_to_decimals(item))
        logger.info("Successfully persisted target config for '%s' in DynamoDB", target_id)
        return True, None
    except Exception as e:
        logger.error("Failed saving target config to DynamoDB: %s", str(e))
        return False, str(e)


def list_target_configs(table_name: str) -> list:
    """List all persisted target configurations from DynamoDB."""
    if not table_name:
        return []
    try:
        dynamodb = boto3.resource("dynamodb", region_name=DEFAULT_REGION)
        table = dynamodb.Table(table_name)
        resp = table.scan(
            FilterExpression="record_id = :cfg",
            ExpressionAttributeValues={":cfg": "TARGET_CONFIG"},
        )
        items = resp.get("Items", [])
        results = []
        for it in items:
            it = convert_decimals_to_floats(it)
            fields_val = {}
            if "fields_json" in it and isinstance(it["fields_json"], str):
                try:
                    fields_val = json.loads(it["fields_json"])
                except Exception:
                    pass
            val_rules = {}
            if "validation_json" in it and isinstance(it["validation_json"], str):
                try:
                    val_rules = json.loads(it["validation_json"])
                except Exception:
                    pass
            results.append({
                "site_id": it.get("target_id", it.get("site_id", "").replace("CONFIG#", "")),
                "site_name": it.get("site_name", ""),
                "target_url": it.get("target_url", ""),
                "base_url": it.get("base_url", ""),
                "extraction_type": it.get("extraction_type", "generic"),
                "container_selector": it.get("container_selector", ""),
                "next_page_selector": it.get("next_page_selector", ""),
                "fields": fields_val,
                "validation_rules": val_rules,
                "timeout_seconds": it.get("timeout_seconds", 15),
                "page_limit": it.get("page_limit", 1),
                "enabled": it.get("enabled", True),
                "updated_at": it.get("updated_at", ""),
            })
        return results
    except Exception as e:
        logger.warning("Could not list target configs from DynamoDB: %s", str(e))
        return []


def get_stored_records(table_name: str, site_id: str = None, limit: int = 100) -> list:
    """Retrieve actual stored scraped records from DynamoDB."""
    if not table_name:
        return []
    try:
        dynamodb = boto3.resource("dynamodb", region_name=DEFAULT_REGION)
        table = dynamodb.Table(table_name)
        if site_id and site_id != "all":
            resp = table.query(
                KeyConditionExpression="site_id = :sid",
                ExpressionAttributeValues={":sid": site_id},
                Limit=limit,
            )
        else:
            resp = table.scan(
                FilterExpression="record_id <> :cfg",
                ExpressionAttributeValues={":cfg": "TARGET_CONFIG"},
                Limit=limit,
            )
        items = resp.get("Items", [])
        return [convert_decimals_to_floats(item) for item in items if item.get("record_id") != "TARGET_CONFIG"]
    except Exception as e:
        logger.warning("Could not query stored records from DynamoDB: %s", str(e))
        return []


def lambda_handler(event, context=None):
    """
    Lambda Handler for DynamoDB and S3 Storage.
    Receives transformed records from transformation Lambda.
    """
    logger.info("Storage handler received event for site: %s", event.get("site_id"))

    records = event.get("records", [])
    site_id = event.get("site_id", "unknown_site")
    config_override = event.get("config_override")

    if not is_running_in_aws():
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{site_id}.json")
        with open(output_path, "w", encoding="utf-8") as output_file:
            json.dump(records, output_file, indent=2, ensure_ascii=False)
        logger.info("Saved %d records locally to %s", len(records), output_path)

    table_name = os.environ.get("DYNAMODB_TABLE_NAME", event.get("dynamodb_table", "TheCloudScraper-Records"))
    bucket_name = os.environ.get("S3_BUCKET_NAME", event.get("bucket_name", ""))
    target_url = event.get("target_url", "")
    scraped_at = event.get("scraped_at", "")
    raw_s3_key = event.get("raw_s3_key", "")

    timestamp_folder = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    now_iso = datetime.now(timezone.utc).isoformat()

    metadata = {
        "site_id": site_id,
        "site_name": event.get("site_name", site_id),
        "target_url": target_url,
        "scraped_at": scraped_at,
        "stored_at": now_iso,
        "raw_s3_key": raw_s3_key,
        "total_transformed_records": len(records),
        "duplicates_removed": event.get("duplicates_removed", 0),
    }

    # 1. Save transformed JSON in S3
    transformed_s3_key, s3_error = save_transformed_json_to_s3(
        bucket_name=bucket_name,
        site_id=site_id,
        timestamp_str=timestamp_folder,
        records=records,
        metadata=metadata,
    )

    # 2. Store records in DynamoDB with conditional write deduplication
    new_stored, existing_found, ddb_error = store_records_in_dynamodb(table_name, records)

    # In AWS production, if an error occurred, fail the state so Step Functions catches it
    if is_running_in_aws() and (s3_error or ddb_error):
        error_msg = "; ".join(filter(None, [s3_error, ddb_error]))
        logger.error("Production storage failed: %s", error_msg)
        return {
            "statusCode": 500,
            "status": "FAILURE",
            "Storage": "FAILURE",
            "site_id": site_id,
            "error": error_msg,
            "records_stored_dynamodb": new_stored,
            "existing_records_dynamodb": existing_found,
            "config_override": config_override,
        }

    in_aws = is_running_in_aws()
    storage_mode = "AWS_PRODUCTION" if in_aws else "OFFLINE_LOCAL_MODE"

    return {
        "statusCode": 200,
        "status": "SUCCESS",
        "Storage": "SUCCESS",
        "storage_mode": storage_mode,
        "site_id": site_id,
        "site_name": event.get("site_name", site_id),
        "target_url": target_url,
        "scraped_at": scraped_at,
        "raw_s3_key": raw_s3_key,
        "transformed_s3_key": transformed_s3_key,
        "dynamodb_table": table_name,
        "records_count": len(records),
        "records_stored_dynamodb": new_stored if in_aws else 0,
        "existing_records_dynamodb": existing_found,
        "duplicates_removed": event.get("duplicates_removed", 0),
        "config_override": config_override,
        "summary": (
            f"Stored {new_stored} new records in DynamoDB (found {existing_found} existing)"
            if in_aws
            else f"Local offline validation: {len(records)} records prepared for DynamoDB"
        ),
    }


if __name__ == "__main__":
    sample_records = [
        {
            "record_id": "books_toscrape#abc12345",
            "site_id": "books_toscrape",
            "title": "A Light in the Attic",
            "price": 51.77,
            "rating": 3,
            "content_hash": "abc1234567890",
            "source_url": "https://books.toscrape.com/",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
    ]
    res = lambda_handler(
        {
            "site_id": "books_toscrape",
            "records": sample_records,
            "dynamodb_table": "TheCloudScraper-Records",
        }
    )
    print("Storage result:", json.dumps(res, indent=2))
