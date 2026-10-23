"""
Unit and integration tests for Preflight Compatibility Checks, Anti-Bot Challenge Detection,
Client-Side SPA Incompatibility Diagnosis, and HTTP Error Classification.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))
import scraper
import start_step_function


class TestPreflightAndErrorClassification(unittest.TestCase):

    def test_preflight_blocks_ssrf_metadata(self):
        """Preflight must reject cloud metadata endpoints before issuing outbound requests."""
        result = scraper.run_preflight_check("http://169.254.169.254/latest/meta-data")
        self.assertFalse(result["is_compatible"])
        self.assertEqual(result["status"], "REJECTED_SSRF")
        self.assertIn("SSRF", result["summary"])

    def test_preflight_blocks_localhost(self):
        """Preflight must reject localhost and loopback targets."""
        result = scraper.run_preflight_check("http://127.0.0.1:8080/admin")
        self.assertFalse(result["is_compatible"])
        self.assertEqual(result["status"], "REJECTED_SSRF")

    @patch("scraper.requests.get")
    def test_preflight_compatible_html_page(self, mock_get):
        """Preflight must confirm compatibility for standard HTML web pages."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.content = b"<html><head><title>Test Page</title></head><body><h1>Article 1</h1><p>Substantive text content here.</p></body></html>"
        mock_resp.text = mock_resp.content.decode("utf-8")
        mock_resp.url = "https://example.org/news"
        mock_get.return_value = mock_resp

        result = scraper.run_preflight_check("https://example.org/news")
        self.assertTrue(result["is_compatible"])
        self.assertEqual(result["status"], "COMPATIBLE")
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["page_title"], "Test Page")
        self.assertFalse(result["requires_javascript"])

    @patch("scraper.requests.get")
    def test_preflight_detects_http_403_access_denied(self, mock_get):
        """Preflight accurately reports HTTP 403 Forbidden as ACCESS_DENIED."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.text = "<html><body>403 Forbidden</body></html>"
        mock_get.return_value = mock_resp

        result = scraper.run_preflight_check("https://example.com/protected")
        self.assertFalse(result["is_compatible"])
        self.assertEqual(result["status"], "ACCESS_DENIED")
        self.assertEqual(result["status_code"], 403)
        self.assertIn("Access Denied", result["summary"])

    @patch("scraper.requests.get")
    def test_preflight_detects_anti_bot_interstitial(self, mock_get):
        """Preflight detects Akamai / Cloudflare challenge interstitial pages."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.text = '<html><head><meta http-equiv="refresh" content="5; URL=\'/?bm-verify=AAQAAAAO\'"></head><body><iframe src="/interstitial"></iframe></body></html>'
        mock_get.return_value = mock_resp

        result = scraper.run_preflight_check("https://www.example-store.com/")
        self.assertFalse(result["is_compatible"])
        self.assertEqual(result["status"], "INCOMPATIBLE_STRUCTURE")
        self.assertTrue(result["requires_javascript"])
        self.assertIn("Anti-Bot Challenge", result["summary"])

    def test_detect_page_incompatibility_spa_skeleton(self):
        """Detect client-side Single Page Application skeletons that lack server-rendered text."""
        spa_html = '<html><head><title>App</title><script src="bundle.js"></script></head><body><div id="root"></div></body></html>'
        is_incompat, reason = scraper.detect_page_incompatibility(spa_html, 200)
        self.assertTrue(is_incompat)
        self.assertIn("Single Page Application", reason)

    @patch("scraper.fetch_page_content")
    def test_lambda_handler_classifies_403_non_retryable(self, mock_fetch):
        """Scraper lambda_handler must return 403 and is_retryable=False when server rejects access."""
        resp = MagicMock()
        resp.status_code = 403
        http_err = requests.exceptions.HTTPError("403 Client Error: Forbidden", response=resp)
        mock_fetch.side_effect = http_err

        event = {"site_id": "test_forbidden", "target_url": "https://example.com/protected"}
        result = scraper.lambda_handler(event)
        self.assertEqual(result["status"], "FAILURE")
        self.assertEqual(result["statusCode"], 403)
        self.assertFalse(result["is_retryable"])
        self.assertEqual(result["error_type"], "ACCESS_DENIED")

    @patch("scraper.fetch_page_content")
    def test_lambda_handler_detects_bot_challenge_on_fetch(self, mock_fetch):
        """Scraper lambda_handler must detect anti-bot challenge and flag statusCode=422."""
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "text/html"}
        resp.text = '<html><head><script>/* cf-chl-bypass */</script></head><body>Challenge</body></html>'
        mock_fetch.return_value = resp

        event = {"site_id": "test_bot", "target_url": "https://example.com/cloudflare-challenge"}
        result = scraper.lambda_handler(event)
        self.assertEqual(result["status"], "FAILURE")
        self.assertEqual(result["statusCode"], 422)
        self.assertFalse(result["is_retryable"])
        self.assertEqual(result["error_type"], "JS_RENDER_OR_CHALLENGE_REQUIRED")

    @patch("scraper.run_preflight_check")
    def test_dispatcher_handles_preflight_get(self, mock_preflight):
        """Dispatcher GET request with action=preflight routes to scraper preflight."""
        mock_preflight.return_value = {"is_compatible": True, "status": "COMPATIBLE"}

        event = {
            "httpMethod": "GET",
            "queryStringParameters": {
                "action": "preflight",
                "url": "https://example.org",
            },
        }
        res = start_step_function.lambda_handler(event)
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertTrue(body["is_compatible"])
        mock_preflight.assert_called_once_with("https://example.org", timeout=8)


if __name__ == "__main__":
    unittest.main()
