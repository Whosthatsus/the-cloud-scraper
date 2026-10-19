"""
End-to-end integration tests simulating the entire The Cloud Scraper pipeline.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Import all lambda modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))
import scraper
import validation
import transformation
import dynamodb_store
import notification

MOCK_HTML_QUOTES = """
<!DOCTYPE html>
<html>
<body>
  <div class="quote">
    <span class="text">“The only way to do great work is to love what you do.”</span>
    <span>by <small class="author">Steve Jobs</small>
    <a href="/author/Steve-Jobs">(about)</a></span>
    <div class="tags">
      <a class="tag" href="/tag/work/">work</a>
      <a class="tag" href="/tag/inspiration/">inspiration</a>
    </div>
  </div>
  <div class="quote">
    <span class="text">“The only way to do great work is to love what you do.”</span>
    <span>by <small class="author">Steve Jobs</small>
    <a href="/author/Steve-Jobs">(about)</a></span>
    <div class="tags">
      <a class="tag" href="/tag/work/">work</a>
    </div>
  </div>
</body>
</html>
"""


class TestPipelineIntegration(unittest.TestCase):

    @patch("scraper.requests.get")
    def test_full_pipeline_flow(self, mock_get):
        """
        Simulate the complete Step Functions state machine lifecycle:
        Scrape -> Validate -> Transform/Deduplicate -> Store -> Notify.
        """
        # 1. Mock website fetch
        mock_resp = MagicMock()
        mock_resp.text = MOCK_HTML_QUOTES
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        # Step 1: Scrape
        scrape_out = scraper.lambda_handler({"site_id": "quotes_toscrape"})
        self.assertEqual(scrape_out["status"], "SUCCESS")
        self.assertEqual(scrape_out["records_count"], 2)

        # Step 2: Validate
        val_out = validation.lambda_handler(scrape_out)
        self.assertEqual(val_out["Validation"], "SUCCESS")
        self.assertEqual(val_out["valid_count"], 2)

        # Step 3: Transform & Deduplicate
        trans_out = transformation.lambda_handler(val_out)
        self.assertEqual(trans_out["status"], "SUCCESS")
        self.assertEqual(trans_out["total_raw"], 2)
        # Identical quotes deduplicated into 1
        self.assertEqual(trans_out["total_transformed"], 1)
        self.assertEqual(trans_out["duplicates_removed"], 1)

        unique_quote = trans_out["records"][0]
        self.assertEqual(unique_quote["author"], "Steve Jobs")
        self.assertIn("work", unique_quote["tags"])
        self.assertTrue(unique_quote["record_id"].startswith("quotes_toscrape#"))

        # Step 4: Storage
        store_out = dynamodb_store.lambda_handler(trans_out)
        self.assertEqual(store_out["Storage"], "SUCCESS")
        self.assertEqual(store_out["records_count"], 1)

        # Step 5: Notification
        notify_out = notification.lambda_handler(store_out)
        self.assertEqual(notify_out["status"], "SUCCESS")
        self.assertIn("quotes_toscrape", notify_out["summary"])
        self.assertGreater(notify_out["cost_metrics"]["estimated_total_usd"], 0)


if __name__ == "__main__":
    unittest.main()
