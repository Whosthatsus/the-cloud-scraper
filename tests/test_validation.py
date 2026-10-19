"""
Unit tests for the Data Validation component (lambda/validation.py).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))
import validation


class TestValidation(unittest.TestCase):

    def setUp(self):
        self.rules = {
            "required_fields": ["title", "price", "detail_link"],
            "min_title_length": 3,
        }

    def test_valid_record(self):
        """Verify that a compliant record passes validation with no errors."""
        rec = {
            "title": "Clean Architecture",
            "price": "£34.99",
            "detail_link": "https://books.toscrape.com/catalogue/clean-arch/index.html",
        }
        is_valid, errors = validation.validate_single_record(rec, self.rules)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_missing_required_field(self):
        """Verify that a record missing a required field fails validation."""
        rec = {
            "title": "Some Book",
            "price": "£10.00",
            # detail_link is missing
        }
        is_valid, errors = validation.validate_single_record(rec, self.rules)
        self.assertFalse(is_valid)
        self.assertTrue(any("detail_link" in err for err in errors))

    def test_invalid_url(self):
        """Verify that a record with an invalid URL is rejected."""
        rec = {
            "title": "Some Book",
            "price": "£10.00",
            "detail_link": "javascript:alert(1)",
        }
        is_valid, errors = validation.validate_single_record(rec, self.rules)
        self.assertFalse(is_valid)
        self.assertTrue(any("Invalid URL" in err for err in errors))

    def test_filter_and_validate_partitioning(self):
        """Verify segregation of records into valid and invalid sets."""
        records = [
            {"title": "Valid Book", "price": "£15.00", "detail_link": "https://example.com/1"},
            {"title": "X", "price": "£15.00", "detail_link": "https://example.com/2"},  # Title too short
            {"title": "Missing Price", "detail_link": "https://example.com/3"},  # Missing price
        ]
        valid, invalid = validation.filter_and_validate_records(records, self.rules)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(invalid), 2)
        self.assertEqual(valid[0]["title"], "Valid Book")

    def test_lambda_handler_all_invalid_fails(self):
        """Verify that if all records are invalid, pipeline marks Validation as FAILURE."""
        event = {
            "site_id": "books_toscrape",
            "records": [
                {"title": "", "price": "invalid", "detail_link": "not-url"}
            ],
            "validation_rules": self.rules,
        }
        res = validation.lambda_handler(event)
        self.assertEqual(res["Validation"], "FAILURE")
        self.assertEqual(res["valid_count"], 0)


if __name__ == "__main__":
    unittest.main()
