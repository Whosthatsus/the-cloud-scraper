"""
Unit tests for the Website Scraper Lambda component (lambda/scraper.py).
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import requests

# Add lambda directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))
import scraper


SAMPLE_BOOKS_HTML = """
<!DOCTYPE html>
<html>
<body>
  <article class="product_pod">
    <h3><a href="catalogue/book-1/index.html" title="Test Book Title">Test Book</a></h3>
    <div class="product_price">
      <p class="price_color">£25.50</p>
      <p class="instock availability">In stock</p>
    </div>
    <p class="star-rating Four"></p>
  </article>
  <article class="product_pod">
    <h3><a href="catalogue/book-2/index.html" title="Second Book">Second Book</a></h3>
    <div class="product_price">
      <p class="price_color">£12.99</p>
      <p class="instock availability">In stock</p>
    </div>
    <p class="star-rating One"></p>
  </article>
</body>
</html>
"""


class TestScraper(unittest.TestCase):

    def test_load_site_config_valid(self):
        """Verify configuration loading for configured test sites."""
        cfg = scraper.load_site_config("books_toscrape")
        self.assertEqual(cfg["site_id"], "books_toscrape")
        self.assertIn("target_url", cfg)
        self.assertIn("container_selector", cfg)

    def test_load_site_config_invalid(self):
        """Verify ValueError raised for unknown site ID."""
        with self.assertRaises(ValueError):
            scraper.load_site_config("non_existent_site_123")

    def test_parse_html_records(self):
        """Verify parsing of HTML into structured dictionaries based on selectors."""
        cfg = {
            "site_id": "books_toscrape",
            "base_url": "https://books.toscrape.com/",
            "container_selector": "article.product_pod",
            "fields": {
                "title": {"selector": "h3 a", "attribute": "title", "type": "string"},
                "price": {"selector": "p.price_color", "type": "price"},
                "rating": {"selector": "p.star-rating", "attribute": "class", "type": "rating"},
                "detail_link": {"selector": "h3 a", "attribute": "href", "type": "url"},
            },
        }
        records = scraper.parse_html_records(SAMPLE_BOOKS_HTML, cfg)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["title"], "Test Book Title")
        self.assertEqual(records[0]["price"], "£25.50")
        self.assertEqual(records[0]["detail_link"], "https://books.toscrape.com/catalogue/book-1/index.html")

    @patch("scraper.requests.get")
    def test_fetch_page_content_success(self, mock_get):
        """Verify fetch_page_content sends proper User-Agent header and returns response."""
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_BOOKS_HTML
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        resp = scraper.fetch_page_content("https://books.toscrape.com/test", timeout=10)
        self.assertEqual(resp.status_code, 200)
        mock_get.assert_called_once()
        headers = mock_get.call_args[1]["headers"]
        self.assertIn("TheCloudScraper", headers["User-Agent"])

    @patch("scraper.requests.get")
    def test_lambda_handler_http_error(self, mock_get):
        """Verify graceful error reporting when HTTP request raises exception."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused by target")

        event = {"site_id": "books_toscrape"}
        result = scraper.lambda_handler(event)
        self.assertEqual(result["status"], "FAILURE")
        self.assertEqual(result["statusCode"], 502)
        self.assertTrue(result.get("is_retryable"))
        self.assertIn("Connection refused", result["error"])


if __name__ == "__main__":
    unittest.main()
