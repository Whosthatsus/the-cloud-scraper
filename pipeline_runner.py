import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone

# Add lambda directory to sys.path since 'lambda' is a reserved keyword in Python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lambda"))

import scraper
import validation
import transformation
import dynamodb_store
import notification

scraper_handler = scraper.lambda_handler
validation_handler = validation.lambda_handler
transform_handler = transformation.lambda_handler
store_handler = dynamodb_store.lambda_handler
notification_handler = notification.lambda_handler


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_pipeline(site_id: str, bucket_name: str = "", table_name: str = "TheCloudScraper-Records") -> dict:
    """
    Execute the entire serverless pipeline for a given site_id in sequence,
    mirroring AWS Step Functions execution semantics.
    """
    start_time = time.time()
    print("\n" + "=" * 70)
    print(f"[RUN] INITIATING THE CLOUD SCRAPER PIPELINE: [{site_id}]")
    print("=" * 70)

    # State 1: Scrape
    print("\n[State 1/5] Executing Scraper Lambda...")
    scrape_event = {
        "site_id": site_id,
        "bucket_name": bucket_name,
    }
    scrape_result = scraper_handler(scrape_event)
    if scrape_result.get("status") != "SUCCESS":
        print(f"[FAILED] Scraper Failed: {scrape_result.get('error')}")
        notification_handler(scrape_result)
        return scrape_result
    print(f"  [OK] Scraped {scrape_result.get('records_count')} records from {scrape_result.get('target_url')}")

    # State 2: Validate
    print("\n[State 2/5] Executing Validation Lambda...")
    val_result = validation_handler(scrape_result)
    if val_result.get("Validation") != "SUCCESS":
        print(f"[FAILED] Validation Failed: {val_result.get('error')}")
        notification_handler(val_result)
        return val_result
    print(f"  [OK] Validated records: {val_result.get('valid_count')} valid, {val_result.get('invalid_count')} invalid")

    # State 3: Transform & Deduplicate
    print("\n[State 3/5] Executing Transformation & Deduplication Lambda...")
    transform_result = transform_handler(val_result)
    print(f"  [OK] Transformed records: {transform_result.get('total_transformed')} unique, {transform_result.get('duplicates_removed')} duplicates removed")

    # State 4: Store in DynamoDB & S3
    print("\n[State 4/5] Executing Cloud Storage Lambda (DynamoDB & S3)...")
    store_event = dict(transform_result)
    store_event["dynamodb_table"] = table_name
    store_event["bucket_name"] = bucket_name
    store_result = store_handler(store_event)
    print(f"  [OK] Storage status: {store_result.get('summary')}")

    # State 5: Notification & Telemetry
    print("\n[State 5/5] Executing Notification & FinOps Telemetry Lambda...")
    elapsed = time.time() - start_time
    notify_event = dict(store_result)
    notify_event["duration_seconds"] = elapsed
    notify_result = notification_handler(notify_event)
    print(f"  [OK] Notification summary: {notify_result.get('summary')}")
    print(f"  [OK] Estimated run cost: ${notify_result['cost_metrics']['estimated_total_usd']:.6f} USD")

    print("\n" + "=" * 70)
    print(f"[SUCCESS] PIPELINE EXECUTION COMPLETED SUCCESSFULLY IN {elapsed:.2f}s")
    print("=" * 70)

    return {
        "status": "SUCCESS",
        "site_id": site_id,
        "elapsed_seconds": round(elapsed, 2),
        "scraped": scrape_result.get("records_count"),
        "valid": val_result.get("valid_count"),
        "transformed": transform_result.get("total_transformed"),
        "duplicates_removed": transform_result.get("duplicates_removed"),
        "cost_metrics": notify_result.get("cost_metrics"),
        "sample_record": transform_result["records"][0] if transform_result.get("records") else None,
    }


def main():
    parser = argparse.ArgumentParser(description="The Cloud Scraper - Pipeline Simulator")
    parser.add_argument("--site", default="books_toscrape", choices=["books_toscrape", "quotes_toscrape"],
                        help="Target site ID to run")
    parser.add_argument("--bucket", default="", help="Optional S3 bucket name")
    parser.add_argument("--table", default="TheCloudScraper-Records", help="DynamoDB table name")
    args = parser.parse_args()

    result = run_pipeline(args.site, args.bucket, args.table)
    if result.get("status") == "SUCCESS" and result.get("sample_record"):
        print("\nSample Transformed Entity:")
        print(json.dumps(result["sample_record"], indent=2))


if __name__ == "__main__":
    main()
