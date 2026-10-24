"""
The Cloud Scraper - Job Dispatcher & REST API Controller Lambda Function
Accepts scheduled events from Amazon EventBridge, on-demand REST API requests
from Amazon API Gateway, or batch messages from Amazon SQS.

Initiates AWS Step Functions State Machine executions, describes execution status,
persists/retrieves target website configurations in Amazon DynamoDB,
and returns actual persisted scraped records.
"""

import os
import re
import json
import uuid
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, NoRegionError

import dynamodb_store
import scraper

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "ap-southeast-2"))

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def sanitize_site_id(name_or_url: str) -> str:
    """Generate a valid, collision-resistant site_id slug."""
    if not name_or_url:
        return f"custom_{uuid.uuid4().hex[:6]}"
    # Extract domain if URL
    if "://" in name_or_url:
        parsed = urlparse(name_or_url)
        name_or_url = parsed.netloc.replace(".", "_") + parsed.path.replace("/", "_")
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", name_or_url).strip("_").lower()
    return slug[:40] or f"custom_{uuid.uuid4().hex[:6]}"


def get_enabled_sites() -> list:
    """List site IDs configured in local config/sites_config.json."""
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
                    return [s.get("site_id") for s in data.get("sites", []) if s.get("enabled", True)]
            except Exception as e:
                logger.warning("Could not read sites configuration at %s: %s", cp, str(e))
    return ["books_toscrape", "quotes_toscrape"]


def get_default_site_configs() -> list:
    """Read default predefined sites from config/sites_config.json."""
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
                    return data.get("sites", [])
            except Exception as e:
                logger.warning("Could not read default site configs: %s", str(e))
    return []


def parse_incoming_event(event: dict) -> list:
    """
    Parse event to extract list of target site job configurations.
    Supports API Gateway POST, EventBridge, SQS, and direct invocations.
    """
    jobs = []

    # 1. API Gateway REST trigger
    if "body" in event and event.get("body"):
        body = event["body"]
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except Exception:
                body = {}

        if isinstance(body, dict):
            # Check if this is a save_target action
            if body.get("action") == "save_target":
                return []

            target_url = body.get("target_url")
            target_id = body.get("target_id") or body.get("site_id")
            site_name = body.get("display_name") or body.get("site_name")
            content_type = body.get("content_type") or body.get("product_type") or ""

            if not target_id and target_url:
                target_id = sanitize_site_id(site_name or target_url)

            if target_id or target_url:
                job_cfg = {
                    "site_id": target_id or "books_toscrape",
                    "target_id": target_id or "books_toscrape",
                    "site_name": site_name or target_id,
                    "display_name": site_name or target_id,
                    "target_url": target_url,
                    "content_type": content_type,
                    "extraction_type": body.get("extraction_type", "generic" if not body.get("container_selector") else "custom"),
                    "container_selector": body.get("container_selector"),
                    "next_page_selector": body.get("next_page_selector"),
                    "fields": body.get("fields", {}),
                    "validation_rules": body.get("validation_rules", {}),
                    "page_limit": body.get("page_limit", 1),
                    "timeout_seconds": body.get("timeout_seconds", 15),
                    "triggered_by": "api_gateway",
                }
                if body.get("config_override"):
                    job_cfg["config_override"] = body["config_override"]
                jobs.append(job_cfg)

    # 2. SQS trigger
    elif "Records" in event and event["Records"] and "s3" not in event["Records"][0]:
        for rec in event["Records"]:
            try:
                body = json.loads(rec.get("body", "{}"))
                target_id = body.get("target_id") or body.get("site_id")
                target_url = body.get("target_url")
                if not target_id and target_url:
                    target_id = sanitize_site_id(target_url)
                if target_id:
                    jobs.append({
                        "site_id": target_id,
                        "target_id": target_id,
                        "site_name": body.get("display_name") or body.get("site_name", target_id),
                        "display_name": body.get("display_name") or body.get("site_name", target_id),
                        "target_url": target_url,
                        "content_type": body.get("content_type") or body.get("product_type") or "",
                        "extraction_type": body.get("extraction_type", "generic"),
                        "container_selector": body.get("container_selector"),
                        "fields": body.get("fields", {}),
                        "page_limit": body.get("page_limit", 1),
                        "timeout_seconds": body.get("timeout_seconds", 15),
                        "triggered_by": "sqs_queue",
                    })
            except Exception:
                pass

    # 3. Direct or EventBridge trigger specifying a site
    elif "site_id" in event or "target_id" in event or "target_url" in event:
        target_url = event.get("target_url")
        target_id = event.get("target_id") or event.get("site_id")
        site_name = event.get("display_name") or event.get("site_name")
        if not target_id and target_url:
            target_id = sanitize_site_id(site_name or target_url)

        jobs.append({
            "site_id": target_id or "books_toscrape",
            "target_id": target_id or "books_toscrape",
            "site_name": site_name or target_id,
            "display_name": site_name or target_id,
            "target_url": target_url,
            "content_type": event.get("content_type") or event.get("product_type") or "",
            "extraction_type": event.get("extraction_type", "generic"),
            "container_selector": event.get("container_selector"),
            "fields": event.get("fields", {}),
            "page_limit": event.get("page_limit", 1),
            "timeout_seconds": event.get("timeout_seconds", 15),
            "triggered_by": "direct" if "source" not in event else "eventbridge",
        })

    # 4. Scheduled EventBridge rule without specific site -> trigger all enabled sites
    else:
        for sid in get_enabled_sites():
            jobs.append({
                "site_id": sid,
                "target_id": sid,
                "triggered_by": "eventbridge_schedule",
            })

    return jobs


def enqueue_job_to_sqs(queue_url: str, job_input: dict) -> dict:
    """Enqueue a scraping job into the Amazon SQS Job Queue."""
    if not queue_url:
        return {"status": "SKIPPED", "message": "No SQS Queue URL provided"}

    try:
        sqs_client = boto3.client("sqs", region_name=DEFAULT_REGION)
        resp = sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(job_input),
        )
        logger.info("Enqueued job to SQS: %s (MessageId=%s)", job_input.get("site_id"), resp.get("MessageId"))
        return {
            "status": "ENQUEUED",
            "messageId": resp.get("MessageId"),
            "site_id": job_input.get("site_id"),
        }
    except Exception as e:
        logger.warning("Could not enqueue job to SQS: %s", str(e))
        return {"status": "FAILED", "error": str(e), "site_id": job_input.get("site_id")}


def start_state_machine_execution(state_machine_arn: str, job_input: dict) -> dict:
    """Start an execution of the Step Functions State Machine."""
    clean_site_id = re.sub(r"[^a-zA-Z0-9_-]", "-", job_input["site_id"])[:35]
    execution_name = f"scrape-{clean_site_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
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
    except Exception as e:
        logger.warning("Could not start Step Functions execution: %s", str(e))
        return {
            "executionArn": "",
            "executionName": execution_name,
            "status": "FAILED",
            "error": str(e),
            "input": job_input,
        }


def describe_sfn_execution(execution_arn: str) -> dict:
    """Describe a Step Functions execution to return its real status, timestamps, and output."""
    if not execution_arn:
        return {"status": "UNKNOWN", "error": "No execution_arn provided"}

    if "simulated" in execution_arn:
        return {
            "executionArn": execution_arn,
            "status": "SUCCEEDED",
            "startDate": datetime.now(timezone.utc).isoformat(),
            "stopDate": datetime.now(timezone.utc).isoformat(),
            "output": {"status": "SUCCESS", "records_count": 20},
        }

    try:
        sfn_client = boto3.client("stepfunctions", region_name=DEFAULT_REGION)
        desc = sfn_client.describe_execution(executionArn=execution_arn)
        output_data = None
        if desc.get("output"):
            try:
                output_data = json.loads(desc["output"])
            except Exception:
                output_data = desc["output"]

        err_cause = desc.get("cause")
        err_name = desc.get("error")

        # If execution failed, retrieve specific cause from execution history events
        if desc.get("status") == "FAILED":
            try:
                hist = sfn_client.get_execution_history(
                    executionArn=execution_arn,
                    reverseOrder=True,
                    maxResults=25,
                )
                for ev in hist.get("events", []):
                    ev_type = ev.get("type")
                    if ev_type in ("ExecutionFailed", "LambdaFunctionFailed", "TaskFailed"):
                        det = (
                            ev.get("executionFailedEventDetails")
                            or ev.get("lambdaFunctionFailedEventDetails")
                            or ev.get("taskFailedEventDetails")
                            or {}
                        )
                        if det.get("cause") and det["cause"] != "The Cloud Scraper pipeline encountered unrecoverable errors.":
                            raw_cause = det["cause"]
                            try:
                                parsed = json.loads(raw_cause)
                                if isinstance(parsed, dict) and parsed.get("errorMessage"):
                                    err_cause = parsed["errorMessage"]
                                elif isinstance(parsed, dict) and parsed.get("error"):
                                    err_cause = parsed["error"]
                                else:
                                    err_cause = raw_cause
                            except Exception:
                                err_cause = raw_cause
                        if det.get("error") and det["error"] != "PipelineExecutionError":
                            err_name = det["error"]

                    # Also inspect TaskStateExited / LambdaFunctionSucceeded if Lambda returned failure status
                    if ev_type in ("TaskStateExited", "LambdaFunctionSucceeded"):
                        details = ev.get("stateExitedEventDetails") or ev.get("lambdaFunctionSucceededEventDetails") or {}
                        out_str = details.get("output")
                        if out_str and ('"FAILURE"' in out_str or '"error"' in out_str):
                            try:
                                out_obj = json.loads(out_str)
                                if isinstance(out_obj, dict) and out_obj.get("error"):
                                    err_cause = out_obj["error"]
                                    if out_obj.get("error_type"):
                                        err_name = out_obj["error_type"]
                                    break
                            except Exception:
                                pass
            except Exception as hist_err:
                logger.debug("Could not inspect execution history for failure details: %s", str(hist_err))

        return {
            "executionArn": desc.get("executionArn"),
            "executionName": desc.get("name"),
            "status": desc.get("status"),
            "startDate": str(desc.get("startDate")),
            "stopDate": str(desc.get("stopDate")),
            "output": output_data,
            "error": err_name,
            "cause": err_cause,
        }
    except Exception as e:
        logger.error("Failed describing Step Functions execution %s: %s", execution_arn, str(e))
        return {"status": "ERROR", "executionArn": execution_arn, "error": str(e)}


def lambda_handler(event, context=None):
    """
    AWS Lambda Handler for Job Dispatching and API Controller.
    Supports GET (status, results, targets, metrics) and POST (start scrape, save target).
    """
    logger.info("Dispatcher received event: %s", json.dumps(event))

    state_machine_arn = os.environ.get("STEP_FUNC_ARN", "")
    bucket_name = os.environ.get("S3_BUCKET_NAME", "")
    dynamodb_table = os.environ.get("DYNAMODB_TABLE_NAME", "TheCloudScraper-Records")
    queue_url = os.environ.get("SQS_QUEUE_URL", "")

    http_method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method", "")
    http_method = http_method.upper() if http_method else ""

    # Handle CORS OPTIONS preflight
    if http_method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"status": "OK"}),
        }

    # =========================================================================
    # Handle GET requests: execution status, live results, targets, overview
    # =========================================================================
    if http_method == "GET":
        query_params = event.get("queryStringParameters") or {}
        execution_arn = query_params.get("execution_arn")
        action = query_params.get("action", "").lower()

        # 1. Execution status lookup
        if execution_arn or action == "status":
            arn = execution_arn or query_params.get("arn")
            result = describe_sfn_execution(arn)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(result),
            }

        # 2. Persisted records lookup from DynamoDB
        if action == "results":
            site_id = query_params.get("site_id", "")
            limit = int(query_params.get("limit", 100))
            records = dynamodb_store.get_stored_records(dynamodb_table, site_id=site_id, limit=limit)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({
                    "status": "SUCCESS",
                    "site_id": site_id or "all",
                    "count": len(records),
                    "records": records,
                }),
            }

        # 3. Targets lookup: DynamoDB stored targets + default sites
        if action == "targets":
            custom_targets = dynamodb_store.list_target_configs(dynamodb_table)
            default_sites = get_default_site_configs()
            # Combine targets, prioritizing DynamoDB
            seen_ids = set()
            all_targets = []
            for ct in custom_targets:
                seen_ids.add(ct["site_id"])
                all_targets.append(ct)
            for ds in default_sites:
                if ds.get("site_id") not in seen_ids:
                    seen_ids.add(ds["site_id"])
                    all_targets.append(ds)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({
                    "status": "SUCCESS",
                    "count": len(all_targets),
                    "targets": all_targets,
                }),
            }

        # 4. Metrics & telemetry overview
        if action == "metrics" or action == "overview":
            dlq_url = os.environ.get("SQS_DLQ_URL", "")
            dlq_count = 0
            if dlq_url:
                try:
                    sqs = boto3.client("sqs", region_name=DEFAULT_REGION)
                    attrs = sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["ApproximateNumberOfMessages"])
                    dlq_count = int(attrs.get("Attributes", {}).get("ApproximateNumberOfMessages", 0))
                except Exception:
                    pass

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({
                    "status": "ONLINE",
                    "region": DEFAULT_REGION,
                    "dynamodb_table": dynamodb_table,
                    "s3_data_lake": bucket_name,
                    "state_machine_arn": state_machine_arn,
                    "dlq_messages_visible": dlq_count,
                }),
            }

        # 5. Preflight compatibility check
        if action == "preflight":
            target_url = query_params.get("url") or query_params.get("target_url") or ""
            timeout = int(query_params.get("timeout", 8))
            preflight_result = scraper.run_preflight_check(target_url, timeout=timeout)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(preflight_result),
            }

        # Default GET response
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "service": "The Cloud Scraper API Gateway",
                "status": "ONLINE",
                "region": DEFAULT_REGION,
                "supported_actions": ["status", "results", "targets", "metrics", "preflight"],
            }),
        }

    # =========================================================================
    # Handle POST requests: Save target config or dispatch scrape job
    # =========================================================================
    if http_method == "POST":
        body_obj = {}
        if "body" in event and event.get("body"):
            try:
                body_obj = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
            except Exception:
                body_obj = {}

        # Check if request is a preflight check
        if body_obj.get("action") == "preflight":
            target_url = body_obj.get("target_url") or body_obj.get("url") or ""
            timeout = int(body_obj.get("timeout_seconds", 8))
            preflight_result = scraper.run_preflight_check(target_url, timeout=timeout)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(preflight_result),
            }

        # Check if request is saving a target configuration
        if body_obj.get("action") == "save_target" or body_obj.get("target_config"):
            target_data = body_obj.get("target") or body_obj.get("target_config") or body_obj
            success, err = dynamodb_store.save_target_config(dynamodb_table, target_data)
            status_code = 200 if success else 400
            return {
                "statusCode": status_code,
                "headers": CORS_HEADERS,
                "body": json.dumps({
                    "status": "SUCCESS" if success else "FAILURE",
                    "message": "Target configuration saved successfully" if success else f"Failed saving target: {err}",
                    "target_id": target_data.get("site_id") or target_data.get("target_id"),
                }),
            }

    # Dispatch scrape jobs (API Gateway POST /scrape, SQS, or EventBridge)
    jobs = parse_incoming_event(event)

    # If triggered by SQS, execute each message directly via Step Functions
    is_sqs_trigger = "Records" in event and event["Records"] and "s3" not in event["Records"][0]

    # If multiple jobs from a scheduled event and queue_url is set, distribute via SQS
    if len(jobs) > 1 and queue_url and not is_sqs_trigger:
        enqueued_results = []
        for job in jobs:
            job["bucket_name"] = bucket_name
            job["dynamodb_table"] = dynamodb_table
            res = enqueue_job_to_sqs(queue_url, job)
            enqueued_results.append(res)
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "status": "SUCCESS",
            "mode": "SQS_DISTRIBUTION",
            "enqueued_count": len(enqueued_results),
            "jobs": enqueued_results,
        }

    # Otherwise, execute Step Functions directly for each job
    results = []
    for job in jobs:
        job["bucket_name"] = bucket_name
        job["dynamodb_table"] = dynamodb_table
        res = start_state_machine_execution(state_machine_arn, job)
        results.append(res)

    is_api_request = bool(http_method)
    if is_api_request:
        return {
            "statusCode": 202,
            "headers": CORS_HEADERS,
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
    test_event = {"site_id": "books_toscrape"}
    res = lambda_handler(test_event)
    print("Dispatch result:", json.dumps(res, indent=2))