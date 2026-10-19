"""
The Cloud Scraper - DynamoDB & S3 Storage Lambda Function
Persists cleaned, structured records and metadata to Amazon DynamoDB
and archives transformed JSON dataset into Amazon S3.
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

DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))


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
        return float(obj)
    if isinstance(obj, dict):
        return {k: convert_decimals_to_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_decimals_to_floats(v) for v in obj]
    return obj


def save_transformed_json_to_s3(
    bucket_name: str, site_id: str, timestamp_str: str, records: list, metadata: dict
) -> str:
    """Save transformed structured JSON dataset to S3 under transform/ folder."""
    if not bucket_name:
        logger.info("No S3 bucket specified. Skipping S3 transformed archive.")
        return ""

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
        return s3_key
    except (ClientError, NoCredentialsError, NoRegionError) as e:
        logger.warning("Could not upload transformed JSON to S3: %s", str(e))
        return ""


def store_records_in_dynamodb(table_name: str, records: list) -> int:
    """
    Batch store unique records in Amazon DynamoDB.
    Returns the count of successfully stored records.
    """
    if not table_name:
        logger.warning("No DynamoDB table name specified.")
        return 0

    try:
        dynamodb = boto3.resource("dynamodb", region_name=DEFAULT_REGION)
        table = dynamodb.Table(table_name)
        stored_count = 0

        with table.batch_writer() as batch:
            for r in records:
                # Convert floats to Decimals for DynamoDB
                item = convert_floats_to_decimals(r)
                batch.put_item(Item=item)
                stored_count += 1

        logger.info("Successfully stored %d records in DynamoDB table %s", stored_count, table_name)
        return stored_count
    except (ClientError, NoCredentialsError, NoRegionError) as e:
        logger.warning("DynamoDB storage skipped or failed (dry-run/credentials required): %s", str(e))
        return 0


def lambda_handler(event, context=None):
    """
    Lambda Handler for DynamoDB and S3 Storage.
    Receives transformed records from transformation Lambda.
    """
    logger.info("Storage handler received event for site: %s", event.get("site_id"))

    records = event.get("records", [])
    site_id = event.get("site_id", "unknown_site")
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
    transformed_s3_key = ""
    if bucket_name:
        transformed_s3_key = save_transformed_json_to_s3(
            bucket_name=bucket_name,
            site_id=site_id,
            timestamp_str=timestamp_folder,
            records=records,
            metadata=metadata,
        )

    # 2. Store records in DynamoDB
    stored_count = 0
    if records and table_name:
        stored_count = store_records_in_dynamodb(table_name, records)

    return {
        "statusCode": 200,
        "status": "SUCCESS",
        "Storage": "SUCCESS",
        "site_id": site_id,
        "site_name": event.get("site_name", site_id),
        "target_url": target_url,
        "scraped_at": scraped_at,
        "raw_s3_key": raw_s3_key,
        "transformed_s3_key": transformed_s3_key,
        "dynamodb_table": table_name,
        "records_count": len(records),
        "records_stored_dynamodb": stored_count,
        "duplicates_removed": event.get("duplicates_removed", 0),
        "summary": f"Stored {len(records)} records (DynamoDB: {stored_count}, S3: {transformed_s3_key or 'N/A'})",
    }


if __name__ == "__main__":
    # Test execution
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
            "dynamodb_table": "TestTable",
        }
    )
    print("Storage result:", json.dumps(res, indent=2))
