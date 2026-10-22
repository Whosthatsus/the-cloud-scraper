"""
The Cloud Scraper - Local Pipeline Simulator & Demonstration Runner
Simulates the AWS Step Functions State Machine workflow locally,
executing: Scrape -> Validate -> Transform/Deduplicate -> Store -> Notify.

Supports live web scraping, offline controlled fixtures, multi-site runs,
pagination, SSRF security validation, execution history tracking,
and controlled failure simulation for fault-tolerance demonstration.
"""

import os
import sys
import json
import time
import uuid
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

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "output", "history.json")


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


def record_execution_history(entry: dict):
    """Persist execution entry into output/history.json (keeps most recent 50 runs)."""
    try:
        out_dir = os.path.dirname(HISTORY_FILE)
        os.makedirs(out_dir, exist_ok=True)
        history = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
                if not isinstance(history, list):
                    history = []
            except Exception:
                history = []
        history.insert(0, entry)
        history = history[:50]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not save execution history: {e}")


def get_execution_history() -> list:
    """Read persisted execution history list from output/history.json."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


def run_pipeline(
    site_id: str,
    bucket_name: str = "",
    table_name: str = "TheCloudScraper-Records",
    use_fixture: bool = False,
    simulate_failure: bool = False,
    custom_url: str = None,
    page_limit: int = 1,
    timeout_seconds: int = 15,
    extraction_type: str = "generic",
    container_selector: str = None,
    fields: dict = None,
    validation_rules: dict = None,
    site_name: str = None,
    config_override: dict = None,
) -> dict:
    """
    Execute the entire serverless pipeline for a given site_id in sequence,
    mirroring AWS Step Functions execution semantics.
    """
    start_time = time.time()
    exec_id = f"exec-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    mode_tag = "OFFLINE FIXTURE" if use_fixture else ("FAILURE SIMULATION" if simulate_failure else "LIVE SCRAPING")

    print("\n" + "=" * 70)
    print(f"[RUN] INITIATING THE CLOUD SCRAPER PIPELINE: [{site_id}] ({mode_tag})")
    print(f"[EXECUTION ID] {exec_id}")
    print("=" * 70)

    # State 1: Scrape
    print("\n[State 1/5] Executing Scraper Lambda...")
    scrape_event = {
        "site_id": site_id,
        "site_name": site_name or site_id,
        "bucket_name": bucket_name,
        "page_limit": page_limit,
        "timeout_seconds": timeout_seconds,
        "extraction_type": extraction_type,
        "container_selector": container_selector,
        "fields": fields or {},
        "validation_rules": validation_rules or {},
    }
    if config_override:
        scrape_event["config_override"] = config_override
    if custom_url:
        scrape_event["target_url"] = custom_url
        print(f"  [INFO] Custom target URL: {custom_url}")
    if use_fixture:
        scrape_event["mock_html"] = OFFLINE_HTML_FIXTURE
        print("  [INFO] Using controlled offline HTML test fixture")
    elif simulate_failure:
        scrape_event["simulate_failure"] = True
        print("  [INFO] Injecting controlled network fault to test Step Functions error routing")

    scrape_result = scraper_handler(scrape_event)

    if scrape_result.get("status") != "SUCCESS":
        print(f"  [ERROR] Scraper Failed as expected: {scrape_result.get('error')}")
        print("\n[Fault Tolerance] Step Functions Catch Block Triggered -> Route Failure to SQS DLQ")
        print("  [DLQ] Enqueued failed execution payload to ScraperDLQ (Redrive isolation)")
        print("\n[State 5/5] Executing Failure Notification Lambda...")
        elapsed_err = round(time.time() - start_time, 2)
        scrape_result["duration_seconds"] = elapsed_err
        scrape_result["elapsed_seconds"] = elapsed_err
        scrape_result["execution_id"] = exec_id
        notify_result = notification_handler(scrape_result)
        print(f"  [ALERT] Published failure alarm to Amazon SNS: {notify_result.get('summary')}")
        print("\n" + "=" * 70)
        print(f"[FAULT TOLERANCE VERIFIED] Pipeline gracefully handled failure in {elapsed_err:.2f}s")
        print("=" * 70)
        scrape_result["cost_metrics"] = notify_result.get("cost_metrics", {
            "estimated_total_usd": 0.000000,
            "lambda_invocations": 2,
            "s3_requests": 0,
            "dynamodb_writes": 0,
            "step_function_state_transitions": 3,
        })
        scrape_result["stages"] = [
            {
                "id": "trigger",
                "name": "Event Ingestion & Dispatch",
                "service": "EventBridge / API Gateway",
                "status": "COMPLETED",
                "detail": f"Dispatched scraping job for '{site_id}' ({exec_id})",
            },
            {
                "id": "scraper",
                "name": "Live Web Scraping & Ingestion",
                "service": "AWS Lambda (Requests + BS4)",
                "status": "FAILED",
                "detail": f"{scrape_result.get('error', 'Scraper failed')}",
            },
            {
                "id": "dlq",
                "name": "Step Functions Catch Block -> DLQ",
                "service": "Amazon SQS Dead Letter Queue",
                "status": "COMPLETED",
                "detail": "Failed execution payload routed to ScraperDLQ with Redrive policy",
            },
            {
                "id": "notification",
                "name": "Failure Alarm & Operator Notification",
                "service": "Amazon SNS & CloudWatch",
                "status": "COMPLETED",
                "detail": f"SNS Alert: {notify_result.get('summary', 'Alarm published')}",
            },
        ]
        scrape_result["scraped"] = 0
        scrape_result["valid"] = 0
        scrape_result["duplicates_removed"] = 0
        scrape_result["transformed"] = 0
        scrape_result["records"] = []

        # Record failure into execution history
        record_execution_history({
            "execution_id": exec_id,
            "timestamp": now_iso,
            "site_id": site_id,
            "target_url": scrape_result.get("target_url", custom_url or site_id),
            "mode": mode_tag,
            "status": "FAILURE",
            "duration": elapsed_err,
            "scraped": 0,
            "valid": 0,
            "duplicates_removed": 0,
            "transformed": 0,
            "cost_usd": scrape_result["cost_metrics"].get("estimated_total_usd", 0.0),
            "error": scrape_result.get("error", "Execution failed"),
        })

        return scrape_result

    print(f"  [OK] Scraped {scrape_result.get('records_count')} records (Pages: {scrape_result.get('pages_scraped', 1)}) from {scrape_result.get('target_url')}")

    # State 2: Validate
    print("\n[State 2/5] Executing Validation Lambda...")
    val_result = validation_handler(scrape_result)
    if val_result.get("Validation") != "SUCCESS":
        print(f"  [ERROR] Validation Failed: {val_result.get('error')}")
        print("  [DLQ] Routing validation failures to ScraperDLQ")
        val_result["duration_seconds"] = time.time() - start_time
        val_result["execution_id"] = exec_id
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

    result_payload = {
        "status": "SUCCESS",
        "execution_id": exec_id,
        "site_id": site_id,
        "elapsed_seconds": round(elapsed, 2),
        "target_url": scrape_result.get("target_url", ""),
        "pages_scraped": scrape_result.get("pages_scraped", 1),
        "scraped": scrape_result.get("records_count"),
        "raw_records_count": scrape_result.get("records_count", 0),
        "valid": val_result.get("valid_count"),
        "invalid_count": val_result.get("invalid_count", 0),
        "transformed": transform_result.get("total_transformed"),
        "duplicates_removed": transform_result.get("duplicates_removed"),
        "cost_metrics": notify_result.get("cost_metrics"),
        "sample_record": transform_result["records"][0] if transform_result.get("records") else None,
        "records": transform_result.get("records", []),
        "stages": [
            {
                "id": "trigger",
                "name": "Event Ingestion & Dispatch",
                "service": "EventBridge / API Gateway",
                "status": "COMPLETED",
                "detail": f"Dispatched scraping job for '{site_id}' ({exec_id})",
            },
            {
                "id": "scraper",
                "name": "Live Web Scraping & Raw Snapshot",
                "service": "AWS Lambda (Requests + BS4)",
                "status": "COMPLETED",
                "detail": f"Scraped {scrape_result.get('records_count')} records ({scrape_result.get('pages_scraped', 1)} page(s)) from {scrape_result.get('target_url')}",
            },
            {
                "id": "validation",
                "name": "Schema & Quality Validation",
                "service": "AWS Lambda",
                "status": "COMPLETED",
                "detail": f"{val_result.get('valid_count')} valid records, {val_result.get('invalid_count')} invalid",
            },
            {
                "id": "transformation",
                "name": "Normalization & SHA-256 Deduplication",
                "service": "AWS Lambda",
                "status": "COMPLETED",
                "detail": f"{transform_result.get('total_transformed')} unique entities ({transform_result.get('duplicates_removed')} duplicates filtered)",
            },
            {
                "id": "storage",
                "name": "Dual-Tier Storage (Local & Cloud)",
                "service": "Amazon DynamoDB & S3",
                "status": "COMPLETED",
                "detail": store_result.get("summary", "Stored records"),
            },
            {
                "id": "notification",
                "name": "FinOps Telemetry & Alerts",
                "service": "Amazon SNS & CloudWatch",
                "status": "COMPLETED",
                "detail": f"Estimated run cost: ${notify_result['cost_metrics']['estimated_total_usd']:.6f} USD",
            },
        ],
        "storage": {
            "mode": store_result.get("storage_mode", "OFFLINE_LOCAL_MODE"),
            "local_file": f"output/{site_id}.json",
            "records_stored_locally": len(transform_result.get("records", [])),
            "aws_s3_status": "NOT_CONFIGURED (Zero-Cost Local Mode)",
            "aws_dynamodb_status": "NOT_CONFIGURED (Zero-Cost Local Mode)",
            "message": "Immutable JSON snapshot stored locally under output/. Live AWS credentials omitted for zero-cost operation.",
        },
    }

    # Record success into execution history
    record_execution_history({
        "execution_id": exec_id,
        "timestamp": now_iso,
        "site_id": site_id,
        "target_url": scrape_result.get("target_url", ""),
        "mode": mode_tag,
        "status": "SUCCESS",
        "duration": round(elapsed, 2),
        "scraped": scrape_result.get("records_count", 0),
        "valid": val_result.get("valid_count", 0),
        "duplicates_removed": transform_result.get("duplicates_removed", 0),
        "transformed": transform_result.get("total_transformed", 0),
        "cost_usd": notify_result["cost_metrics"].get("estimated_total_usd", 0.0),
        "pages_scraped": scrape_result.get("pages_scraped", 1),
    })

    return result_payload


def main():
    parser = argparse.ArgumentParser(
        description="The Cloud Scraper - Local Pipeline Simulator & Demonstration Runner"
    )
    parser.add_argument(
        "--site",
        default="books_toscrape",
        choices=["books_toscrape", "quotes_toscrape", "webscraper_laptops", "hacker_news"],
        help="Target site ID to run (default: books_toscrape)",
    )
    parser.add_argument("--url", default=None, help="Custom target URL override")
    parser.add_argument("--pages", type=int, default=1, help="Page limit (1-5, default: 1)")
    parser.add_argument("--timeout", type=int, default=15, help="Request timeout in seconds (3-30, default: 15)")
    parser.add_argument("--all", action="store_true", help="Run pipeline across all configured sites")
    parser.add_argument("--fixture", action="store_true", help="Use controlled offline HTML test fixture")
    parser.add_argument("--simulate-failure", action="store_true", help="Simulate failure to test DLQ & SNS alerting")
    parser.add_argument("--bucket", default="", help="Optional S3 bucket name")
    parser.add_argument("--table", default="TheCloudScraper-Records", help="DynamoDB table name")
    args = parser.parse_args()

    if args.all:
        for sid in ["books_toscrape", "quotes_toscrape", "webscraper_laptops", "hacker_news"]:
            run_pipeline(
                sid,
                args.bucket,
                args.table,
                args.fixture,
                args.simulate_failure,
                args.url,
                args.pages,
                args.timeout,
            )
    else:
        res = run_pipeline(
            args.site,
            args.bucket,
            args.table,
            args.fixture,
            args.simulate_failure,
            args.url,
            args.pages,
            args.timeout,
        )
        if res.get("status") == "SUCCESS" and res.get("sample_record"):
            print("\nSample Transformed Entity (DynamoDB & S3 format):")
            print(json.dumps(res["sample_record"], indent=2))


if __name__ == "__main__":
    main()
