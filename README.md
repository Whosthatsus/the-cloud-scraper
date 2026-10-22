# The Cloud Scraper — Serverless Automated Data Pipeline

> **Course:** Cloud Architecture Design (CAD) — BCSE355L  
> **Project Name:** The Cloud Scraper — Serverless Automated Data Pipeline  
> **Derived From:** AWS Step Functions ETL Pipeline Pattern  
> **Status:** Live AWS Deployment Verified • Public CloudFront Dashboard Live • 49/49 Automated Tests Passing  
> **Public Web Dashboard:** [https://d3k1ttzl3bzy2k.cloudfront.net](https://d3k1ttzl3bzy2k.cloudfront.net)  
> **API Gateway Endpoint:** `https://xehoja83gg.execute-api.ap-southeast-2.amazonaws.com/prod/scrape`  
> **AWS Region:** `ap-southeast-2` (Sydney)  

---

## 1. Executive Summary & Objective

**The Cloud Scraper** is a production-ready, serverless automated data ingestion and processing pipeline designed on AWS. 

In the original repository pattern, data ingestion was purely reactive and file-driven: users had to manually upload static CSV files into an S3 bucket to trigger execution. **The Cloud Scraper** transforms this architecture into an **active, automated web intelligence pipeline**:

1. **Automated Ingestion:** Periodically fetches web data on configurable schedules via **Amazon EventBridge** or on-demand via **Amazon API Gateway** (REST endpoint).
2. **Resilient Web Scraping:** Extracts structured content (titles, prices, ratings, authors, tags, URLs) using Python `Requests` and `BeautifulSoup` according to declarative, site-specific selector rules, with built-in `robots.txt` compliance checking.
3. **Data Quality & Hygiene:** Validates extracted records against strict schema and type rules, isolating malformed entities and rejecting corrupted feeds.
4. **Deterministic Deduplication:** Normalizes text and numeric formats, computing a deterministic **SHA-256 fingerprint hash** per entity to prevent redundant storage across recurring scrape cycles.
5. **Dual-Tier Cloud Storage:**
   - **Amazon S3 Data Lake:** Preserves immutable raw HTML snapshots (`raw/`) and versioned transformed JSON datasets (`transform/`).
   - **Amazon DynamoDB:** Stores queryable, structured records with partition key `site_id`, sort key `record_id`, and a Global Secondary Index on `content_hash` for fast identity lookups. Conditional writes (`attribute_not_exists(record_id)`) protect against redundant writes. Complete data lineage is maintained with `source_url` and ISO 8601 timestamps (`scraped_at`, `transformed_at`).
6. **Decoupling & Fault Isolation:** Employs **Amazon SQS** (`ScraperJobQueue`) with an associated **Dead-Letter Queue (DLQ)** (`ScraperDLQ`) to decouple multi-site batches and isolate persistent scraping failures without stalling downstream services.
7. **Workflow Orchestration:** Coordinated by **AWS Step Functions**, implementing exponential retry backoffs, task timeouts, and fail-safe catchers.
8. **Observability & FinOps:** Enriches execution logs in **Amazon CloudWatch**, issues operational alerts through **Amazon SNS**, and calculates estimated per-run serverless execution costs.

---

## 2. Architecture & Workflow

### Architectural Diagram

```mermaid
flowchart TD
    subgraph Trigger_Layer["1. Trigger & Ingestion Layer"]
        EB["Amazon EventBridge (Cron Rule)<br>cron(0 12 * * ? *)"] -->|Scheduled Event| Dispatcher
        APIG["Amazon API Gateway (REST API)<br>POST /scrape"] -->|On-Demand Request| Dispatcher
        SQS_In["Amazon SQS Job Queue"] -->|Queued Site Job| Dispatcher
        Dispatcher["AWS Lambda: Job Dispatcher<br>(lambda/start_step_function.py)"]
    end

    subgraph Orchestration_Layer["2. Workflow Orchestration Layer (AWS Step Functions)"]
        Dispatcher -->|Start Execution| SFN["AWS Step Functions State Machine<br>(CloudScraperStateMachine)"]
        
        SFN --> S1["1. Scrape Target Website<br>(lambda/scraper.py)"]
        S1 --> C1{"Scrape Status<br>SUCCESS?"}
        
        C1 -->|Yes| S2["2. Validate Extracted Records<br>(lambda/validation.py)"]
        C1 -->|No / Error| DLQ_Task["Route Failure to SQS DLQ"]
        
        S2 --> C2{"Validation<br>SUCCESS?"}
        C2 -->|Yes| S3["3. Transform & Deduplicate<br>(lambda/transformation.py)"]
        C2 -->|No / Error| DLQ_Task
        
        S3 --> S4["4. Store in Cloud<br>(lambda/dynamodb_store.py)"]
        S4 --> S5["5. Publish Success Notification<br>(lambda/notification.py)"]
        
        DLQ_Task --> S6["6. Publish Failure Notification<br>(lambda/notification.py)"]
        S6 --> FailState["Fail Execution State"]
    end

    subgraph Storage_Layer["3. Cloud Storage Layer"]
        S1 -.->|Raw HTML Snapshot| S3_Raw["Amazon S3: raw/<site_id>/<timestamp>/page.html"]
        S4 -.->|Clean Structured Items| DDB[("Amazon DynamoDB: TheCloudScraper-Records")]
        S4 -.->|Transformed JSON Archive| S3_Trans["Amazon S3: transform/<site_id>/records.json"]
    end

    subgraph Monitoring_Layer["4. Observability & Alerting Layer"]
        DLQ_Task --> SQS_DLQ["Amazon SQS Dead-Letter Queue (DLQ)"]
        SQS_DLQ -.-> CW_Alarm["CloudWatch Alarm (DLQ Messages >= 1)"]
        CW_Alarm -.-> SNS["Amazon SNS Alert Topic"]
        S5 --> SNS
        S6 --> SNS
        SNS --> Email["Operator Email Alerts"]
        SFN -.-> CW_Logs["CloudWatch Logs & X-Ray Traces"]
    end
```

---

## 3. Transition from Original Pattern (Architectural Rationale)

The original repository (`aws-samples/aws-step-functions-etl-pipeline-pattern`) implemented a batch file processing pattern. Here is how each component was evolved:

| Pipeline Stage | Original Architecture | The Cloud Scraper Evolution | Rationale for Change |
| :--- | :--- | :--- | :--- |
| **Ingestion** | S3 `ObjectCreated` event on CSV file uploads. | EventBridge cron rules + API Gateway REST API + SQS. | Eliminates manual upload bottleneck; enables fully autonomous, scheduled web harvesting and on-demand scraping. |
| **Extraction** | Read CSV via Pandas into memory. | Configurable HTTP scraping via Requests + BeautifulSoup. | Dynamically parses live HTML DOM trees using external declarative selectors (`config/sites_config.json`). |
| **Validation** | Cerberus schema validation on CSV rows. | Declarative rule validation (required fields, URL checks, minimum lengths, price bounds). | Handles real-world web variability, filtering malformed records while allowing clean records to continue. |
| **Deduplication** | None (row-by-row pass through). | Deterministic SHA-256 fingerprint hashing (`content_hash`). | Guarantees idempotency; recurring scrape jobs never store redundant copies of existing items. |
| **Transformation** | Heavy AWS Glue PySpark job (`gluejob.py`) writing Snappy Parquet. | Native serverless Python Lambda transformation. | Slashes cold-start latency from 3–5 minutes down to seconds; eliminates DPU cluster costs for streaming web data. |
| **Storage** | S3 stage/transform/archive folders. | Dual-tier storage: Amazon S3 (raw HTML snapshot immutability) + Amazon DynamoDB (NoSQL operational queries). | Adheres to modern data lakehouse best practices: audit trail preserved in S3, low-latency API queries served from DynamoDB. |
| **Fault Tolerance** | S3 move to `error/` folder. | Amazon SQS Dead-Letter Queue (DLQ) + Step Functions Retries + CloudWatch Alarm. | Isolates network transients, rate limiting, and broken HTML without blocking other scraping jobs. |
| **FinOps** | No cost visibility. | Built-in serverless execution cost estimation per run. | Cloud Architecture Design requirement: computes real-time micro-dollar cost across Lambda, S3, DynamoDB, and Step Functions. |

---

## 4. Repository Structure

```
the-cloud-scraper/
├── config/
│   └── sites_config.json            # Configurable target sites, CSS selectors, rate limits, rules
├── lambda/
│   ├── scraper.py                   # Website scraper & S3 raw snapshot archiver (Requests + BS4)
│   ├── validation.py                # Schema & data hygiene validator
│   ├── transformation.py           # Text cleaner, price/rating normalizer & SHA-256 deduplicator
│   ├── dynamodb_store.py            # DynamoDB batch writer (conditional writes) & S3 JSON archiver
│   ├── start_step_function.py      # Job Dispatcher (EventBridge / API Gateway / SQS trigger)
│   ├── notification.py             # FinOps cost estimator & SNS alert dispatcher
│   ├── requirements.txt             # Lambda deployment package dependencies
│   ├── move_file.py                 # (Preserved) S3 object management utility
│   ├── s3object.py                  # (Preserved) S3 folder initialization utility
│   ├── start_crawler.py             # (Preserved) Optional Glue Crawler starter
│   └── check_crawler.py             # (Preserved) Optional Glue Crawler status checker
├── scripts/
│   └── package_lambdas.py           # Self-contained build script creating deployable zip with dependencies
├── tests/
│   ├── test_scraper.py              # Unit tests for scraping, robots.txt & selector extraction
│   ├── test_validation.py           # Unit tests for schema validation & field filtering
│   ├── test_transformation.py       # Unit tests for normalization & SHA-256 deduplication
│   ├── test_dynamodb_store.py       # Unit tests for DynamoDB conditional writes & Decimal conversion
│   ├── test_dispatcher.py           # Unit tests for EventBridge, API Gateway, and SQS parsing
│   ├── test_notification.py         # Unit tests for FinOps calculation and SNS alert payloads
│   └── test_pipeline_integration.py # End-to-end integration simulation of Step Functions workflow
├── pipeline_runner.py               # Local CLI simulator for testing the entire pipeline end-to-end
├── template.yml                     # Complete AWS SAM / CloudFormation Infrastructure-as-Code template
├── parameter.json                   # CloudFormation parameter overrides
├── requirements.txt                 # Python project root dependencies
└── README.md                        # Project documentation & architectural guide
```

---

## 5. Sample Configuration: Permitted Test Websites & Open Feeds

Target websites and their extraction rules are configured declaratively in [`config/sites_config.json`](config/sites_config.json). The project supports 4 pre-configured, tested public sources that permit automated scraping:

### Target 1: Books to Scrape (`books_toscrape`)
- **Target URL:** `https://books.toscrape.com/catalogue/page-1.html`
- **Category:** E-commerce Sandbox
- **Container Selector:** `article.product_pod`
- **Extracted Fields:** `title`, `price` (normalized float GBP), `availability`, `rating` (1–5 int), `detail_link`
- **Pagination Support:** Next page followed via `li.next a` up to configured `page_limit`.

### Target 2: Quotes to Scrape (`quotes_toscrape`)
- **Target URL:** `https://quotes.toscrape.com/`
- **Category:** Quotations & Authors Sandbox
- **Container Selector:** `div.quote`
- **Extracted Fields:** `quote`, `author`, `author_url`, `tags` (string array)
- **Pagination Support:** Next page followed via `li.next a`.

### Target 3: WebScraper Laptops Sandbox (`webscraper_laptops`)
- **Target URL:** `https://webscraper.io/test-sites/e-commerce/allinone/computers/laptops`
- **Category:** Dedicated Scraper Testing Sandbox (117 test products)
- **Container Selector:** `div.product-wrapper`
- **Extracted Fields:** `title`, `price` (normalized float USD), `description`, `rating` (data-rating integer), `reviews` count, `detail_link`.

### Target 4: Hacker News Permitted Feed (`hacker_news`)
- **Target URL:** `https://news.ycombinator.com/`
- **Category:** Tech News & Aggregator (Robots.txt permitted for frontpage index)
- **Container Selector:** `tr.athing`
- **Extracted Fields:** `rank` (integer rank), `title`, `detail_link`.

---

## 5B. General-Purpose Web Scraping & Dynamic Target Registration

The Cloud Scraper is **not restricted** to a hard-coded list of domains. Users can enter arbitrary eligible public website URLs and extract data on demand via the dashboard or REST API:

1. **Automatic Generic Extraction Mode (`extraction_mode: "generic"`):**
   - Heuristically detects repeating cards, table rows, article containers, headings, links, and content paragraphs.
   - Requires zero CSS selector authoring.
   - Ideal for news blogs, documentation pages, press releases, and listings.

2. **Configurable CSS Selector Mode (`extraction_mode: "custom"`):**
   - Allows users to specify precise DOM element selectors for container, title, links, and custom metadata fields.
   - Dynamically mapped into Lambda extraction rules without rebuilding backend functions.

3. **Dynamic Target Registration in DynamoDB (`action: "save_target"`):**
   - Custom targets can be saved to DynamoDB with partition key `site_id` and sort key `TARGET_CONFIG`.
   - Saved targets appear automatically in the target selector and can be re-run on demand or on recurring schedules.

4. **Multi-Layer SSRF & Safety Protection:**
   - Pre-flight DNS resolution and IP validation.
   - Strictly blocks localhost (`127.0.0.1`, `::1`), RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local (`169.254.0.0/16`), and AWS IMDS metadata endpoints (`169.254.169.254`).
   - Automatically re-validates redirect URLs to prevent SSRF redirect bypasses.
   - Content-type filtering enforces `text/html` and limits maximum response payload to 5MB.

---

## 6. Local Testing & Verification (Zero-AWS-Prerequisite Mode)

You can verify the entire pipeline locally without requiring active AWS credentials.

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Launch the Upgraded Web Dashboard
Launch the lightweight zero-dependency local web dashboard to demonstrate the full application (frontend + backend pipeline) to your teacher without incurring any AWS charges:

```bash
python server.py
```
Open **[http://localhost:8000](http://localhost:8000)** in your web browser.

**Key Dashboard Features:**
- **Sidebar Navigation:** Clean dark-navy layout with 6 views (*Overview*, *Scrape Workspace*, *Results & Data*, *Execution History*, *Storage & Lineage*, *Step Functions ETL*).
- **Executive Overview:** Aggregated statistics across all historical runs (*Total Scraped, Valid Records, Duplicates Filtered, Clean Entities, Success/Fail Ratio, Latest Latency*).
- **Scrape Workspace:** Source selector across 4 feeds, custom URL field with strict SSRF guardrails, configurable page limits (1–5) and timeouts (3–30s).
- **Results Table:** Sortable columns (click any column header to sort ascending/descending), live text search filter, configurable items-per-page (10, 25, 50, All), and pagination controls.
- **Dual Export:** Download datasets directly as **RFC 4180 CSV** or **Standardized JSON** with one click.
- **Execution History:** Persisted audit log saved in `output/history.json` with direct "View" actions to inspect past runs.
- **SSRF & Network Security:** Strictly blocks internal hosts (`localhost`, `127.0.0.1`), RFC 1918 private subnets, non-standard ports, and cloud metadata service (`169.254.169.254`).
- **Fault-Tolerance Verification:** Click **"Test Fault Tolerance"** to simulate upstream network failure, verifying that Step Functions' Catch Block isolates the failure, diverts to the **SQS Dead Letter Queue (DLQ)**, and triggers the **SNS Alarm**.
- **Dual-Tier Storage Panel:** Disambiguates active local JSON storage (`output/<site_id>.json`) from cloud AWS targets (S3/DynamoDB), ensuring strict zero-cost transparency.

### Step 3: Run the Automated Test Suite (PyTest)
Execute all 41 unit and integration tests across all pipeline modules and security checks:
```bash
pytest -v tests/
```

**Expected Result:**
```
============================== 41 passed in 5.24s ==============================
```

### Step 4: Run the CLI Pipeline Simulator
The pipeline simulator [`pipeline_runner.py`](pipeline_runner.py) mirrors Step Functions execution semantics:

```bash
# 1. Run live scraping for Books to Scrape
python pipeline_runner.py --site books_toscrape

# 2. Run live scraping for Quotes to Scrape
python pipeline_runner.py --site quotes_toscrape

# 3. Run live scraping for WebScraper Laptops (117 items)
python pipeline_runner.py --site webscraper_laptops

# 4. Run live scraping for Hacker News
python pipeline_runner.py --site hacker_news

# 5. Run multi-site batch scraping across all configured sites
python pipeline_runner.py --all

# 6. Run with controlled offline HTML test fixture (zero internet requirement)
python pipeline_runner.py --fixture

# 7. Run controlled failure simulation (demonstrates SQS DLQ & SNS alerting)
python pipeline_runner.py --simulate-failure

# 5. Run controlled failure simulation (demonstrates SQS DLQ & SNS alerting)
python pipeline_runner.py --simulate-failure
```

### Step 4: Package Lambda Artifacts
To package the Lambda functions and production dependencies into a self-contained deployable zip:
```bash
python scripts/package_lambdas.py
```
This builds `build/the-cloud-scraper-lambda.zip` (~1.47 MB) containing all dependencies (`requests`, `beautifulsoup4`, `urllib3`, etc.) ready for deployment.

---

## 7. Cloud Deployment (AWS SAM / CloudFormation)

> [!NOTE]
> The following deployment commands require an active AWS account, configured AWS CLI credentials (`aws configure`), and the AWS SAM CLI installed.

### Prerequisites for Cloud Deployment
1. **AWS CLI** configured with administrator or deployment credentials.
2. **AWS SAM CLI** (`sam --version` >= 1.90).
3. A globally unique Amazon S3 bucket name.

### Step-by-Step Deployment

1. **Configure Parameters in `parameter.json`:**
   ```json
   [
     {
       "ParameterKey": "pProjectName",
       "ParameterValue": "the-cloud-scraper"
     },
     {
       "ParameterKey": "pS3BucketName",
       "ParameterValue": "my-unique-cloud-scraper-bucket-2026"
     },
     {
       "ParameterKey": "pEmailforNotification",
       "ParameterValue": "your-email@example.com"
     },
     {
       "ParameterKey": "pScrapeSchedule",
       "ParameterValue": "cron(0 12 * * ? *)"
     },
     {
       "ParameterKey": "pDefaultSiteId",
       "ParameterValue": "books_toscrape"
     }
   ]
   ```

2. **Build the SAM Application:**
   ```bash
   sam build
   ```

3. **Deploy the Stack:**
   ```bash
   sam deploy --guided
   ```
   *Or non-interactively using parameter overrides:*
   ```bash
   sam deploy \
     --stack-name the-cloud-scraper-stack \
     --template-file template.yml \
     --parameter-overrides file://parameter.json \
     --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
     --resolve-s3
   ```

4. **Confirm SNS Email Subscription:**
   Check the inbox of `pEmailforNotification` and click **"Confirm subscription"** in the AWS Notification email.

---

## 8. Triggering Cloud Executions

Once deployed on AWS, the pipeline can be triggered in three ways:

### A. Automated Schedule (EventBridge)
Runs automatically based on `pScrapeSchedule` (default: every day at 12:00 PM UTC).

### B. On-Demand API Trigger (API Gateway)
Send an HTTP POST request to the deployed REST endpoint:
```bash
curl -X POST https://<api-id>.execute-api.<region>.amazonaws.com/prod/scrape \
  -H "Content-Type: application/json" \
  -d '{"site_id": "books_toscrape"}'
```

### C. Direct Step Functions Execution (AWS CLI)
```bash
aws stepfunctions start-execution \
  --state-machine-arn <StateMachineArn> \
  --input '{"site_id": "quotes_toscrape"}'
```

---

## 9. FinOps Cost Estimation Model

One of the core tenets of Cloud Architecture Design is cost awareness. The following table provides an estimated operational cost breakdown for scraping **10,000 records per month**:

| Service Component | Operational Driver | Unit Pricing (us-east-1) | Monthly Cost (10,000 items) |
| :--- | :--- | :--- | :--- |
| **AWS Lambda** | 500 executions x 4 functions (2,000 runs, avg 1.5s @ 512MB) | $0.0000166667 / GB-s | ~$0.02 USD |
| **AWS Step Functions** | 500 executions x 5 state transitions (2,500 transitions) | $0.000025 / transition | ~$0.06 USD |
| **Amazon DynamoDB** | 10,000 Write Request Units (WRU) + Storage (<100MB) | $1.25 / million WRU | ~$0.01 USD |
| **Amazon S3** | 500 raw HTML snapshots + 500 JSON archives (1,000 PUTs) | $0.005 / 1,000 PUT requests | ~$0.01 USD |
| **Amazon SQS & SNS** | 500 notifications and message queues | Free tier eligible | ~$0.00 USD |
| **Total Estimated Cost** | **Monthly aggregate cost** | — | **< $0.15 USD / month** |

---

## 10. Stack Teardown & Cleanup

To avoid ongoing charges after completing evaluations or lab sessions:

```bash
# 1. Empty the S3 Data Lake Bucket
aws s3 rm s3://<pS3BucketName> --recursive

# 2. Delete the CloudFormation Stack
sam delete --stack-name the-cloud-scraper-stack
```

---

## 11. Ethical Scraping & Security Compliance

- **Permitted Sites:** Default configurations strictly target test-permitted sandbox domains (`books.toscrape.com`, `quotes.toscrape.com`).
- **Rate Limiting:** Built-in delay throttles (`rate_limit_delay_seconds: 1.0`) protect upstream web servers.
- **Identifiable User-Agent:** Requests identify the scraper (`TheCloudScraper/1.0 (+https://github.com/...; CAD-Course-Project)`).
- **Least Privilege:** IAM roles restrict resource access strictly to the project's DynamoDB table, S3 bucket, SQS queues, and SNS topic.
- **Data Encryption:** Server-Side Encryption (SSE-AES256) is enabled by default on S3, DynamoDB, SQS, and SNS.
