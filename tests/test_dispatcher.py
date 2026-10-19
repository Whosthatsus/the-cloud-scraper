"""
Unit tests for the Job Dispatcher component (lambda/start_step_function.py).
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))
import start_step_function


class TestJobDispatcher(unittest.TestCase):

    def test_parse_api_gateway_event(self):
        """Verify parsing of API Gateway HTTP POST /scrape event."""
        event = {
            "httpMethod": "POST",
            "path": "/scrape",
            "body": json.dumps({"site_id": "quotes_toscrape"}),
        }
        jobs = start_step_function.parse_incoming_event(event)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["site_id"], "quotes_toscrape")
        self.assertEqual(jobs[0]["triggered_by"], "api_gateway")

    def test_parse_sqs_event(self):
        """Verify parsing of Amazon SQS queue message event."""
        event = {
            "Records": [
                {
                    "eventSource": "aws:sqs",
                    "body": json.dumps({"site_id": "books_toscrape"}),
                }
            ]
        }
        jobs = start_step_function.parse_incoming_event(event)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["site_id"], "books_toscrape")
        self.assertEqual(jobs[0]["triggered_by"], "sqs_queue")

    def test_parse_eventbridge_event(self):
        """Verify parsing of EventBridge scheduled event."""
        event = {"source": "aws.events", "site_id": "books_toscrape"}
        jobs = start_step_function.parse_incoming_event(event)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["site_id"], "books_toscrape")
        self.assertEqual(jobs[0]["triggered_by"], "eventbridge")

    @patch("start_step_function.boto3.client")
    def test_enqueue_job_to_sqs_mocked(self, mock_client):
        """Verify SQS send_message call when enqueuing jobs."""
        mock_sqs = MagicMock()
        mock_sqs.send_message.return_value = {"MessageId": "msg-12345"}
        mock_client.return_value = mock_sqs

        res = start_step_function.enqueue_job_to_sqs(
            "https://sqs.us-east-1.amazonaws.com/123/queue",
            {"site_id": "books_toscrape"},
        )
        self.assertEqual(res["status"], "ENQUEUED")
        self.assertEqual(res["messageId"], "msg-12345")
        mock_sqs.send_message.assert_called_once()

    @patch("start_step_function.boto3.client")
    def test_start_state_machine_execution_mocked(self, mock_client):
        """Verify Step Functions start_execution invocation."""
        mock_sfn = MagicMock()
        mock_sfn.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123:execution:sm:test-1",
            "startDate": "2026-10-20T00:00:00Z",
        }
        mock_client.return_value = mock_sfn

        res = start_step_function.start_state_machine_execution(
            "arn:aws:states:us-east-1:123:stateMachine:sm",
            {"site_id": "books_toscrape"},
        )
        self.assertEqual(res["status"], "RUNNING")
        self.assertTrue(res["executionArn"].startswith("arn:aws:states:"))


if __name__ == "__main__":
    unittest.main()
