# The Cloud Scraper — Report Evidence & Traceability Checklist
## Cloud Architecture and Design (BCSE355L) — Final Verification Audit

This internal checklist establishes end-to-end academic traceability between the claims made in **The Cloud Scraper Final Project Report (`The_Cloud_Scraper_Final_Project_Report.docx` and `.pdf`)**, the original **Review 1 Proposal (`24BIT0283,24BIT0317,24BIT0586FIRST_REVIEW (1).pdf`)**, the **Implementation Audit Report (`cad_final_review_report.md`)**, the **project repository source code**, and the **live AWS cloud deployment evidence** in the Sydney region (`ap-southeast-2`).

---

## 1. Document Metadata & Attribution Checklist

| Requirement / Field | Report Value | Source Baseline & Verification Proof | Status |
| :--- | :--- | :--- | :---: |
| **Project Title** | The Cloud Scraper — Serverless Automated Data Pipeline | Matches Review 1 proposal title exactly | **VERIFIED** |
| **Course Code & Title** | BCSE355L: Cloud Architecture and Design | Matches Review 1 proposal header exactly | **VERIFIED** |
| **Semester** | Fall 2026–2027 | Matches Review 1 proposal header exactly | **VERIFIED** |
| **Slot** | B1 + TB1 | Specified in student project registration | **VERIFIED** |
| **Course Faculty** | Prof. Venkatesh P | Matches course instructor assignment | **VERIFIED** |
| **Team Member 1** | Bhumi Choudhary — 24BIT0586 | Student registration & Review 1 author list | **VERIFIED** |
| **Team Member 2** | Kaushal More — 24BIT0283 | Student registration & Review 1 author list | **VERIFIED** |
| **Team Member 3** | Kshitij Agarwal — 24BIT0317 | Student registration & Review 1 author list | **VERIFIED** |
| **Academic School** | School of Computer Science Engineering and Information Systems (SCOPE) | Official institutional affiliation at VIT | **VERIFIED** |
| **Degree Programme** | B.Tech Information Technology | Official degree programme | **VERIFIED** |

---

## 2. Review 1 Baseline Objectives Traceability Matrix

| Review 1 Proposal Objective | Report Chapter / Section | Implementation Component | Live Cloud / Repo Evidence | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Obj 1: Serverless Event-Driven Architecture** | Chapter 1.2, 2.2, 5.1 | 6 AWS Lambda microservices + Step Functions | CloudFormation stack `the-cloud-scraper` active in `ap-southeast-2` | **VERIFIED** |
| **Obj 2: Scheduled & On-Demand Triggers** | Chapter 2.2, 5.2, 6.2 | Amazon EventBridge + API Gateway (`POST /scrape`) | API Gateway `xehoja83gg` returns HTTP 202; EventBridge rule configured | **VERIFIED** |
| **Obj 3: Decoupled Multi-Stage Pipeline** | Chapter 2.2, 5.3, 6.4–6.7 | AWS Step Functions (`the-cloud-scraper-pipeline-sm`) | State machine definition in `template.yml` lines 270–370 | **VERIFIED** |
| **Obj 4: Fault Tolerance & Dead-Letter Queue** | Chapter 2.2, 6.8, 10.5 | Step Functions Catch (`States.ALL`) & SQS DLQ | DLQ `the-cloud-scraper-scraper-dlq` verified with 3 quarantined messages | **VERIFIED** |
| **Obj 5: Durable Dual-Tier Persistence** | Chapter 2.2, 5.5, 6.7 | Amazon S3 Data Lake + Amazon DynamoDB | S3 bucket `the-cloud-scraper-bhumi-20261023` + DynamoDB `the-cloud-scraper-records` | **VERIFIED** |
| **Obj 6: Centralized Monitoring & Alerting** | Chapter 2.2, 6.9, 10.5 | Amazon CloudWatch Alarms + Amazon SNS Topic | SNS Topic `the-cloud-scraper-notifications-topic` (`bhumi.choudhary166@gmail.com`) | **VERIFIED** |
| **Obj 7: Cost Awareness & Pay-Per-Use** | Chapter 2.2, 6.9, 10.6 | FinOps micro-cost model in `notification.py` | Estimated execution cost: $0.000165 USD / run (<$0.15/month for 10,000 runs) | **VERIFIED** |
| **Obj 8: Least-Privilege IAM & Encryption** | Chapter 2.2, 10.3, 10.4 | `LambdaExecutionRole` + SSE-AES256 encryption | Scoped IAM policies in `template.yml`; default SSE-AES256 on S3 and DynamoDB | **VERIFIED** |
| **Obj 9: Infrastructure as Code (IaC)** | Chapter 2.2, 5.6 | AWS SAM / CloudFormation (`template.yml`) | Stack deployed and verified via `sam deploy` (`UPDATE_COMPLETE`) | **VERIFIED** |
| **Obj 10: Dynamic Target Innovation** | Chapter 3.4, 6.3, 6.4 | DynamoDB Target Registry + Heuristic Parser | Tested live on Hacker News and Travel Books (Acceptance Tests A & B) | **VERIFIED** |

---

## 3. Formal Acceptance Tests Verification Checklist (Tests A through J)

| Test ID | Test Description | Verified Execution / Artifact | Output Metrics & Cloud Proof | Status |
| :---: | :--- | :--- | :--- | :---: |
| **Test A** | Custom Target Registration & Scraping | `scrape-hacker_news_live-20261022220014-926eb4` | Extracted 30 live tech articles from news.ycombinator.com; saved to DynamoDB & S3 in 4.88s | **PASSED** |
| **Test B** | Generic HTML Extraction (Unfamiliar DOM) | `scrape-travel_books_generic-20261022220134-44d352` | Heuristically parsed 11 book items without CSS selectors; saved to DynamoDB & S3 in 3.25s | **PASSED** |
| **Test C** | Asynchronous Live Status Monitoring | Polled `GET /scrape?execution_arn=...` | Verified state transitions: `RUNNING` &rarr; `SUCCEEDED` with stop timestamps & durations | **PASSED** |
| **Test D** | Verification of Non-Fallback Behavior | Tested custom URL against `test_scraper.py` | Proved custom targets do NOT apply `books_toscrape` selectors; verified distinct record IDs | **PASSED** |
| **Test E** | Fault Tolerance & SQS DLQ Routing | `scrape-test_404_resilience-20261022220504-c820da` | Non-existent 404 URL caught by Step Functions; routed to DLQ; 3 messages visible in SQS | **PASSED** |
| **Test F** | Multi-Layer SSRF & Safety Protection | `scrape-ssrf_attack_test-20261022220355-cfdc2b` | Inbound attack targeting 169.254.169.254 blocked immediately; all 6 SSRF unit tests passed | **PASSED** |
| **Test G** | Dual-Tier Cloud Persistence Verification | S3 Data Lake & DynamoDB Table Inspections | 8 partitioned objects in S3 data lake (AES256); 71+ structured items in DynamoDB table | **PASSED** |
| **Test H** | Scheduled Batch Ingestion Simulation | Dispatcher invoked with EventBridge payload | Parsed `aws.events` trigger; distributed 4 jobs into `ScraperJobQueue` (`mode: SQS_DISTRIBUTION`) | **PASSED** |
| **Test I** | Client-Side Data Inspection & Export | Tested dashboard Results tab in browser | Dynamic column rendering, instant search, sorting, and RFC 4180 CSV / JSON downloads | **PASSED** |
| **Test J** | Regression Testing on Baseline Sandboxes | Verified Books to Scrape & Quotes to Scrape | 20 books and 10 quotes verified in DynamoDB; all 49 pytest unit & integration tests pass | **PASSED** |

---

## 4. Deployed AWS Infrastructure & Artifact Evidence

| Cloud Component | Resource Name / Physical ID | AWS Service | Operational State & Configuration Details |
| :--- | :--- | :--- | :--- |
| **Public Web Dashboard** | `https://d3k1ttzl3bzy2k.cloudfront.net` | Amazon CloudFront | Active CDN distribution (ID: `E63365QMCM5`), SSL/TLS terminated, HTTP 200 verified |
| **Web Origin Bucket** | `the-cloud-scraper-web-893041508558` | Amazon S3 | Static hosting origin containing `index.html`, `app.js`, `style.css`, and fallback datasets |
| **Ingestion API** | `xehoja83gg.execute-api.ap-southeast-2.amazonaws.com` | Amazon API Gateway | Regional REST API with `/scrape` resource supporting `POST`, `GET`, and `OPTIONS` |
| **State Machine** | `the-cloud-scraper-pipeline-sm` | AWS Step Functions | Standard State Machine in `ap-southeast-2`, 5 task states, 1 DLQ catch state |
| **Dispatcher Microservice** | `the-cloud-scraper-dispatcher` | AWS Lambda | Python 3.10, 512MB RAM, handles REST routing, target config saving, and SFN execution |
| **Scraper Microservice** | `the-cloud-scraper-scraper` | AWS Lambda | Python 3.10, Requests + BS4, SSRF guardrails, generic/custom extraction, 60s timeout |
| **Validation Microservice** | `the-cloud-scraper-validation` | AWS Lambda | Python 3.10, schema hygiene, field presence, URL validation, partitioning |
| **Transformation Microservice**| `the-cloud-scraper-transformation` | AWS Lambda | Python 3.10, mojibake cleaner, price/rating normalizer, SHA-256 fingerprint generator |
| **Storage Microservice** | `the-cloud-scraper-dynamodb-store` | AWS Lambda | Python 3.10, batch conditional writes (`attribute_not_exists`), S3 multi-part JSON writer |
| **Telemetry Microservice** | `the-cloud-scraper-notification` | AWS Lambda | Python 3.10, FinOps micro-cost calculator, Amazon SNS alert dispatcher |
| **Private Data Lake** | `the-cloud-scraper-bhumi-20261023` | Amazon S3 | Private bucket, Server-Side Encryption (`AES256`), partitioned by `raw/` and `transform/` |
| **Structured Store** | `the-cloud-scraper-records` | Amazon DynamoDB | On-Demand (PAY_PER_REQUEST), Partition Key: `site_id`, Sort Key: `record_id` |
| **Job Fan-Out Queue** | `the-cloud-scraper-job-queue` | Amazon SQS | Standard Queue for scheduled multi-site batch distribution |
| **Dead-Letter Queue (DLQ)**| `the-cloud-scraper-scraper-dlq` | Amazon SQS | Standard Queue, 14-day retention period (1,209,600s), active quarantine |
| **Notification Topic** | `the-cloud-scraper-notifications-topic` | Amazon SNS | Operational alert topic, email subscription: `bhumi.choudhary166@gmail.com` |
| **Cron Scheduler** | `the-cloud-scraper-scheduled-rule` | Amazon EventBridge | Expression: `cron(0 12 * * ? *)`, currently maintained in `DISABLED` state for cost safety |
| **Monitoring Alarm** | `the-cloud-scraper-dlq-alarm` | Amazon CloudWatch | Metric: `ApproximateNumberOfMessagesVisible >= 1` on DLQ, triggers SNS alert |
| **Execution Role** | `the-cloud-scraper-LambdaExecutionRole-*` | AWS IAM | Scoped policies for DynamoDB, S3, SQS, SNS, and CloudWatch Logs |

---

## 5. Storage Partitioning & Data Lineage Checklist

### S3 Data Lake Partition Layout (`s3://the-cloud-scraper-bhumi-20261023/`)
- `raw/books_toscrape/20261022T212959Z/page.html` (50,509 bytes) & `metadata.json` (247 bytes)
- `raw/quotes_toscrape/20261022T211844Z/page.html` (11,064 bytes) & `metadata.json` (228 bytes)
- `raw/hacker_news_live/20261022T220016Z/page.html` (34,737 bytes) & `metadata.json` (230 bytes)
- `raw/travel_books_generic/20261022T220135Z/page.html` (37,040 bytes) & `metadata.json` (276 bytes)
- `transform/books_toscrape/20261022T213003Z/records.json` (13,072 bytes) & `metadata.json` (365 bytes)
- `transform/quotes_toscrape/20261022T211848Z/records.json` (6,393 bytes) & `metadata.json` (348 bytes)
- `transform/hacker_news_live/20261022T220019Z/records.json` (17,327 bytes) & `metadata.json` (356 bytes)
- `transform/travel_books_generic/20261022T220137Z/records.json` (7,663 bytes) & `metadata.json` (406 bytes)

### DynamoDB Primary Key & Lineage Design (`the-cloud-scraper-records`)
- **Partition Key (`PK`)**: `site_id` (String, e.g., `hacker_news_live`, `books_toscrape`)
- **Sort Key (`SK`)**: `record_id` (String, e.g., `hacker_news_live#7f1f29aad09c559b` or `TARGET_CONFIG`)
- **Cryptographic Hash**: `content_hash` (64-character SHA-256 hex string)
- **Temporal Lineage**: `scraped_at` (ISO 8601 UTC) and `transformed_at` (ISO 8601 UTC)
- **Source Provenance**: `source_url` (Original target URL fetched by scraper)

---

## 6. Honest Technical Disclosures & Known Limitations

To maintain uncompromising academic integrity, the following limitations are explicitly documented in Chapter 11 of the report and confirmed by implementation evidence:

1. **Client-Side JavaScript Rendering (SPA Limitation)**:
   - *Current Behavior*: The scraper microservice utilizes Python `Requests` and `BeautifulSoup4`, which extract static HTML DOM trees. Websites that depend exclusively on client-side JavaScript execution (e.g., React/Vue/Angular SPAs requiring hydration) are not rendered.
   - *Documented Roadmap*: Future iterations propose deploying an AWS Fargate container task running headless Chromium/Playwright, coordinated by Step Functions Choice states.

2. **Distributed Rate Limiting Coordination**:
   - *Current Behavior*: Polite rate limits (1.0s delay) are enforced per Lambda invocation. If multiple concurrent Lambda instances target the same domain simultaneously, they do not share a global token bucket.
   - *Documented Roadmap*: Future iterations propose implementing an Amazon ElastiCache (Redis) token bucket or DynamoDB atomic counters.

3. **Anti-Bot Protections & CAPTCHA**:
   - *Current Behavior*: Websites utilizing Cloudflare Turnstile, PerimeterX, or reCAPTCHA challenges return HTTP 403/503 status codes. These are caught as errors and diverted to the SQS DLQ.
   - *Documented Roadmap*: Integration with authorized rotating proxy networks.

4. **EventBridge Scheduled Rule State**:
   - *Current Behavior*: The EventBridge rule (`the-cloud-scraper-scheduled-rule`) is currently kept in the `DISABLED` state in AWS to prevent unintended recurring charges during post-demonstration periods. On-demand scraping via API Gateway remains fully active.

---

## 7. Deliverable Verification Checklist

- [x] **Word Document Generated**: `C:\Users\BHUMI\.gemini\antigravity\scratch\the-cloud-scraper\The_Cloud_Scraper_Final_Project_Report.docx` (2,528.27 KB)
- [x] **PDF Document Exported via Word**: `C:\Users\BHUMI\.gemini\antigravity\scratch\the-cloud-scraper\The_Cloud_Scraper_Final_Project_Report.pdf` (1,414.75 KB)
- [x] **Evidence Checklist Generated**: `C:\Users\BHUMI\.gemini\antigravity\scratch\the-cloud-scraper\report_evidence_checklist.md`
- [x] **Publication Diagrams Embedded**: 6 figures at 300 DPI generated in `figures/` + 3 console screenshots in `images/`
- [x] **Automated Test Suite Verified**: 49 / 49 tests passing in Pytest (1.46s)
- [x] **Live Cloud Endpoints Verified**: Public CloudFront dashboard (`https://d3k1ttzl3bzy2k.cloudfront.net`) and REST API (`https://xehoja83gg.execute-api.ap-southeast-2.amazonaws.com/prod/scrape`) returning HTTP 200
- [x] **Full Chapter Structure**: All 12 chapters, Abstract, Acknowledgements, TOC, List of Figures, List of Tables, References, and Appendices A–D completely written and formatted.
