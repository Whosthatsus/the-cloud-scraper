"""
Tests for General-Purpose Custom Scraping, Generic Extraction, Target Configuration,
and API Gateway Endpoints.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import scraper
import validation
import transformation
import dynamodb_store
import start_step_function
import pipeline_runner

ARBITRARY_NEWS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Tech Careers & Engineering News</title></head>
<body>
  <h1>Latest Technology Openings</h1>
  <div class="job-card">
    <h3 class="role-title"><a href="/jobs/cloud-architect">Senior Cloud Architect</a></h3>
    <p class="summary">Design serverless pipelines on AWS with Step Functions and DynamoDB.</p>
    <span class="location">Sydney, Australia</span>
  </div>
  <div class="job-card">
    <h3 class="role-title"><a href="/jobs/devops-engineer">Principal DevOps Engineer</a></h3>
    <p class="summary">Automate infrastructure deployment using AWS SAM and CloudFormation.</p>
    <span class="location">Remote</span>
  </div>
</body>
</html>
"""

BLOG_ARTICLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Introduction to Serverless Architectures</title></head>
<body>
  <h1>Serverless Data Pipelines on AWS</h1>
  <p>Serverless architectures allow developers to build decoupled, event-driven pipelines.</p>
  <h2>Core Building Blocks</h2>
  <p>AWS Lambda, Step Functions, DynamoDB, and S3 form the foundation of high-throughput data pipelines.</p>
  <h2>Cost Efficiency</h2>
  <p>Pay-per-use billing ensures zero idle costs during inactive periods.</p>
</body>
</html>
"""


class TestCustomScrapingAndAPI(unittest.TestCase):

    def test_generic_html_extraction_on_job_cards(self):
        """Verify generic extractor detects repeating card containers on an arbitrary HTML page."""
        records = scraper.parse_html_records(
            ARBITRARY_NEWS_HTML,
            {
                "site_id": "tech_jobs",
                "base_url": "https://techjobs.example.org/",
                "target_url": "https://techjobs.example.org/listings",
                "extraction_type": "generic",
            },
        )
        self.assertGreaterEqual(len(records), 2)
        self.assertIn("Cloud Architect", records[0]["title"])
        self.assertIn("Step Functions", records[0]["text"])
        self.assertTrue(records[0]["detail_link"].startswith("https://techjobs.example.org/"))

    def test_generic_html_extraction_on_article(self):
        """Verify generic extractor handles heading-and-paragraph documents without card containers."""
        records = scraper.parse_html_records(
            BLOG_ARTICLE_HTML,
            {
                "site_id": "cloud_blog",
                "base_url": "https://blog.example.com/",
                "target_url": "https://blog.example.com/serverless-post",
                "extraction_type": "generic",
            },
        )
        self.assertGreaterEqual(len(records), 1)
        self.assertTrue(any("Serverless" in r["title"] for r in records))
        self.assertTrue(any("AWS" in r["text"] for r in records))

    def test_custom_css_selector_extraction(self):
        """Verify extraction with explicit user-configured CSS selectors."""
        custom_config = {
            "site_id": "tech_jobs_custom",
            "base_url": "https://techjobs.example.org/",
            "target_url": "https://techjobs.example.org/listings",
            "extraction_type": "custom",
            "container_selector": "div.job-card",
            "fields": {
                "role": {"selector": "h3.role-title a", "type": "string", "required": True},
                "job_link": {"selector": "h3.role-title a", "attribute": "href", "type": "url", "required": True},
                "description": {"selector": "p.summary", "type": "string"},
                "location": {"selector": "span.location", "type": "string"},
            },
        }
        records = scraper.parse_html_records(ARBITRARY_NEWS_HTML, custom_config)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["role"], "Senior Cloud Architect")
        self.assertEqual(records[0]["job_link"], "https://techjobs.example.org/jobs/cloud-architect")
        self.assertEqual(records[0]["location"], "Sydney, Australia")

    def test_custom_url_no_silent_fallback_to_books(self):
        """Verify custom URL creates dynamic configuration and does not fallback to books_toscrape."""
        event = {
            "site_id": "custom_target_sydney",
            "site_name": "Sydney Careers Portal",
            "target_url": "https://careers.example.gov.au/vacancies",
            "mock_html": ARBITRARY_NEWS_HTML,
            "extraction_type": "generic",
        }
        result = scraper.lambda_handler(event)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["site_id"], "custom_target_sydney")
        self.assertEqual(result["site_name"], "Sydney Careers Portal")
        self.assertEqual(result["target_url"], "https://careers.example.gov.au/vacancies")
        self.assertNotEqual(result["site_id"], "books_toscrape")
        self.assertGreaterEqual(result["records_count"], 2)

    def test_validation_accepts_generic_records(self):
        """Verify validation succeeds on arbitrary records without expecting price or rating."""
        generic_records = [
            {
                "title": "Principal Architect",
                "text": "AWS cloud migrations and event-driven patterns.",
                "url": "https://example.com/arch",
            }
        ]
        val_event = {
            "site_id": "custom_generic_site",
            "records": generic_records,
            "extraction_type": "generic",
        }
        res = validation.lambda_handler(val_event)
        self.assertEqual(res["Validation"], "SUCCESS")
        self.assertEqual(res["valid_count"], 1)

    def test_transformation_hashes_generic_records(self):
        """Verify transformation handles generic fields and generates stable record_ids."""
        generic_records = [
            {
                "title": "Principal Architect",
                "text": "AWS cloud migrations.",
                "url": "https://example.com/arch",
            }
        ]
        trans_event = {
            "site_id": "custom_generic_site",
            "target_url": "https://example.com/jobs",
            "records": generic_records,
        }
        res = transformation.lambda_handler(trans_event)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["total_transformed"], 1)
        r = res["records"][0]
        self.assertTrue(r["record_id"].startswith("custom_generic_site#"))
        self.assertEqual(r["source_url"], "https://example.com/jobs")

    @patch("start_step_function.boto3.client")
    def test_dispatcher_describes_step_functions_status(self, mock_client):
        """Verify API Gateway GET /scrape?execution_arn=... calls describe_execution."""
        mock_sfn = MagicMock()
        mock_sfn.describe_execution.return_value = {
            "executionArn": "arn:aws:states:ap-southeast-2:123:execution:sm:scrape-custom-1",
            "name": "scrape-custom-1",
            "status": "SUCCEEDED",
            "startDate": "2026-10-23T01:00:00Z",
            "stopDate": "2026-10-23T01:00:04Z",
            "output": json.dumps({"status": "SUCCESS", "records_count": 15}),
        }
        mock_client.return_value = mock_sfn

        event = {
            "httpMethod": "GET",
            "queryStringParameters": {
                "execution_arn": "arn:aws:states:ap-southeast-2:123:execution:sm:scrape-custom-1"
            },
        }
        res = start_step_function.lambda_handler(event)
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertEqual(body["status"], "SUCCEEDED")
        self.assertEqual(body["executionName"], "scrape-custom-1")
        self.assertEqual(body["output"]["records_count"], 15)

    @patch("dynamodb_store.boto3.resource")
    def test_dynamodb_target_config_save_and_list(self, mock_resource):
        """Verify saving and listing custom target configurations in DynamoDB."""
        mock_table = MagicMock()
        mock_ddb = MagicMock()
        mock_ddb.Table.return_value = mock_table
        mock_resource.return_value = mock_ddb

        mock_table.scan.return_value = {
            "Items": [
                {
                    "site_id": "CONFIG#custom_sydney_news",
                    "record_id": "TARGET_CONFIG",
                    "target_id": "custom_sydney_news",
                    "site_name": "Sydney News Wire",
                    "target_url": "https://news.example.com.au/",
                    "extraction_type": "generic",
                    "enabled": True,
                }
            ]
        }

        # Save target
        success, err = dynamodb_store.save_target_config(
            "TestTable",
            {
                "site_id": "custom_sydney_news",
                "site_name": "Sydney News Wire",
                "target_url": "https://news.example.com.au/",
                "extraction_type": "generic",
            },
        )
        self.assertTrue(success)
        mock_table.put_item.assert_called_once()

        # List targets
        targets = dynamodb_store.list_target_configs("TestTable")
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["site_id"], "custom_sydney_news")


if __name__ == "__main__":
    unittest.main()
