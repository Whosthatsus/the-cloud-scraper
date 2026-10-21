"""
Unit tests for security URL validation, new scraping sources, CSV export, and execution history.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import scraper
import server
import pipeline_runner


class TestSecurityAndSources(unittest.TestCase):

    def test_ssrf_blocks_localhost(self):
        """Verify that localhost and loopback addresses are blocked by SSRF validation."""
        is_safe, err = scraper.validate_target_url_security("http://localhost:8080/secret")
        self.assertFalse(is_safe)
        self.assertIn("blocked", err.lower())

    def test_ssrf_blocks_private_ip(self):
        """Verify that private RFC 1918 addresses are blocked."""
        is_safe, err = scraper.validate_target_url_security("http://127.0.0.1/admin")
        self.assertFalse(is_safe)
        self.assertIn("forbidden", err.lower())

        is_safe, err = scraper.validate_target_url_security("http://192.168.1.1/router")
        self.assertFalse(is_safe)

    def test_ssrf_blocks_aws_metadata_service(self):
        """Verify that AWS IMDS IP (169.254.169.254) is strictly blocked."""
        is_safe, err = scraper.validate_target_url_security("http://169.254.169.254/latest/meta-data/")
        self.assertFalse(is_safe)
        self.assertIn("forbidden", err.lower())

    def test_ssrf_blocks_unsupported_schemes(self):
        """Verify that file:// and ftp:// schemes are rejected."""
        is_safe, err = scraper.validate_target_url_security("file:///etc/passwd")
        self.assertFalse(is_safe)
        self.assertIn("scheme", err.lower())

        is_safe, err = scraper.validate_target_url_security("ftp://example.com/file")
        self.assertFalse(is_safe)

    def test_ssrf_blocks_dangerous_ports(self):
        """Verify that non-standard ports (like database 5432) are rejected."""
        is_safe, err = scraper.validate_target_url_security("http://books.toscrape.com:5432/")
        self.assertFalse(is_safe)
        self.assertIn("port", err.lower())

    def test_valid_public_urls_permitted(self):
        """Verify that valid public HTTPS web URLs pass security check."""
        is_safe, err = scraper.validate_target_url_security("https://books.toscrape.com/catalogue/page-1.html")
        self.assertTrue(is_safe)
        self.assertEqual(err, "")

        is_safe, err = scraper.validate_target_url_security("https://webscraper.io/test-sites/e-commerce/allinone")
        self.assertTrue(is_safe)

    def test_load_new_site_configs(self):
        """Verify that webscraper_laptops and hacker_news configs load properly."""
        cfg_laptops = scraper.load_site_config("webscraper_laptops")
        self.assertEqual(cfg_laptops["site_id"], "webscraper_laptops")
        self.assertEqual(cfg_laptops["container_selector"], "div.product-wrapper")

        cfg_hn = scraper.load_site_config("hacker_news")
        self.assertEqual(cfg_hn["site_id"], "hacker_news")
        self.assertEqual(cfg_hn["container_selector"], "tr.athing")

    def test_csv_export_conversion(self):
        """Verify that record dictionaries convert to properly escaped RFC 4180 CSV."""
        sample_records = [
            {
                "title": 'Book with, comma and "quotes"',
                "price": 29.99,
                "rating": 5,
                "tags": ["sci-fi", "space"],
            },
            {
                "title": "Simple Title",
                "price": 10.0,
                "rating": 4,
                "tags": [],
            },
        ]
        csv_output = server.convert_records_to_csv(sample_records)
        self.assertIn("title,price,rating,tags", csv_output)
        self.assertIn('"Book with, comma and ""quotes"""', csv_output)
        self.assertIn("sci-fi; space", csv_output)
        self.assertIn("Simple Title", csv_output)

    def test_execution_history_recording(self):
        """Verify recording and retrieval of execution history entries."""
        entry = {
            "execution_id": "test-exec-12345",
            "timestamp": "2026-10-22T01:00:00Z",
            "site_id": "books_toscrape",
            "status": "SUCCESS",
            "duration": 1.25,
            "scraped": 20,
            "valid": 20,
            "duplicates_removed": 0,
            "transformed": 20,
            "cost_usd": 0.000085,
        }
        pipeline_runner.record_execution_history(entry)
        history = pipeline_runner.get_execution_history()
        self.assertTrue(len(history) > 0)
        self.assertEqual(history[0]["execution_id"], "test-exec-12345")


if __name__ == "__main__":
    unittest.main()
