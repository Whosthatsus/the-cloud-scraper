"""
Unit tests for the Data Transformation and Deduplication component (lambda/transformation.py).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))
import transformation


class TestTransformation(unittest.TestCase):

    def test_clean_text_mojibake(self):
        """Verify cleaning of encoding artifacts and extra whitespace."""
        raw = "  Â£51.77   In   Stock  "
        cleaned = transformation.clean_text(raw)
        self.assertEqual(cleaned, "£51.77 In Stock")

    def test_parse_price(self):
        """Verify price extraction from various currency formats."""
        self.assertEqual(transformation.parse_price("£51.77"), 51.77)
        self.assertEqual(transformation.parse_price("$109.99"), 109.99)
        self.assertEqual(transformation.parse_price("EUR 45.00"), 45.00)
        self.assertEqual(transformation.parse_price(42.5), 42.5)
        self.assertEqual(transformation.parse_price("No Price"), 0.0)
        self.assertEqual(transformation.parse_price(None), 0.0)

    def test_parse_rating(self):
        """Verify rating string conversion to integers."""
        self.assertEqual(transformation.parse_rating("star-rating One"), 1)
        self.assertEqual(transformation.parse_rating("star-rating Two"), 2)
        self.assertEqual(transformation.parse_rating("Three"), 3)
        self.assertEqual(transformation.parse_rating("Rating: 4 of 5"), 4)
        self.assertEqual(transformation.parse_rating("Five"), 5)
        self.assertEqual(transformation.parse_rating(None), 0)

    def test_deterministic_content_hash(self):
        """Verify SHA-256 fingerprint is identical for identical records."""
        rec1 = {
            "title": "A Light in the Attic",
            "detail_link": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        }
        rec2 = {
            "title": "A Light in the Attic",
            "detail_link": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        }
        hash1 = transformation.generate_content_hash(rec1, "books_toscrape")
        hash2 = transformation.generate_content_hash(rec2, "books_toscrape")
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)  # Valid SHA-256 hex string

    def test_deduplication(self):
        """Verify duplicate records are filtered while preserving single unique instances."""
        batch = [
            {
                "title": "Duplicate Book",
                "price": "£10.00",
                "detail_link": "https://example.com/item1",
            },
            {
                "title": "Duplicate Book",
                "price": "£10.00",
                "detail_link": "https://example.com/item1",
            },
            {
                "title": "Unique Book",
                "price": "£20.00",
                "detail_link": "https://example.com/item2",
            },
        ]
        event = {
            "site_id": "test_site",
            "records": batch,
        }
        res = transformation.lambda_handler(event)
        self.assertEqual(res["total_raw"], 3)
        self.assertEqual(res["total_transformed"], 2)
        self.assertEqual(res["duplicates_removed"], 1)


if __name__ == "__main__":
    unittest.main()
