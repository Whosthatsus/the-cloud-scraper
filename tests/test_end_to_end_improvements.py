"""
Unit and Integration Tests for End-to-End Improvements:
Error Transparency, Advisory robots.txt, Embedded JSON & SPA Parsing,
Content-Type Filtering, Unified Schema, DynamoDB Auto-Registration, and API Diagnostics.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import scraper
import validation
import transformation
import dynamodb_store
import notification
import start_step_function


class TestEndToEndImprovements(unittest.TestCase):

    def setUp(self):
        self.sample_html_savana = """
        <!DOCTYPE html>
        <html>
        <head><title>Savana - Category Jeans</title></head>
        <body>
        <div id="root"></div>
        <script>
        window.$preData = {
            "vtoken": "12345",
            "/n/api/buyer/guide/user/goods-flow/pagelist-activity": {
                "goodsList": [
                    {
                        "goodsId": 2185162,
                        "goodsName": "High Waist Camouflage Green Pintuck Seam Wide Leg Jeans",
                        "promotePrice": 1253,
                        "promotePriceText": "₹1,253",
                        "salePrice": 1790,
                        "salePriceText": "₹1,790",
                        "copywritting": "Camouflage Green denim wide leg pants",
                        "imageList": [{"goodsThumb": "https://img.savana.com/pic1.jpg"}]
                    },
                    {
                        "goodsId": 2194632,
                        "goodsName": "High Waist Dark Wash Embroidered Wide Leg Denim",
                        "promotePrice": 1490,
                        "promotePriceText": "₹1,490",
                        "salePrice": 2100,
                        "salePriceText": "₹2,100",
                        "copywritting": "Dark wash vintage denim",
                        "imageList": [{"goodsThumb": "https://img.savana.com/pic2.jpg"}]
                    },
                    {
                        "goodsId": 2200100,
                        "goodsName": "Floral Summer Knit Top",
                        "promotePrice": 899,
                        "promotePriceText": "₹899",
                        "salePrice": 1299,
                        "salePriceText": "₹1,299",
                        "copywritting": "Knit crop top",
                        "imageList": [{"goodsThumb": "https://img.savana.com/pic3.jpg"}]
                    }
                ]
            }
        };
        </script>
        </body>
        </html>
        """

        self.sample_html_savana_detail = """
        <!DOCTYPE html>
        <html>
        <head><title>High Waist Medium Wash Straight Leg Jeans</title></head>
        <body>
        <div id="root"></div>
        <script>
        window.$preData = {
            "vtoken": "12345",
            "/n/api/intention/item/v4/detail": {
                "goodsId": 2298832,
                "goodsName": "High Waist Medium Wash Straight Leg Jeans",
                "salesPrice": 1790,
                "promotePrice": 1253,
                "salesPriceText": "₹1,790",
                "promotePriceText": "₹1,253",
                "discountValueText": "30%OFF",
                "goodsDesc": "High quality straight leg jeans medium wash"
            }
        };
        </script>
        </body>
        </html>
        """

        self.sample_nextjs_html = """
        <!DOCTYPE html>
        <html>
        <body>
        <div id="__next"></div>
        <script id="__NEXT_DATA__" type="application/json">
        {
            "props": {
                "pageProps": {
                    "articles": [
                        {
                            "headline": "Serverless Architecture Trends 2026",
                            "url": "/articles/serverless-2026",
                            "description": "Deep dive into AWS Lambda and Step Functions advancements.",
                            "type": "technology"
                        },
                        {
                            "headline": "Scaling DynamoDB Multi-Region",
                            "url": "/articles/dynamodb-scale",
                            "description": "Global table design patterns.",
                            "type": "database"
                        }
                    ]
                }
            }
        }
        </script>
        </body>
        </html>
        """

        self.sample_jsonld_html = """
        <!DOCTYPE html>
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Classic Oxford Cotton Shirt",
            "description": "Premium 100% breathable organic cotton shirt.",
            "url": "https://example.com/products/oxford-shirt",
            "offers": {
                "@type": "Offer",
                "price": 49.99,
                "priceCurrency": "USD"
            }
        }
        </script>
        </head>
        <body><h1>Classic Oxford Cotton Shirt</h1></body>
        </html>
        """

    # 1. State Machine & Error Transparency Tests
    def test_dlq_preserves_error_details(self):
        """Verify that Route Failure to DLQ preserves error fields without wiping execution state."""
        template_path = os.path.join(os.path.dirname(__file__), "..", "template.yml")
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('"ResultPath": "$.dlq_result"', content)

    def test_fail_execution_dynamic_error_and_cause(self):
        """Verify Step Functions Fail state uses dynamic ErrorPath and CausePath."""
        template_path = os.path.join(os.path.dirname(__file__), "..", "template.yml")
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('"ErrorPath": "$.error_type"', content)
        self.assertIn('"CausePath": "$.error"', content)

    def test_notification_preserves_error_and_error_type(self):
        """Verify notification Lambda handler outputs clean error and error_type fields for Fail state."""
        event = {
            "status": "FAILURE",
            "site_id": "savana_test",
            "error": "Access Denied by anti-bot verification",
            "error_type": "ACCESS_DENIED",
        }
        res = notification.lambda_handler(event)
        self.assertEqual(res["error"], "Access Denied by anti-bot verification")
        self.assertEqual(res["error_type"], "ACCESS_DENIED")

    def test_describe_sfn_execution_extracts_actual_cause(self):
        """Verify describe_sfn_execution prioritizes genuine cause over generic fallback."""
        mock_sfn = MagicMock()
        mock_sfn.describe_execution.return_value = {
            "executionArn": "arn:aws:states:ap-southeast-2:123456789:execution:sm:test",
            "name": "test-execution",
            "status": "FAILED",
            "startDate": "2026-10-24T00:00:00Z",
            "stopDate": "2026-10-24T00:00:05Z",
            "cause": "HTTP 403 Forbidden: Target server refused access",
            "error": "ACCESS_DENIED",
        }
        with patch("boto3.client", return_value=mock_sfn):
            res = start_step_function.describe_sfn_execution("arn:aws:states:ap-southeast-2:123456789:execution:sm:test")
            self.assertEqual(res["status"], "FAILED")
            self.assertEqual(res["cause"], "HTTP 403 Forbidden: Target server refused access")
            self.assertEqual(res["error"], "ACCESS_DENIED")

    def test_describe_sfn_execution_lambda_output_inspection(self):
        """Verify describe_sfn_execution inspects history TaskStateExited output if cause was generic."""
        mock_sfn = MagicMock()
        mock_sfn.describe_execution.return_value = {
            "executionArn": "arn:aws:states:ap-southeast-2:123456789:execution:sm:test",
            "name": "test-execution",
            "status": "FAILED",
            "cause": "The Cloud Scraper pipeline encountered unrecoverable errors.",
            "error": "PipelineExecutionError",
        }
        mock_sfn.get_execution_history.return_value = {
            "events": [
                {
                    "type": "TaskStateExited",
                    "stateExitedEventDetails": {
                        "name": "Scrape Target Website",
                        "output": json.dumps({
                            "status": "FAILURE",
                            "error": "Target website robots.txt policy blocked path",
                            "error_type": "ROBOTS_DISALLOWED"
                        })
                    }
                }
            ]
        }
        with patch("boto3.client", return_value=mock_sfn):
            res = start_step_function.describe_sfn_execution("arn:aws:states:ap-southeast-2:123456789:execution:sm:test")
            self.assertEqual(res["cause"], "Target website robots.txt policy blocked path")
            self.assertEqual(res["error"], "ROBOTS_DISALLOWED")

    # 2. Advisory Robots.txt Tests
    def test_robots_txt_advisory_allowed(self):
        """Verify on-demand scrape proceeds with advisory warning when robots.txt disallows."""
        event = {
            "site_id": "test_advisory",
            "target_url": "https://example.com/disallowed-path",
            "mock_html": "<html><body><h1>Allowed Under Advisory</h1></body></html>",
        }
        with patch("scraper.check_robots_allowed", return_value=False):
            res = scraper.lambda_handler(event)
            self.assertEqual(res["status"], "SUCCESS")
            self.assertEqual(len(res["records"]), 1)

    def test_robots_txt_strict_enforcement_blocks(self):
        """Verify robots.txt halts with 403 when strict_robots is explicitly requested."""
        event = {
            "site_id": "test_strict",
            "target_url": "https://example.com/disallowed-path",
            "strict_robots": True,
        }
        with patch("scraper.validate_target_url_security", return_value=(True, "")):
            with patch("scraper.check_robots_allowed", return_value=False):
                res = scraper.lambda_handler(event)
                self.assertEqual(res["statusCode"], 403)
                self.assertEqual(res["error_type"], "ROBOTS_DISALLOWED")

    def test_robots_allowed_flag_recorded_in_metadata(self):
        """Verify robots_allowed boolean is recorded in response metadata."""
        event = {
            "site_id": "test_meta",
            "target_url": "https://example.com/items",
            "mock_html": "<html><body><article><h2>Item 1</h2><p>Desc 1</p></article><article><h2>Item 2</h2><p>Desc 2</p></article></body></html>",
        }
        res = scraper.lambda_handler(event)
        self.assertIn("robots_allowed", res)

    # 3. Embedded JSON & SPA Parsing Tests
    def test_embedded_json_savana_predata_activity_listing(self):
        """Verify extraction of 36 goods items from Savana window.$preData activity pagelist."""
        cfg = {
            "base_url": "https://www.savana.com/",
            "target_url": "https://www.savana.com/activity/12879",
            "site_name": "Savana Jeans",
            "site_id": "savana_jeans",
        }
        records = scraper.extract_embedded_json_records(self.sample_html_savana, cfg)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["title"], "High Waist Camouflage Green Pintuck Seam Wide Leg Jeans")
        self.assertEqual(records[0]["price"], 1253.0)
        self.assertIn("details/2185162", records[0]["url"])

    def test_embedded_json_savana_single_product_detail(self):
        """Verify single product detail extraction from Savana window.$preData."""
        cfg = {
            "base_url": "https://www.savana.com/",
            "target_url": "https://www.savana.com/details/2298832",
            "site_name": "Savana Detail",
            "site_id": "savana_detail",
        }
        records = scraper.extract_embedded_json_records(self.sample_html_savana_detail, cfg)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "High Waist Medium Wash Straight Leg Jeans")
        self.assertEqual(records[0]["price"], 1253.0)
        self.assertTrue(records[0]["metadata"].get("is_single_product"))

    def test_embedded_json_nextjs_hydration(self):
        """Verify extraction of articles from Next.js __NEXT_DATA__."""
        cfg = {
            "base_url": "https://techblog.com/",
            "target_url": "https://techblog.com/archive",
            "site_name": "Tech Blog",
            "site_id": "tech_blog",
        }
        records = scraper.extract_embedded_json_records(self.sample_nextjs_html, cfg)
        self.assertEqual(len(records), 2)
        self.assertIn("Serverless Architecture Trends", records[0]["title"])
        self.assertIn("articles/serverless-2026", records[0]["url"])

    def test_embedded_json_schema_org_jsonld(self):
        """Verify extraction of product microdata from Schema.org application/ld+json."""
        cfg = {
            "base_url": "https://example.com/",
            "target_url": "https://example.com/products/oxford-shirt",
            "site_name": "Example Store",
            "site_id": "example_store",
        }
        records = scraper.extract_embedded_json_records(self.sample_jsonld_html, cfg)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "Classic Oxford Cotton Shirt")
        self.assertEqual(records[0]["price"], 49.99)
        self.assertEqual(records[0]["content_type"], "product")

    def test_detect_page_incompatibility_spa_with_json_passes(self):
        """Verify an SPA page containing embedded JSON state is NOT falsely flagged incompatible."""
        is_incompatible, reason = scraper.detect_page_incompatibility(self.sample_html_savana, 200)
        self.assertFalse(is_incompatible)
        self.assertEqual(reason, "")

    def test_detect_page_incompatibility_antibot_challenge_detected(self):
        """Verify active anti-bot challenge interstitial is detected."""
        challenge_html = "<html><body><script src='cf-chl-bypass'></script>Checking your browser...</body></html>"
        is_incompatible, reason = scraper.detect_page_incompatibility(challenge_html, 200)
        self.assertTrue(is_incompatible)
        self.assertIn("Anti-Bot Challenge", reason)

    # 4. Content-Type Filtering Tests
    def test_content_type_filtering_jeans(self):
        """Verify jeans filter matches only jeans and denim products."""
        rec1 = {"title": "Blue Denim Straight Jeans", "description": "Comfort stretch"}
        rec2 = {"title": "Silk Floral Blouse", "description": "Summer edition"}
        self.assertTrue(scraper.matches_content_type(rec1, "jeans"))
        self.assertFalse(scraper.matches_content_type(rec2, "jeans"))

    def test_content_type_filtering_bottoms(self):
        """Verify bottoms filter matches trousers, pants, jeans, and skirts."""
        rec_pants = {"title": "Pleated Linen Trousers", "description": "Relaxed fit"}
        rec_skirt = {"title": "A-Line Corduroy Skirt", "description": "Casual wear"}
        rec_shirt = {"title": "Cotton Graphic Tee", "description": "Crew neck"}
        self.assertTrue(scraper.matches_content_type(rec_pants, "bottoms"))
        self.assertTrue(scraper.matches_content_type(rec_skirt, "bottoms"))
        self.assertFalse(scraper.matches_content_type(rec_shirt, "bottoms"))

    def test_content_type_filtering_books(self):
        """Verify books filter matches book and literature keywords."""
        rec_book = {"title": "Clean Code", "description": "A Handbook of Agile Software Craftsmanship"}
        rec_device = {"title": "Wireless Gaming Mouse", "description": "RGB Ergonomic"}
        self.assertTrue(scraper.matches_content_type(rec_book, "books"))
        self.assertFalse(scraper.matches_content_type(rec_device, "books"))

    def test_content_type_filtering_news(self):
        """Verify news filter matches article and headline keywords."""
        rec_news = {"title": "Open Source Foundation Releases Report", "description": "Annual security update"}
        rec_item = {"title": "Coffee Mug", "description": "Ceramic 12oz"}
        self.assertTrue(scraper.matches_content_type(rec_news, "news"))
        self.assertFalse(scraper.matches_content_type(rec_item, "news"))

    def test_content_type_filtering_zero_matches_fallback(self):
        """Verify parse_html_records falls back safely without returning empty list when filter matches zero."""
        cfg = {
            "base_url": "https://www.savana.com/",
            "target_url": "https://www.savana.com/activity/12879",
            "content_type": "motorcycle_helmets",  # Won't match jeans or knit tops
        }
        records = scraper.parse_html_records(self.sample_html_savana, cfg)
        self.assertGreater(len(records), 0)

    # 5. Schema Normalization & Deduplication Tests
    def test_standardized_record_schema(self):
        """Verify transformed records adhere to the unified standard schema."""
        raw = {
            "title": " High Waist Jeans ",
            "price": "₹1,253.00",
            "url": "https://www.savana.com/details/2298832",
            "description": "Premium denim jeans",
            "content_type": "jeans",
            "display_name": "Savana Fashion",
            "custom_attribute": "wash_dark",
        }
        res = transformation.clean_and_normalize_record(raw, "savana_jeans", "https://www.savana.com/", "2026-10-24T00:00:00Z")
        self.assertEqual(res["target_id"], "savana_jeans")
        self.assertEqual(res["site_id"], "savana_jeans")
        self.assertEqual(res["display_name"], "Savana Fashion")
        self.assertEqual(res["title"], "High Waist Jeans")
        self.assertEqual(res["price"], 1253.0)
        self.assertEqual(res["description"], "Premium denim jeans")
        self.assertEqual(res["content_type"], "jeans")
        self.assertEqual(res["url"], "https://www.savana.com/details/2298832")
        self.assertTrue(res["record_id"].startswith("savana_jeans#"))
        self.assertIn("custom_attribute", res["metadata"])

    def test_transformation_clean_text_mojibake(self):
        """Verify cleaning of unicode mojibake currency symbols."""
        cleaned = transformation.clean_text("Â£34.99   special\u00c2\u00a3offer  ")
        self.assertEqual(cleaned, "£34.99 special£offer")

    # 6. Storage & Registry Tests
    def test_dynamodb_store_auto_registration(self):
        """Verify dynamodb_store auto-registers target configuration upon successful storage."""
        mock_table = MagicMock()
        mock_ddb = MagicMock()
        mock_ddb.Table.return_value = mock_table

        with patch("boto3.resource", return_value=mock_ddb):
            event = {
                "site_id": "test_auto_reg",
                "display_name": "Test Auto Target",
                "target_url": "https://example.com/items",
                "records": [{"record_id": "test_auto_reg#1", "title": "Item 1", "price": 10.0}],
                "dynamodb_table": "the-cloud-scraper-records",
            }
            res = dynamodb_store.lambda_handler(event)
            self.assertEqual(res["status"], "SUCCESS")
            # Verify put_item was called for TARGET_CONFIG
            config_call_found = any(
                call[1].get("Item", {}).get("record_id") == "TARGET_CONFIG"
                for call in mock_table.put_item.call_args_list
            )
            self.assertTrue(config_call_found)

    def test_start_step_function_action_targets(self):
        """Verify GET /scrape?action=targets returns merged targets."""
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [
                {
                    "site_id": "CONFIG#savana_jeans",
                    "target_id": "savana_jeans",
                    "site_name": "Savana Jeans Catalog",
                    "target_url": "https://www.savana.com/activity/12879",
                    "record_id": "TARGET_CONFIG"
                }
            ]
        }
        mock_ddb = MagicMock()
        mock_ddb.Table.return_value = mock_table

        with patch("boto3.resource", return_value=mock_ddb):
            event = {
                "httpMethod": "GET",
                "queryStringParameters": {"action": "targets"}
            }
            res = start_step_function.lambda_handler(event)
            self.assertEqual(res["statusCode"], 200)
            body = json.loads(res["body"])
            target_ids = [t["site_id"] for t in body["targets"]]
            self.assertIn("savana_jeans", target_ids)
            self.assertIn("books_toscrape", target_ids)

    def test_zero_records_distinguished_from_infrastructure_failure(self):
        """Verify validation Lambda flags empty records with ZERO_RECORDS_EXTRACTED error_type."""
        event = {
            "site_id": "empty_site",
            "records": [],
        }
        res = validation.lambda_handler(event)
        self.assertEqual(res["status"], "FAILURE")
        self.assertEqual(res["error_type"], "ZERO_RECORDS_EXTRACTED")
        self.assertIn("No records found", res["error"])

    def test_full_pipeline_runner_end_to_end_local(self):
        """Verify full simulated execution flow from scraper to validation, transformation, and storage."""
        # Step 1: Scrape
        scrape_event = {
            "site_id": "test_e2e",
            "target_url": "https://www.savana.com/activity/12879",
            "mock_html": self.sample_html_savana,
            "content_type": "jeans",
        }
        scrape_res = scraper.lambda_handler(scrape_event)
        self.assertEqual(scrape_res["status"], "SUCCESS")
        self.assertEqual(len(scrape_res["records"]), 2)  # 2 jeans records, 1 knit top filtered

        # Step 2: Validate
        val_res = validation.lambda_handler(scrape_res)
        self.assertEqual(val_res["status"], "SUCCESS")
        self.assertEqual(val_res["valid_count"], 2)

        # Step 3: Transform
        trans_res = transformation.lambda_handler(val_res)
        self.assertEqual(trans_res["status"], "SUCCESS")
        self.assertEqual(trans_res["total_transformed"], 2)

        # Step 4: Storage
        mock_table = MagicMock()
        mock_ddb = MagicMock()
        mock_ddb.Table.return_value = mock_table
        with patch("boto3.resource", return_value=mock_ddb):
            store_res = dynamodb_store.lambda_handler(trans_res)
            self.assertEqual(store_res["status"], "SUCCESS")
            self.assertEqual(store_res["records_count"], 2)


if __name__ == "__main__":
    unittest.main()
