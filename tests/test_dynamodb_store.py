"""
Unit tests for the DynamoDB & S3 Storage component (lambda/dynamodb_store.py).
"""

import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

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
        """Verify put_item is invoked with conditional expressions for deduplication."""
        mock_dynamo = MagicMock()
        mock_table = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_resource.return_value = mock_dynamo

        records = [
            {"record_id": "books#1", "site_id": "books", "price": 10.5},
            {"record_id": "books#2", "site_id": "books", "price": 20.0},
        ]
        new_count, existing_count, err = dynamodb_store.store_records_in_dynamodb("TestTable", records)
        self.assertEqual(new_count, 2)
        self.assertEqual(existing_count, 0)
        self.assertIsNone(err)
        self.assertEqual(mock_table.put_item.call_count, 2)

    @patch("dynamodb_store.boto3.resource")
    def test_store_records_conditional_check_failed(self, mock_resource):
        """Verify conditional check failure is handled as an existing duplicate item."""
        mock_dynamo = MagicMock()
        mock_table = MagicMock()
        # Simulate ConditionalCheckFailedException for an existing record
        mock_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": "The conditional request failed"}},
            "PutItem",
        )
        mock_dynamo.Table.return_value = mock_table
        mock_resource.return_value = mock_dynamo

        records = [{"record_id": "books#1", "site_id": "books", "price": 10.5}]
        new_count, existing_count, err = dynamodb_store.store_records_in_dynamodb("TestTable", records)
        self.assertEqual(new_count, 0)
        self.assertEqual(existing_count, 1)
        self.assertIsNone(err)

    @patch("dynamodb_store.boto3.client")
    def test_save_transformed_json_to_s3_mocked(self, mock_client):
        """Verify transformed records are archived to S3."""
        mock_s3 = MagicMock()
        mock_client.return_value = mock_s3

        records = [{"record_id": "books#1"}]
        metadata = {"site_id": "books_toscrape"}
        key, err = dynamodb_store.save_transformed_json_to_s3("my-bucket", "books_toscrape", "20261020", records, metadata)
        self.assertTrue(key.startswith("transform/books_toscrape/20261020/"))
        self.assertIsNone(err)
        self.assertEqual(mock_s3.put_object.call_count, 2)


if __name__ == "__main__":
    unittest.main()
