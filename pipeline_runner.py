"""
The Cloud Scraper - Local Pipeline Simulator & Demonstration Runner
Simulates the AWS Step Functions State Machine workflow locally,
executing: Scrape -> Validate -> Transform/Deduplicate -> Store -> Notify.

Supports live web scraping, offline controlled fixtures, multi-site runs,
and controlled failure simulation for fault-tolerance demonstration.
"""

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
import start_step_function

scraper_handler = scraper.lambda_handler
validation_handler = validation.lambda_handler
transform_handler = transformation.lambda_handler
store_handler = dynamodb_store.lambda_handler
notification_handler = notification.lambda_handler
dispatcher_handler = start_step_function.lambda_handler


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


OFFLINE_HTML_FIXTURE = """
<!DOCTYPE html>
<html>
<body>
  <article class="product_pod">
    <h3><a href="catalogue/cloud-architecture-patterns_1/index.html" title="Cloud Architecture Patterns">Cloud Architecture Patterns</a></h3>
    <div class="product_price">
      <p class="price_color">£49.99</p>
      <p class="instock availability">In stock</p>
    </div>
    <p class="star-rating Five"></p>
  </article>
  <article class="product_pod">
    <h3><a href="catalogue/serverless-design_2/index.html" title="Serverless Data Pipelines">Serverless Data Pipelines</a></h3>
    <div class="product_price">
      <p class="price_color">£39.50</p>
      <p class="instock availability">In stock</p>
    </div>
    <p class="star-rating Four"></p>
  </article>
  <article class="product_pod">
    <h3><a href="catalogue/serverless-design_2/index.html" title="Serverless Data Pipelines">Serverless Data Pipelines</a></h3>
    <div class="product_price">
      <p class="price_color">£39.50</p>
      <p class="instock availability">In stock</p>
    </div>
    <p class="star-rating Four"></p>
  </article>
</body>
</html>
"""


def run_pipeline(
    site_id: str,
    bucket_name: str = "",
    table_name: str = "TheCloudScraper-Records",
    use_fixture: bool = False,
    simulate_failure: bool = False,
) -> dict:
    """
    Execute the entire serverless pipeline for a given site_id in sequence,
    mirroring AWS Step Functions execution semantics.
    """
    start_time = time.time()
    mode_tag = "OFFLINE FIXTURE" if use_fixture else ("FAILURE SIMULATION" if simulate_failure else "LIVE SCRAPING")
    print("\n" + "=" * 70)
    print(f"[RUN] INITIATING THE CLOUD SCRAPER PIPELINE: [{site_id}] ({mode_tag})")
    print("=" * 70)

    # State 1: Scrape
    print("\n[State 1/5] Executing Scraper Lambda...")
    scrape_event = {
        "site_id": site_id,
        "bucket_name": bucket_name,
    }
    if use_fixture:
        scrape_event["mock_html"] = OFFLINE_HTML_FIXTURE
        print("  [INFO] Using controlled offline HTML test fixture")
    elif simulate_failure:
        scrape_event["target_url"] = "http://localhost:59999/non-existent-server"
        print("  [INFO] Injecting controlled connection failure to test error routing")

    scrape_result = scraper_handler(scrape_event)

    if scrape_result.get("status") != "SUCCESS":
        print(f"  [ERROR] Scraper Failed as expected: {scrape_result.get('error')}")
        print("\n[Fault Tolerance] Step Functions Catch Block Triggered -> Route Failure to SQS DLQ")
        print("  [DLQ] Enqueued failed execution payload to ScraperDLQ (Redrive isolation)")
        print("\n[State 5/5] Executing Failure Notification Lambda...")
        scrape_result["duration_seconds"] = time.time() - start_time
        notify_result = notification_handler(scrape_result)
        print(f"  [ALERT] Published failure alarm to Amazon SNS: {notify_result.get('summary')}")
        print("\n" + "=" * 70)
        print(f"[FAULT TOLERANCE VERIFIED] Pipeline gracefully handled failure in {scrape_result['duration_seconds']:.2f}s")
        print("=" * 70)
        return scrape_result

    print(f"  [OK] Scraped {scrape_result.get('records_count')} records from {scrape_result.get('target_url')}")

    # State 2: Validate
    print("\n[State 2/5] Executing Validation Lambda...")
    val_result = validation_handler(scrape_result)
    if val_result.get("Validation") != "SUCCESS":
        print(f"  [ERROR] Validation Failed: {val_result.get('error')}")
        print("  [DLQ] Routing validation failures to ScraperDLQ")
        val_result["duration_seconds"] = time.time() - start_time
        notification_handler(val_result)
        return val_result
    print(f"  [OK] Validated records: {val_result.get('valid_count')} valid, {val_result.get('invalid_count')} invalid")

    # State 3: Transform & Deduplicate
    print("\n[State 3/5] Executing Transformation & Deduplication Lambda...")
    transform_result = transform_handler(val_result)
    print(f"  [OK] Transformed records: {transform_result.get('total_transformed')} unique, {transform_result.get('duplicates_removed')} duplicates removed (SHA-256 fingerprinting)")

    # State 4: Store in DynamoDB & S3
    print("\n[State 4/5] Executing Cloud Storage Lambda (DynamoDB & S3)...")
    store_event = dict(transform_result)
    store_event["dynamodb_table"] = table_name
    store_event["bucket_name"] = bucket_name
    store_result = store_handler(store_event)
    print(f"  [OK] Storage status: {store_result.get('summary')}")
    print(f"  [OK] Mode: {store_result.get('storage_mode')} (Conditional writes enforced)")

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
    parser = argparse.ArgumentParser(
        description="The Cloud Scraper - Local Pipeline Simulator & Demonstration Runner"
    )
    parser.add_argument(
        "--site",
        default="books_toscrape",
        choices=["books_toscrape", "quotes_toscrape"],
        help="Target site ID to run (default: books_toscrape)",
    )
    parser.add_argument("--all", action="store_true", help="Run pipeline across all configured sites")
    parser.add_argument("--fixture", action="store_true", help="Use controlled offline HTML test fixture")
    parser.add_argument("--simulate-failure", action="store_true", help="Simulate failure to test DLQ & SNS alerting")
    parser.add_argument("--bucket", default="", help="Optional S3 bucket name")
    parser.add_argument("--table", default="TheCloudScraper-Records", help="DynamoDB table name")
    args = parser.parse_args()

    if args.all:
        for sid in ["books_toscrape", "quotes_toscrape"]:
            run_pipeline(sid, args.bucket, args.table, args.fixture, args.simulate_failure)
    else:
        res = run_pipeline(args.site, args.bucket, args.table, args.fixture, args.simulate_failure)
        if res.get("status") == "SUCCESS" and res.get("sample_record"):
            print("\nSample Transformed Entity (DynamoDB & S3 format):")
            print(json.dumps(res["sample_record"], indent=2))


if __name__ == "__main__":
    main()
