"""
The Cloud Scraper - Notification & FinOps Observability Lambda Function
Publishes enriched pipeline metrics, operational health alerts, and execution
cost estimates to Amazon SNS and Amazon CloudWatch Logs.
"""

import os
import json
import logging
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, NoRegionError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))


def calculate_estimated_cost(
    duration_seconds: float, records_stored: int, memory_mb: int = 512, state_transitions: int = 5
) -> dict:
    """
    Estimate the execution cost for this serverless pipeline run.
    Based on AWS us-east-1 serverless pricing (as of 2026):
    - Lambda: $0.0000166667 per GB-second, $0.20 per 1M requests
    - S3: $0.005 per 1,000 PUT requests
    - DynamoDB: $1.25 per 1M Write Request Units (WRU)
    - Step Functions: $0.000025 per state transition
    """
    gb_seconds = (duration_seconds or 1.5) * (memory_mb / 1024.0)
    lambda_compute_cost = gb_seconds * 0.0000166667
    lambda_request_cost = 4 * 0.0000002  # 4 Lambda invocations in pipeline
    s3_put_cost = 2 * (0.005 / 1000.0)  # Raw snapshot + Transformed JSON
    dynamodb_wru_cost = (records_stored or 1) * (1.25 / 1000000.0)
    step_functions_cost = state_transitions * 0.000025

    total_cost = lambda_compute_cost + lambda_request_cost + s3_put_cost + dynamodb_wru_cost + step_functions_cost

    return {
        "estimated_total_usd": round(total_cost, 6),
        "lambda_compute_usd": round(lambda_compute_cost, 7),
        "s3_storage_ops_usd": round(s3_put_cost, 7),
        "dynamodb_writes_usd": round(dynamodb_wru_cost, 7),
        "step_functions_usd": round(step_functions_cost, 7),
    }


def format_notification_body(event: dict, cost_data: dict) -> str:
    """Format clear, human-readable notification text for email subscribers."""
    status = event.get("status") or event.get("Validation") or "UNKNOWN"
    site_id = event.get("site_id", "N/A")
    site_name = event.get("site_name", site_id)
    target_url = event.get("target_url", "N/A")
    scraped_at = event.get("scraped_at", datetime.now(timezone.utc).isoformat())

    records_count = event.get("records_count") or event.get("total_scraped", 0)
    stored_count = event.get("records_stored_dynamodb", records_count)
    dups_removed = event.get("duplicates_removed", 0)
    raw_s3_key = event.get("raw_s3_key", "N/A")
    transformed_key = event.get("transformed_s3_key", "N/A")
    error_msg = event.get("error", "None")

    lines = [
        "==========================================================",
        f" The Cloud Scraper — Pipeline Execution Report: [{status}]",
        "==========================================================",
        f"Timestamp:             {scraped_at}",
        f"Site ID:               {site_id} ({site_name})",
        f"Target URL:            {target_url}",
        f"Pipeline Status:       {status}",
        "",
        "--- Data Processing Metrics ---",
        f"Raw Records Extracted: {records_count}",
        f"Duplicates Filtered:   {dups_removed}",
        f"Records Stored:        {stored_count}",
        f"Raw S3 Key:            {raw_s3_key}",
        f"Transformed S3 Key:    {transformed_key}",
        "",
        "--- FinOps Cost Estimation ---",
        f"Estimated Total Cost:  ${cost_data['estimated_total_usd']:.6f} USD",
        f" - Lambda Compute:     ${cost_data['lambda_compute_usd']:.7f} USD",
        f" - Step Functions:     ${cost_data['step_functions_usd']:.7f} USD",
        f" - DynamoDB Operations: ${cost_data['dynamodb_writes_usd']:.7f} USD",
        f" - S3 Ingestion Ops:   ${cost_data['s3_storage_ops_usd']:.7f} USD",
    ]

    if status != "SUCCESS":
        lines.extend([
            "",
            "--- Failure Details ---",
            f"Error Reason:          {error_msg}",
            "Action: Execution routed to Dead-Letter Queue (DLQ).",
        ])

    lines.append("==========================================================")
    return "\n".join(lines)


def lambda_handler(event, context=None):
    """
    AWS Lambda Handler for Notifications & CloudWatch Telemetry.
    Publishes execution summary and cost metrics to Amazon SNS.
    """
    logger.info("Notification handler received event: %s", json.dumps(event))

    status = event.get("status") or event.get("Validation") or "SUCCESS"
    site_id = event.get("site_id", "unknown")
    topic_arn = os.environ.get("SNS_TOPIC") or os.environ.get("SNS_TOPIC_ARN", "")
    records_count = int(event.get("records_count") or event.get("total_scraped", 0))

    cost_data = calculate_estimated_cost(
        duration_seconds=float(event.get("duration_seconds", 2.0)),
        records_stored=records_count,
    )

    body_text = format_notification_body(event, cost_data)
    subject = f"The Cloud Scraper: [{status}] {site_id} ({records_count} records)"

    sns_result = {"published": False, "message": "SNS Topic ARN not configured or in local test mode"}

    if topic_arn:
        try:
            sns_client = boto3.client("sns", region_name=DEFAULT_REGION)
            response = sns_client.publish(
                TopicArn=topic_arn,
                Subject=subject[:100],  # SNS Subject max 100 characters
                Message=body_text,
            )
            sns_result = {
                "published": True,
                "message_id": response.get("MessageId"),
                "status": "DELIVERED",
            }
            logger.info("Successfully published notification to SNS: %s", response.get("MessageId"))
        except (ClientError, NoCredentialsError, NoRegionError) as e:
            logger.warning("Could not publish to SNS: %s", str(e))
            sns_result = {"published": False, "error": str(e)}

    error_msg = event.get("error")
    if not error_msg:
        if "error_info" in event and isinstance(event["error_info"], dict):
            error_msg = event["error_info"].get("Cause") or str(event["error_info"])
        elif status != "SUCCESS":
            error_msg = f"Pipeline execution failed at stage with status: {status}"
        else:
            error_msg = "None"

    error_type = event.get("error_type")
    if not error_type:
        if "error_info" in event and isinstance(event["error_info"], dict):
            error_type = event["error_info"].get("Error") or "PipelineExecutionError"
        elif status != "SUCCESS":
            error_type = "STAGE_FAILURE"
        else:
            error_type = "NONE"

    return {
        "statusCode": 200,
        "status": status,
        "Notification": "SUCCESS" if sns_result.get("published") else "SKIPPED",
        "site_id": site_id,
        "records_count": records_count,
        "cost_metrics": cost_data,
        "sns_result": sns_result,
        "summary": subject,
        "error": str(error_msg)[:512],
        "error_type": str(error_type)[:128],
    }


if __name__ == "__main__":
    test_event = {
        "status": "SUCCESS",
        "site_id": "books_toscrape",
        "site_name": "Books to Scrape",
        "target_url": "https://books.toscrape.com/",
        "records_count": 20,
        "duplicates_removed": 1,
        "records_stored_dynamodb": 19,
        "raw_s3_key": "raw/books_toscrape/20261020/page.html",
        "transformed_s3_key": "transform/books_toscrape/20261020/records.json",
    }
    res = lambda_handler(test_event)
    print(res["summary"])
    print(format_notification_body(test_event, res["cost_metrics"]))