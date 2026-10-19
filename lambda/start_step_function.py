"""
The Cloud Scraper - Job Dispatcher Lambda Function
Accepts scheduled events from Amazon EventBridge, on-demand REST API requests
from Amazon API Gateway, or batch messages from Amazon SQS, and initiates
AWS Step Functions State Machine executions.
"""

import os
import json
import uuid
import logging
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, NoRegionError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))


def get_enabled_sites() -> list:
    """Read enabled sites from configuration file."""
    config_path = os.environ.get(
        "SITES_CONFIG_PATH",
        os.path.join(os.path.dirname(__file__), "..", "config", "sites_config.json"),
    )
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [s.get("site_id") for s in data.get("sites", []) if s.get("enabled", True)]
        except Exception as e:
            logger.warning("Could not read sites configuration: %s", str(e))
    return ["books_toscrape", "quotes_toscrape"]


def parse_incoming_event(event: dict) -> list:
    """
    Parse event to extract list of target site job configurations.
    Supports EventBridge, API Gateway, SQS, and direct invocation.
    """
    jobs = []

    # 1. API Gateway REST trigger
    if "body" in event and isinstance(event.get("body"), str):
        try:
            body = json.loads(event["body"])
            site_id = body.get("site_id")
            if site_id:
                jobs.append({
                    "site_id": site_id,
                    "target_url": body.get("target_url"),
                    "triggered_by": "api_gateway",
                })
        except Exception:
            pass

    # 2. SQS trigger
    elif "Records" in event and event["Records"] and "s3" not in event["Records"][0]:
        for rec in event["Records"]:
            try:
                body = json.loads(rec.get("body", "{}"))
                site_id = body.get("site_id")
                if site_id:
                    jobs.append({
                        "site_id": site_id,
                        "target_url": body.get("target_url"),
                        "triggered_by": "sqs_queue",
                    })
            except Exception:
                pass

    # 3. Direct or EventBridge trigger specifying a site
    elif "site_id" in event:
        jobs.append({
            "site_id": event["site_id"],
            "target_url": event.get("target_url"),
            "triggered_by": "direct" if "source" not in event else "eventbridge",
        })

    # 4. Scheduled EventBridge rule without specific site -> trigger all enabled sites
    else:
        for sid in get_enabled_sites():
            jobs.append({
                "site_id": sid,
                "triggered_by": "eventbridge_schedule",
            })

    return jobs


def start_state_machine_execution(state_machine_arn: str, job_input: dict) -> dict:
    """Start an execution of the Step Functions State Machine."""
    execution_name = f"scrape-{job_input['site_id']}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    job_input["execution_id"] = execution_name
    job_input["dispatched_at"] = datetime.now(timezone.utc).isoformat()

    if not state_machine_arn:
        logger.info("Local test mode: State Machine ARN not provided. Simulated execution: %s", execution_name)
        return {
            "executionArn": f"arn:aws:states:local:simulated:execution:{execution_name}",
            "executionName": execution_name,
            "status": "SIMULATED",
            "input": job_input,
        }

    try:
        sfn_client = boto3.client("stepfunctions", region_name=DEFAULT_REGION)
        response = sfn_client.start_execution(
            stateMachineArn=state_machine_arn,
            name=execution_name,
            input=json.dumps(job_input),
        )
        logger.info("Started Step Functions execution: %s", response.get("executionArn"))
        return {
            "executionArn": response.get("executionArn"),
            "startDate": str(response.get("startDate")),
            "executionName": execution_name,
            "status": "RUNNING",
            "input": job_input,
        }
    except (ClientError, NoCredentialsError, NoRegionError) as e:
        logger.warning("Could not start Step Functions execution: %s", str(e))
        return {
            "executionArn": "",
            "executionName": execution_name,
            "status": "FAILED",
            "error": str(e),
            "input": job_input,
        }


def lambda_handler(event, context=None):
    """
    AWS Lambda Handler for Job Dispatching.
    Initiates Step Functions execution for target websites.
    """
    logger.info("Dispatcher received event: %s", json.dumps(event))

    state_machine_arn = os.environ.get("STEP_FUNC_ARN", "")
    bucket_name = os.environ.get("S3_BUCKET_NAME", "")
    dynamodb_table = os.environ.get("DYNAMODB_TABLE_NAME", "TheCloudScraper-Records")

    jobs = parse_incoming_event(event)
    results = []

    for job in jobs:
        job["bucket_name"] = bucket_name
        job["dynamodb_table"] = dynamodb_table
        res = start_state_machine_execution(state_machine_arn, job)
        results.append(res)

    # API Gateway response format if invoked via HTTP
    is_api_request = "httpMethod" in event or ("body" in event and "path" in event)
    if is_api_request:
        return {
            "statusCode": 202,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "message": f"Successfully initiated scraping pipeline for {len(results)} job(s)",
                "jobs": results,
            }),
        }

    return {
        "statusCode": 200,
        "status": "SUCCESS",
        "dispatched_count": len(results),
        "executions": results,
    }


if __name__ == "__main__":
    # Test dispatch locally
    test_event = {"site_id": "books_toscrape"}
    res = lambda_handler(test_event)
    print("Dispatch result:", json.dumps(res, indent=2))