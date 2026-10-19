"""
Unit tests for the DynamoDB & S3 Storage component (lambda/dynamodb_store.py).
"""

import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))
import dynamodb_store


class TestDynamoDBStore(unittest.TestCase):

    def test_float_to_decimal_conversion(self):
        """Verify floats are converted to Decimals for DynamoDB compatibility."""
        data = {
            "title": "Sample",
            "price": 45.99,
            "nested": {"rating": 4.5, "tags": [1.1, 2.2]},
        }
        converted = dynamodb_store.convert_floats_to_decimals(data)
        self.assertIsInstance(converted["price"], Decimal)
        self.assertIsInstance(converted["nested"]["rating"], Decimal)
        self.assertEqual(converted["price"], Decimal("45.99"))

    def test_decimal_to_float_conversion(self):
        """Verify Decimals are converted back to floats for JSON serialization."""
        data = {
            "price": Decimal("45.99"),
            "nested": [Decimal("1.5")],
        }
        converted = dynamodb_store.convert_decimals_to_floats(data)
        self.assertIsInstance(converted["price"], float)
        self.assertEqual(converted["price"], 45.99)

    @patch("dynamodb_store.boto3.resource")
    def test_store_records_in_dynamodb_mocked(self, mock_resource):
        """Verify batch_writer is invoked properly for storing items."""
        mock_dynamo = MagicMock()
        mock_table = MagicMock()
        mock_batch = MagicMock()
        mock_table.batch_writer.return_value.__enter__.return_value = mock_batch
        mock_dynamo.Table.return_value = mock_table
        mock_resource.return_value = mock_dynamo

        records = [
            {"record_id": "books#1", "site_id": "books", "price": 10.5},
            {"record_id": "books#2", "site_id": "books", "price": 20.0},
        ]
        count = dynamodb_store.store_records_in_dynamodb("TestTable", records)
        self.assertEqual(count, 2)
        self.assertEqual(mock_batch.put_item.call_count, 2)

    @patch("dynamodb_store.boto3.client")
    def test_save_transformed_json_to_s3_mocked(self, mock_client):
        """Verify transformed records are archived to S3."""
        mock_s3 = MagicMock()
        mock_client.return_value = mock_s3

        records = [{"record_id": "books#1"}]
        metadata = {"site_id": "books_toscrape"}
        key = dynamodb_store.save_transformed_json_to_s3("my-bucket", "books_toscrape", "20261020", records, metadata)
        self.assertTrue(key.startswith("transform/books_toscrape/20261020/"))
        self.assertEqual(mock_s3.put_object.call_count, 2)


if __name__ == "__main__":
    unittest.main()
