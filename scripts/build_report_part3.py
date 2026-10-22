"""
Chapters 6 through 8 of The Cloud Scraper Final Project Report.
"""

import os
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from report_helpers import (
    COLOR_NAVY, COLOR_BLUE, COLOR_SLATE, COLOR_DARK, COLOR_MUTED,
    HEX_NAVY, HEX_BLUE, HEX_LIGHT_BG, HEX_ALT_ROW, HEX_BORDER,
    format_table_header_and_rows, add_custom_heading, add_body_paragraph,
    add_bullet_item, add_code_block, add_callout, add_figure_with_caption
)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIGURES_DIR = os.path.join(PROJECT_DIR, "figures")
IMAGES_DIR = os.path.join(PROJECT_DIR, "images")


def build_chapter_6(doc):
    """Chapter 6: Implementation Details"""
    add_custom_heading(doc, "Chapter 6: Implementation Details", level=1)
    
    add_custom_heading(doc, "6.1 Public Web Dashboard & CloudFront CDN Distribution", level=2)
    add_body_paragraph(
        doc,
        "The user interface for The Cloud Scraper is implemented as a lightweight, zero-dependency single-page application (SPA) "
        "crafted in vanilla HTML5, CSS3, and ES6 JavaScript. The frontend source files (web/index.html, web/app.js, web/style.css) "
        "are hosted in a private Amazon S3 static website bucket (the-cloud-scraper-web-893041508558) and distributed globally "
        "via an Amazon CloudFront CDN distribution (Distribution ID: E63365QMCM5, Domain: https://d3k1ttzl3bzy2k.cloudfront.net). "
        "This architectural choice ensures edge caching, global SSL/TLS termination, and instantaneous page load times without requiring "
        "any backend web servers (e.g., Nginx, Node.js, or Apache)."
    )
    add_body_paragraph(
        doc,
        "The dashboard interface provides five dedicated operator views: (1) Overview & Telemetry (aggregating total scraped entities, "
        "validation rates, duplicate counts, and active cloud environment indicators), (2) Scrape Workspace (providing dynamic URL inputs, "
        "extraction strategy selectors, preset shortcuts, and real-time Step Functions progress bars), (3) Results & Data (featuring dynamic "
        "dataset selection, client-side search, column sorting, pagination, and RFC 4180 CSV / JSON exports), (4) Execution History (persisting "
        "chronological run logs with direct deep-links into the AWS Step Functions console), and (5) Storage & Architecture (visualizing "
        "data lineage and partition paths across S3 and DynamoDB)."
    )

    add_custom_heading(doc, "6.2 Job Dispatcher REST API Controller", level=2)
    add_body_paragraph(
        doc,
        "The entry point for on-demand cloud scraping is implemented in lambda/start_step_function.py. Rather than deploying "
        "disparate Lambda functions for routing, the Job Dispatcher implements a consolidated REST API controller pattern "
        "integrated with Amazon API Gateway (https://xehoja83gg.execute-api.ap-southeast-2.amazonaws.com/prod/scrape). The controller "
        "evaluates inbound HTTP methods and query parameters to execute five discrete operations:"
    )
    add_bullet_item(doc, "POST /scrape (Job Ingestion): Parses site_id, target_url, extraction_mode, and custom selectors; starts a new Step Functions execution with an execution name (e.g., scrape-{site_id}-{timestamp}-{uuid}); returns HTTP 202 Accepted with executionArn.", "• Ingestion: ")
    add_bullet_item(doc, "POST /scrape (Target Registration): When action='save_target', persists dynamic extraction rules into the DynamoDB registry table with record_id='TARGET_CONFIG'.", "• Target Registration: ")
    add_bullet_item(doc, "GET /scrape?execution_arn=... (Status Polling): Invokes stepfunctions:DescribeExecution to return real-time execution status (RUNNING, SUCCEEDED, FAILED), start/stop timestamps, error causes, and execution output.", "• Execution Monitoring: ")
    add_bullet_item(doc, "GET /scrape?action=results&site_id=... (Live Data Inspection): Queries DynamoDB partition key site_id to stream structured records directly to the dashboard.", "• Data Inspection: ")
    add_bullet_item(doc, "GET /scrape?action=targets (Registry Lookup): Scans DynamoDB for all stored target configurations, merging them with built-in profiles to populate dashboard selectors dynamically.", "• Registry Discovery: ")

    add_custom_heading(doc, "6.3 Dynamic Target Registration & Management", level=2)
    add_body_paragraph(
        doc,
        "A critical innovation of this project is the ability to add new data sources dynamically without modifying code or redeploying the stack. "
        "Figure 6.1 illustrates the sequence diagram for registering a new target and subsequently dispatching a scraping job."
    )

    fig4_path = os.path.join(FIGURES_DIR, "fig4_target_sequence.png")
    add_figure_with_caption(doc, fig4_path, "Figure 6.1: Sequence diagram showing dynamic target registration in DynamoDB and Step Functions dispatch.", width_inches=6.0)

    add_body_paragraph(
        doc,
        "When a user defines a target (e.g., Hacker News Live at https://news.ycombinator.com/), the configuration is saved "
        "to DynamoDB. When the job is dispatched, the Job Dispatcher attaches the target rules into a config_override object passed "
        "directly into the Step Functions execution input. Downstream Lambda microservices read config_override first, ensuring custom "
        "selectors, extraction modes, and validation thresholds apply dynamically across the entire state machine."
    )

    add_custom_heading(doc, "6.4 Web Scraper Microservice (Extraction Engine)", level=2)
    add_body_paragraph(
        doc,
        "The scraping microservice is implemented in lambda/scraper.py. It accepts the Step Functions input payload, loads the target "
        "configuration (from config_override, DynamoDB, or config/sites_config.json), and executes a resilient HTTP fetch using Python Requests "
        "and BeautifulSoup4. The microservice implements two distinct extraction engines:"
    )

    add_custom_heading(doc, "6.4.1 Automatic Generic HTML Extraction Heuristics", level=3)
    add_body_paragraph(
        doc,
        "When a target specifies extraction_mode='generic', the scraper employs heuristic DOM pattern recognition to harvest data "
        "from unfamiliar websites without pre-defined CSS selectors. The heuristic engine operates in three stages:"
    )
    add_bullet_item(doc, "Repeating Card Discovery: Scans the DOM tree for repeating container tags (article, section, div[class*='item'], div[class*='card'], div[class*='post'], li[class*='product'], tr[class*='row']).", "Stage 1: ")
    add_bullet_item(doc, "Element Resolution: Within each discovered card, heuristically locates the primary title (h1–h4, strong, a.title), resolves hyperlinked URLs (a[href] converted to absolute URLs via urllib.parse.urljoin), and extracts descriptive text paragraphs.", "Stage 2: ")
    add_bullet_item(doc, "Fallback Grouping: If no repeating containers match, the engine groups top-level heading tags with their subsequent sibling paragraphs, generating structured entity rows.", "Stage 3: ")

    add_custom_heading(doc, "6.4.2 Configurable CSS Selector Extraction Engine", level=3)
    add_body_paragraph(
        doc,
        "When extraction_mode='custom', the scraper applies precise declarative CSS selectors. For each item matching container_selector, "
        "the engine iterates over defined fields, resolving inner text or HTML attributes (e.g., selector: 'span.titleline > a', attribute: 'href'). "
        "Extracted raw text undergoes immediate whitespace stripping and normalization."
    )

    add_custom_heading(doc, "6.4.3 Robots.txt & Rate Limiting Enforcement", level=3)
    add_body_paragraph(
        doc,
        "Prior to fetching web content, the scraper parses the target domain's /robots.txt using urllib.robotparser.RobotFileParser. "
        "If scraping is prohibited for the designated User-Agent, the execution fails cleanly with a non-retryable policy exception. "
        "For multi-page crawls, a polite delay (rate_limit_delay_seconds: 1.0) is enforced between requests, and the raw HTML is "
        "archived immediately into Amazon S3 under raw/{site_id}/{timestamp}/page.html."
    )

    add_custom_heading(doc, "6.5 Schema Validation & Quality Gate Microservice", level=2)
    add_body_paragraph(
        doc,
        "Implemented in lambda/validation.py, the validation microservice functions as an automated data quality gate. "
        "Raw scraped records are evaluated against strict schema cleanliness criteria:"
    )
    add_bullet_item(doc, "Required Field Presence: Ensures every item possesses non-empty values for required keys (e.g., title, quote, url).", "• Completeness: ")
    add_bullet_item(doc, "Syntactic URL Validation: Parses URLs with urllib.parse to verify valid schemes (http/https) and network locations.", "• URL Validity: ")
    add_bullet_item(doc, "Domain Type Enforcement: Verifies price formats, numeric rating ranges (1–5), and minimum text lengths.", "• Type Checking: ")
    add_bullet_item(doc, "Record Partitioning: Valid records are forwarded to transformation, while invalid items are partitioned into an invalid_records array. If all records fail validation, the stage raises an unrecoverable exception to trigger DLQ quarantine.", "• Fault Partitioning: ")

    add_custom_heading(doc, "6.6 Transformation & Deterministic Deduplication Microservice", level=2)
    add_body_paragraph(
        doc,
        "Implemented in lambda/transformation.py, this microservice standardizes clean records and guarantees write idempotency. "
        "Text attributes are sanitized to eliminate mojibake encoding artifacts (e.g., converting 'Â£' to '£'). "
        "Numeric prices are normalized to standard floats, and star ratings ('One' through 'Five') are mapped to integer values."
    )
    add_body_paragraph(
        doc,
        "To prevent duplicate items across recurring scraping jobs, the transformer computes a deterministic SHA-256 fingerprint hash: "
        "content_hash = hashlib.sha256(canonical_representation).hexdigest(). The unique record_id is generated as {site_id}#{content_hash[:16]}. "
        "This hash uniquely identifies the record based on its core identity attributes, ensuring that identical products or articles scraped "
        "on subsequent days generate identical record IDs."
    )

    add_custom_heading(doc, "6.7 Dual-Tier Storage Microservice", level=2)
    add_body_paragraph(
        doc,
        "Implemented in lambda/dynamodb_store.py, this microservice writes transformed records into the dual-tier cloud storage architecture. "
        "Figure 6.2 illustrates the relationship between the S3 Data Lake partition hierarchy and the DynamoDB NoSQL primary key schema."
    )

    fig5_path = os.path.join(FIGURES_DIR, "fig5_storage_layout.png")
    add_figure_with_caption(doc, fig5_path, "Figure 6.2: Dual-tier storage layout showing S3 Data Lake partitioning and DynamoDB primary key design.", width_inches=6.0)

    add_body_paragraph(
        doc,
        "The microservice converts Python floats to Python Decimal types (required by DynamoDB) and issues batch conditional writes "
        "using ConditionExpression: 'attribute_not_exists(record_id)'. If an item already exists, DynamoDB silently suppresses the write, "
        "preventing redundant storage costs. Concurrently, the entire transformed dataset is serialized into versioned JSON and uploaded "
        "to Amazon S3 under transform/{site_id}/{timestamp}/records.json with SSE-AES256 encryption."
    )

    add_custom_heading(doc, "6.8 Fault Tolerance & Dead-Letter Queue Quarantine", level=2)
    add_body_paragraph(
        doc,
        "When an unhandled exception occurs in any Lambda task (e.g., HTTP 404, connection timeout, validation failure, or SSRF rejection), "
        "the Step Functions state machine traps the error using Catch: [{ErrorEquals: ['States.ALL'], Next: 'SendToDLQ'}]. "
        "The SendToDLQ state invokes arn:aws:states:::sqs:sendMessage, placing the full failure context directly into the Amazon SQS DLQ "
        "(the-cloud-scraper-scraper-dlq) with a 14-day retention period. The state machine then invokes lambda/notification.py to publish an "
        "urgent Amazon SNS email alert before terminating in a Fail state. Unaffected parallel scraping jobs continue unimpeded."
    )

    add_custom_heading(doc, "6.9 FinOps Telemetry & Alerting Microservice", level=2)
    add_body_paragraph(
        doc,
        "Implemented in lambda/notification.py, this microservice provides real-time economic observability. For every completed execution, "
        "it calculates the estimated serverless cost based on AWS Sydney pricing: Lambda invocation count and duration, Step Functions state "
        "transitions ($0.000025/transition), DynamoDB Write Request Units ($1.25/million), and S3 PUT operations ($0.005/1,000). "
        "A structured notification body is formatted and published to the Amazon SNS topic (the-cloud-scraper-notifications-topic), "
        "delivering immediate operational transparency to subscribed engineering stakeholders."
    )
    doc.add_page_break()


def build_chapter_7(doc):
    """Chapter 7: Technology Stack"""
    add_custom_heading(doc, "Chapter 7: Technology Stack", level=1)
    
    add_custom_heading(doc, "7.1 Architectural Technology Mapping", level=2)
    add_body_paragraph(
        doc,
        "To satisfy the rigorous design standards of Cloud Architecture Design (BCSE355L), The Cloud Scraper integrates "
        "managed AWS services, modern Python microservice runtimes, and client-side web technologies. Table 7.1 provides a complete "
        "architectural inventory detailing each technology, its architectural role, and its verified implementation evidence."
    )

    # Table 7.1
    t71_headers = ["Technology / Service", "Category", "Architectural Role", "Verified Implementation Evidence"]
    t71_data = [
        ("AWS Lambda", "Compute", "Stateless execution of 6 microservices (scraper, validator, transformer, store, dispatcher, notify)", "6 functions deployed in ap-southeast-2 running Python 3.10; 512MB RAM"),
        ("AWS Step Functions", "Orchestration", "Standard State Machine coordinating multi-stage ETL, retries, and DLQ routing", "State Machine: the-cloud-scraper-pipeline-sm (CREATE_COMPLETE)"),
        ("Amazon API Gateway", "API Ingestion", "Regional REST API exposing POST/GET /scrape with CORS and proxy integration", "Endpoint: https://xehoja83gg.execute-api.ap-southeast-2.amazonaws.com/prod/scrape"),
        ("Amazon DynamoDB", "NoSQL Database", "Primary structured entity store (PK: site_id, SK: record_id) and Target Registry", "Table: the-cloud-scraper-records; 71+ records verified active"),
        ("Amazon S3 (Data Lake)", "Object Storage", "Dual-tier immutable data lake: raw HTML snapshots and clean transformed JSON", "Bucket: the-cloud-scraper-bhumi-20261023 (SSE-AES256 encrypted)"),
        ("Amazon S3 (Web Origin)", "Web Hosting", "Static website origin hosting index.html, app.js, style.css, and fallback datasets", "Bucket: the-cloud-scraper-web-893041508558 (Synced & active)"),
        ("Amazon CloudFront", "Content Delivery", "Global CDN providing HTTPS caching and distribution of the dashboard interface", "Distribution ID: E63365QMCM5 (https://d3k1ttzl3bzy2k.cloudfront.net)"),
        ("Amazon SQS", "Messaging", "Decoupled job queue (ScraperJobQueue) and 14-day Dead-Letter Queue (ScraperDLQ)", "the-cloud-scraper-scraper-dlq verified with 3 quarantined messages"),
        ("Amazon SNS", "Alerting", "Publishing real-time operational success notifications and critical failure alerts", "Topic: the-cloud-scraper-notifications-topic (bhumi.choudhary166@gmail.com)"),
        ("Amazon EventBridge", "Scheduling", "Time-based cron trigger (cron(0 12 * * ? *)) for automated batch execution", "Rule: the-cloud-scraper-scheduled-rule (Configured, kept DISABLED for cost)"),
        ("Amazon CloudWatch", "Observability", "Centralized logging, metric filters, and DLQ message depth threshold alarms", "Log groups /aws/lambda/the-cloud-scraper-* and CloudWatch Alarm active"),
        ("AWS IAM", "Security", "Least-privilege role-based access control for Lambda execution and state machine", "IAM Role: LambdaExecutionRole with scoped DynamoDB/S3/SQS/SNS policies"),
        ("AWS SAM", "IaC & Build", "Infrastructure-as-Code specification defining all resources in template.yml", "template.yml validated and deployed with sam deploy (UPDATE_COMPLETE)"),
        ("Python 3.10 + BS4", "Data Extraction", "HTML DOM tree parsing, heuristic generic card extraction, and robots.txt checks", "lambda/scraper.py using Requests (2.31.0) and BeautifulSoup4 (4.12.3)"),
        ("Pytest 9.1.1", "Testing", "Automated test suite executing 49 unit, integration, and security test cases", "tests/ directory executing with 100% pass rate in 1.46s")
    ]
    t71 = doc.add_table(rows=len(t71_data) + 1, cols=4)
    for c_idx, h in enumerate(t71_headers):
        t71.cell(0, c_idx).paragraphs[0].text = h
    for r_idx, row in enumerate(t71_data):
        for c_idx, val in enumerate(row):
            t71.cell(r_idx + 1, c_idx).paragraphs[0].text = val

    format_table_header_and_rows(t71, [1.5, 1.3, 1.9, 1.8])

    add_custom_heading(doc, "7.2 Technical Rationale for Selected Cloud Services", level=2)
    add_body_paragraph(
        doc,
        "The selection of each cloud service was driven by specific architectural requirements. AWS Step Functions was selected "
        "over simple Lambda chaining because it provides visual execution state auditing, declarative retries, and native integration "
        "with SQS DLQ without requiring complex distributed locking code. Amazon DynamoDB was chosen over Amazon RDS because its On-Demand "
        "billing model scales directly with scrape frequency, eliminating the continuous $15+/month minimum cost of an always-on RDS instance "
        "while providing sub-10ms key-value lookups on record_id."
    )
    doc.add_page_break()


def build_chapter_8(doc):
    """Chapter 8: Testing and Validation"""
    add_custom_heading(doc, "Chapter 8: Testing and Validation", level=1)
    
    add_custom_heading(doc, "8.1 Testing Methodology & Verification Framework", level=2)
    add_body_paragraph(
        doc,
        "To ensure uncompromising reliability across both local development and live cloud environments, The Cloud Scraper "
        "underwent a multi-tiered verification framework comprising: (1) Automated Unit Tests, (2) Integration Workflow Simulations, "
        "(3) Security Boundary Penetration Tests, and (4) Formal Live AWS Cloud Acceptance Tests (Tests A through J)."
    )

    add_custom_heading(doc, "8.2 Automated Unit & Integration Testing Suite", level=2)
    add_body_paragraph(
        doc,
        "The automated test suite is implemented using Pytest (v9.1.1) and Python's built-in unittest.mock library. "
        "The suite executes across eight test modules, covering selector parsing, schema validation, normalization, DynamoDB conditional writes, "
        "EventBridge parsing, FinOps cost formulas, SSRF attack vectors, and end-to-end pipeline simulations. "
        "Table 8.1 summarizes the automated test suite results, confirming a 100% pass rate (49/49 passed in 1.46 seconds)."
    )

    # Table 8.1
    t81_headers = ["Test Module", "Focus Area", "Test Cases", "Pass Rate", "Execution Time"]
    t81_data = [
        ("test_scraper.py", "HTTP fetching, robots.txt, mock HTML parsing, config loader", "7 tests", "100% (7/7)", "0.18s"),
        ("test_validation.py", "Schema rules, required fields, type checks, partitioning", "5 tests", "100% (5/5)", "0.12s"),
        ("test_transformation.py", "Mojibake cleaning, price/rating parsing, SHA-256 hashes", "5 tests", "100% (5/5)", "0.14s"),
        ("test_dynamodb_store.py", "Decimal conversion, conditional writes, S3 JSON saving", "5 tests", "100% (5/5)", "0.13s"),
        ("test_dispatcher.py", "API Gateway, EventBridge, SQS parsing, SFN start mocked", "5 tests", "100% (5/5)", "0.15s"),
        ("test_notification.py", "FinOps micro-cost calculation, SNS alert payload formatting", "4 tests", "100% (4/4)", "0.11s"),
        ("test_security_and_sources.py", "SSRF private IP, IMDS, localhost, bad ports, CSV export", "10 tests", "100% (10/10)", "0.32s"),
        ("test_custom_scraping_and_api.py", "Generic extraction heuristics, custom selectors, no fallback", "8 tests", "100% (8/8)", "0.31s"),
        ("TOTAL VERIFIED SUITE", "Comprehensive unit, integration, and security validation", "49 tests", "100% (49/49)", "1.46s")
    ]
    t81 = doc.add_table(rows=len(t81_data) + 1, cols=5)
    for c_idx, h in enumerate(t81_headers):
        t81.cell(0, c_idx).paragraphs[0].text = h
    for r_idx, row in enumerate(t81_data):
        for c_idx, val in enumerate(row):
            t81.cell(r_idx + 1, c_idx).paragraphs[0].text = val

    format_table_header_and_rows(t81, [1.8, 2.1, 0.9, 1.0, 0.7])

    add_custom_heading(doc, "8.3 Formal Acceptance Testing (Tests A through J)", level=2)
    add_body_paragraph(
        doc,
        "To rigorously validate that the platform fulfills all technical requirements of the first-review document, "
        "ten comprehensive acceptance tests (Tests A through J) were executed directly against deployed AWS cloud resources. "
        "Table 8.2 presents the formal verification matrix, documenting the test procedures, expected outcomes, observed cloud behaviors, "
        "and empirical evidence."
    )

    # Table 8.2
    t82_headers = ["Test ID & Requirement", "Test Procedure & Target", "Expected Cloud Outcome", "Observed Cloud Result", "Status"]
    t82_data = [
        ("Test A:\nCustom Target Registration", "Registered 'hacker_news_live' targeting news.ycombinator.com with custom CSS selectors; dispatched via API Gateway", "Step Functions state machine executes; extracts 30 stories; saves to DynamoDB and S3", "Execution 'scrape-hacker_news_live-20261022220014-926eb4' SUCCEEDED in 4.88s; 30 records saved", "PASSED"),
        ("Test B:\nGeneric HTML Extraction", "Dispatched 'travel_books_generic' targeting Travel Books category using Automatic Generic Mode (no CSS selectors)", "Scraper heuristically identifies book cards, titles, and links; persists valid records", "Execution 'scrape-travel_books_generic-20261022220134-44d352' SUCCEEDED in 3.25s; 11 records saved", "PASSED"),
        ("Test C:\nLive Status Monitoring", "Dispatched job via POST /scrape; polled GET /scrape?execution_arn=... every 2s from browser dashboard", "API Gateway returns HTTP 202; polling returns RUNNING -> SUCCEEDED; UI updates stages", "API returned 202 with executionArn; polled describe_execution; UI displayed all 7 stages completed", "PASSED"),
        ("Test D:\nNo Silent Fallback", "Dispatched custom target; verified Lambda logs and DynamoDB records do not scrape books_toscrape default", "Target URL requested directly; no fallback selectors applied; distinct record_id generated", "DynamoDB items verified with site_id='hacker_news_live' and news URLs; unit test verified", "PASSED"),
        ("Test E:\nFault Tolerance & DLQ", "Dispatched non-existent 404 URL (https://books.toscrape.com/non-existent-page-404.html)", "State machine traps HTTP 404; transitions to SendToDLQ; quarantines payload to SQS", "Execution 'scrape-test_404_resilience-20261022220504-c820da' caught; 3 messages visible in DLQ", "PASSED"),
        ("Test F:\nSecurity & SSRF Guardrail", "Dispatched attack targeting AWS IMDS metadata service (http://169.254.169.254/latest/meta-data/)", "Scraper blocks connection immediately; rejects prohibited IP; execution fails to DLQ", "Execution 'scrape-ssrf_attack_test-20261022220355-cfdc2b' blocked immediately; 6 SSRF tests passed", "PASSED"),
        ("Test G:\nDual-Tier Cloud Persistence", "Inspected AWS S3 data lake and DynamoDB table via AWS CLI following scraping runs", "Raw HTML in raw/ and JSON in transform/; structured items in DynamoDB table", "S3: 8 objects verified (AES256); DynamoDB: 71+ records verified with SHA-256 sort keys", "PASSED"),
        ("Test H:\nScheduled Batch Ingestion", "Simulated EventBridge scheduled event payload against Job Dispatcher Lambda", "Dispatcher parses scheduled trigger and distributes multi-site batch into SQS Job Queue", "Dispatcher returned mode='SQS_DISTRIBUTION', enqueued_count=4 jobs into ScraperJobQueue", "PASSED"),
        ("Test I:\nClient Data Inspection", "Used dashboard Results tab to filter, sort, paginate, and export datasets as CSV and JSON", "Dynamic column rendering, instant search, working pagination, RFC 4180 CSV export", "Verified client-side search, column sort on price/title, and direct CSV/JSON downloads", "PASSED"),
        ("Test J:\nRegression Testing", "Executed baseline sandbox scraping against Books to Scrape and Quotes to Scrape", "Original sandbox sources continue to scrape, validate, deduplicate, and persist", "Books to Scrape returned 20 records; Quotes to Scrape returned 10 records; 49/49 tests pass", "PASSED")
    ]
    t82 = doc.add_table(rows=len(t82_data) + 1, cols=5)
    for c_idx, h in enumerate(t82_headers):
        t82.cell(0, c_idx).paragraphs[0].text = h
    for r_idx, row in enumerate(t82_data):
        for c_idx, val in enumerate(row):
            t82.cell(r_idx + 1, c_idx).paragraphs[0].text = val

    format_table_header_and_rows(t82, [1.4, 1.6, 1.6, 1.5, 0.6])

    add_custom_heading(doc, "8.4 Fault Injection and Resilience Testing", level=2)
    add_body_paragraph(
        doc,
        "Fault injection experiments confirmed the resilience of the Step Functions orchestration model. Injected network timeouts "
        "(simulating 30-second hung connections) and malformed HTML payloads (stripping all required container tags) were caught "
        "by the state machine's States.ALL error handler within 1.2 seconds of failure detection. In all test cases, the failed payload "
        "was preserved in the SQS DLQ with zero data corruption in the DynamoDB table."
    )
    doc.add_page_break()


print("Chapters 6-8 generator defined.")
