"""
Unit tests for the Notification & FinOps Telemetry component (lambda/notification.py).
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))
import notification


class TestNotification(unittest.TestCase):

    def test_calculate_estimated_cost(self):
        """Verify FinOps cost calculation logic across Lambda, S3, DynamoDB, and Step Functions."""
        cost = notification.calculate_estimated_cost(
            duration_seconds=2.0,
            records_stored=20,
            memory_mb=512,
            state_transitions=5,
        )
        self.assertIn("estimated_total_usd", cost)
        self.assertIn("lambda_compute_usd", cost)
        self.assertIn("dynamodb_writes_usd", cost)
        self.assertIn("s3_storage_ops_usd", cost)
        self.assertIn("step_functions_usd", cost)
        self.assertGreater(cost["estimated_total_usd"], 0)
        self.assertLess(cost["estimated_total_usd"], 0.01)  # Micro-dollars per run

    def test_format_notification_body_success(self):
        """Verify email notification message structure for successful runs."""
        event = {
            "status": "SUCCESS",
            "site_id": "books_toscrape",
            "records_count": 20,
            "records_stored_dynamodb": 19,
            "duplicates_removed": 1,
        }
        cost = notification.calculate_estimated_cost(2.0, 20)
        body = notification.format_notification_body(event, cost)
        self.assertIn("The Cloud Scraper", body)
        self.assertIn("[SUCCESS]", body)
        self.assertIn("Raw Records Extracted: 20", body)
        self.assertIn("FinOps Cost Estimation", body)

    def test_format_notification_body_failure(self):
        """Verify email notification message structure for failure runs."""
        event = {
            "status": "FAILURE",
            "site_id": "books_toscrape",
            "error": "HTTP 502 Bad Gateway",
        }
        cost = notification.calculate_estimated_cost(0.5, 0)
        body = notification.format_notification_body(event, cost)
        self.assertIn("[FAILURE]", body)
        self.assertIn("Dead-Letter Queue (DLQ)", body)
        self.assertIn("HTTP 502 Bad Gateway", body)

    @patch("notification.boto3.client")
    def test_publish_to_sns_mocked(self, mock_client):
        """Verify SNS publish invocation when SNS topic ARN is provided."""
        mock_sns = MagicMock()
        mock_sns.publish.return_value = {"MessageId": "sns-msg-999"}
        mock_client.return_value = mock_sns

        with patch.dict(os.environ, {"SNS_TOPIC_ARN": "arn:aws:sns:us-east-1:123:alerts"}):
            event = {"status": "SUCCESS", "site_id": "books_toscrape"}
            res = notification.lambda_handler(event)
            self.assertEqual(res["Notification"], "SUCCESS")
            self.assertTrue(res["sns_result"]["published"])
            mock_sns.publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()
