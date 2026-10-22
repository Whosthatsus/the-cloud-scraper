"""
Chapters 1 through 5 of The Cloud Scraper Final Project Report.
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


def build_chapter_1(doc):
    """Chapter 1: Introduction"""
    add_custom_heading(doc, "Chapter 1: Introduction", level=1)
    
    add_custom_heading(doc, "1.1 Background and Motivation", level=2)
    add_body_paragraph(
        doc,
        "In the contemporary data economy, automated web data harvesting has become an indispensable capability across "
        "multiple industry sectors, including competitive retail intelligence, financial market forecasting, scientific research, "
        "and machine learning corpus preparation. Publicly accessible websites represent the largest, most dynamic repository "
        "of real-time information in existence. However, extracting high-volume data from the web in a robust, automated, "
        "and economically sustainable manner presents profound distributed systems challenges."
    )
    add_body_paragraph(
        doc,
        "Traditionally, web scraping systems have been engineered as long-running monolithic scripts deployed on dedicated "
        "Virtual Private Servers (VPS) or cloud instances such as Amazon EC2. These architectures suffer from acute structural "
        "inefficiencies: they incur continuous 24/7 compute billing regardless of actual scraping activity, fail catastrophically "
        "when network timeouts or DOM structure changes occur, lack automated deduplication, and require manual operational intervention "
        "to scale up or recover. Conversely, the rise of serverless computing architectures offers an unprecedented opportunity to "
        "reimagine web data collection as an event-driven, decoupled, and micro-billed extract-transform-load (ETL) pipeline."
    )

    add_custom_heading(doc, "1.2 Context of Cloud Architecture and Design", level=2)
    add_body_paragraph(
        doc,
        "This project was undertaken within the academic framework of the Cloud Architecture and Design (BCSE355L) course at "
        "Vellore Institute of Technology. The primary academic directive of this course is to evaluate and implement enterprise cloud "
        "patterns that satisfy the core tenets of the AWS Well-Architected Framework: Operational Excellence, Security, Reliability, "
        "Performance Efficiency, and Cost Optimization."
    )
    add_body_paragraph(
        doc,
        "Rather than relying on theoretical simulations or provisioned mock servers, The Cloud Scraper was conceived as a "
        "live, fully implemented reference architecture that demonstrates how serverless primitives (AWS Lambda, AWS Step Functions, "
        "Amazon DynamoDB, Amazon S3, Amazon SQS, and Amazon EventBridge) can be orchestrated into an autonomous web intelligence system. "
        "The project rigorously examines how serverless state machines can manage transient network failures, enforce schema hygiene, "
        "prevent redundant storage via deterministic cryptographic hashing, and dynamically scale from zero to parallel multi-target "
        "executions while achieving near-zero idle economic overhead."
    )

    add_custom_heading(doc, "1.3 Project Scope and Intended Use Cases", level=2)
    add_body_paragraph(
        doc,
        "The operational scope of The Cloud Scraper encompasses the complete lifecycle of automated web harvesting, beginning "
        "with dynamic target ingestion and culminating in dual-tier cloud persistence and FinOps monitoring. Specifically, the platform supports:"
    )
    add_bullet_item(doc, "On-Demand & Scheduled Data Ingestion: Triggering single-target or multi-source batch collection via REST API or cron rules.", "• Ingestion: ")
    add_bullet_item(doc, "General-Purpose DOM Extraction: Heuristic generic card discovery or targeted CSS selector parsing on any permitted public URL.", "• Extraction: ")
    add_bullet_item(doc, "Data Hygiene & Quality Enforcement: Automated rejection of malformed, incomplete, or corrupted records before cloud storage.", "• Validation: ")
    add_bullet_item(doc, "Deterministic Idempotency: Computing SHA-256 content hashes to eliminate duplicate records across recurring scraping cycles.", "• Deduplication: ")
    add_bullet_item(doc, "Dual-Tier Persistence: Preserving immutable raw HTML snapshots in an S3 Data Lake and structured entities in Amazon DynamoDB.", "• Storage: ")
    add_bullet_item(doc, "Fault Isolation & Resilience: Quarantining persistent failures into an SQS Dead-Letter Queue (DLQ) without pipeline stalling.", "• Fault Tolerance: ")

    add_custom_heading(doc, "1.4 Document Organization", level=2)
    add_body_paragraph(
        doc,
        "This report is structured into twelve comprehensive chapters detailing the complete design, engineering, verification, "
        "and empirical outcomes of the project. Chapter 2 formalizes the problem statement and maps the Review 1 baseline objectives "
        "to our actual implementation. Chapter 3 contrasts the proposed system against existing scrapers. Chapter 4 outlines functional "
        "and non-functional requirements. Chapter 5 details the cloud architecture and state machine design. Chapter 6 provides an "
        "in-depth breakdown of microservice implementations. Chapter 7 details the technology stack. Chapter 8 presents unit and formal "
        "acceptance test matrices. Chapter 9 discusses empirical cloud results. Chapter 10 covers security, SSRF defense, and FinOps costs. "
        "Chapter 11 addresses limitations and future work, and Chapter 12 concludes the report."
    )
    doc.add_page_break()


def build_chapter_2(doc):
    """Chapter 2: Problem Statement and Objectives"""
    add_custom_heading(doc, "Chapter 2: Problem Statement and Objectives", level=1)
    
    add_custom_heading(doc, "2.1 Problem Definition", level=2)
    add_body_paragraph(
        doc,
        "Organizations that require continuous web data intelligence face a fundamental infrastructure dilemma. "
        "Conventional scraping pipelines are typically deployed on virtual machines or containers that run continuously. "
        "When web traffic is intermittent or scheduled once per day, these servers remain idle for over 95% of the billing cycle, "
        "wasting significant cloud budgets. Furthermore, web scraping is inherently fragile: target websites frequently introduce "
        "transient network latency, HTTP 429 rate limits, HTTP 500 server errors, or subtle structural DOM updates. "
        "In a monolithic script, any unhandled network hiccup crashes the entire batch, resulting in corrupted datasets, data loss, "
        "and silent failures that go unnoticed until downstream business intelligence pipelines break."
    )
    add_body_paragraph(
        doc,
        "Additionally, traditional web data collection lacks formal data quality gates and cryptographic deduplication. "
        "Scraped records are frequently dumped directly into relational tables or unindexed CSV files without schema validation, "
        "causing dirty records (missing titles, null prices, garbled encodings) to pollute corporate databases. When scrapers re-run on "
        "a schedule, they blindly re-insert identical records, consuming unnecessary storage and requiring computationally expensive "
        "downstream deduplication. The problem addressed by this project is to design, implement, and verify a cloud-native, "
        "fully serverless architecture that eliminates idle costs, isolates failures, automates quality gates, and guarantees "
        "idempotent cloud persistence."
    )

    add_custom_heading(doc, "2.2 Original Proposal Objectives (Review 1 Baseline)", level=2)
    add_body_paragraph(
        doc,
        "In the initial project proposal (Review 1), our team established nine core architectural objectives designed to "
        "satisfy the curricular and technical requirements of BCSE355L. These baseline objectives were formulated as follows:"
    )
    add_bullet_item(doc, "Design a fully serverless, event-driven architecture for automated data scraping that requires zero server provisioning or manual scaling.", "Objective 1: ")
    add_bullet_item(doc, "Implement scheduled and on-demand triggers so scraping jobs run automatically at defined intervals or via external API calls.", "Objective 2: ")
    add_bullet_item(doc, "Build a decoupled, multi-stage pipeline (extract → validate/clean → transform → store) using managed queues and orchestration services.", "Objective 3: ")
    add_bullet_item(doc, "Ensure fault tolerance through automatic retries, dead-letter queues, and checkpointing so transient failures do not corrupt the pipeline.", "Objective 4: ")
    add_bullet_item(doc, "Persist raw and processed data in a durable, queryable cloud data store to support downstream analytics, reporting, or ML use cases.", "Objective 5: ")
    add_bullet_item(doc, "Implement centralized logging, monitoring, and alerting so pipeline health, execution cost, and failures are visible in real time.", "Objective 6: ")
    add_bullet_item(doc, "Optimize for cost and elasticity by relying entirely on pay-per-execution compute, scaling to zero when idle.", "Objective 7: ")
    add_bullet_item(doc, "Enforce least-privilege security using fine-grained IAM roles, encrypted storage, and secret management.", "Objective 8: ")
    add_bullet_item(doc, "Package the entire architecture as Infrastructure-as-Code (IaC) so it can be deployed and versioned consistently.", "Objective 9: ")

    add_custom_heading(doc, "2.3 Expected Outcomes", level=2)
    add_body_paragraph(
        doc,
        "The expected outcome of the project was a fully functioning, publicly demonstrable web data engineering platform. "
        "The system was expected to demonstrate rapid elasticity by spinning up stateless Lambda workers on demand, executing "
        "under Step Functions supervision, quarantining failures into an SQS Dead-Letter Queue without human intervention, "
        "and providing a browser-based dashboard for data exploration and export."
    )

    add_custom_heading(doc, "2.4 Objective-to-Implementation Mapping", level=2)
    add_body_paragraph(
        doc,
        "To ensure rigorous academic traceability, Table 2.1 maps every original Review 1 objective directly to its "
        "deployed AWS implementation component, operational mechanism, and verified verification proof."
    )

    # Table 2.1
    t21_headers = ["Original Objective (Review 1)", "Implemented Cloud Component", "Architectural Mechanism", "Verification Proof"]
    t21_data = [
        ("1. Fully Serverless Architecture", "AWS Lambda + AWS Step Functions", "6 Python 3.10 microservices, state machine execution", "Stack 'the-cloud-scraper' ACTIVE in ap-southeast-2"),
        ("2. Scheduled & On-Demand Triggers", "Amazon EventBridge + API Gateway", "REST API (POST /scrape) and cron rule (pScrapeSchedule)", "API Gateway returns HTTP 202; EventBridge rule configured"),
        ("3. Decoupled Multi-Stage Pipeline", "Step Functions + SQS Job Queue", "States: Scrape -> Validate -> Transform -> Store -> Notify", "State Machine: the-cloud-scraper-pipeline-sm"),
        ("4. Fault Tolerance & Dead-Letter Queue", "Amazon SQS DLQ + Step Functions Catch", "Fail-safe catch (States.ALL) routes failed context to DLQ", "the-cloud-scraper-scraper-dlq verified (3 msgs quarantined)"),
        ("5. Durable Dual-Tier Persistence", "Amazon S3 Data Lake + DynamoDB", "Raw HTML snapshots in S3; structured items in DynamoDB", "S3: 8 partitioned objects; DynamoDB: 71+ records"),
        ("6. Centralized Monitoring & Alerts", "CloudWatch Logs/Alarms + Amazon SNS", "Structured JSON logs, metric filters, email alerts to SNS", "Topic: the-cloud-scraper-notifications-topic active"),
        ("7. Pay-Per-Use Cost Optimization", "AWS Lambda On-Demand + FinOps", "Scale-to-zero when idle; micro-cost model per execution", "Estimated cost: $0.000165 USD / execution (<$0.15/mo)"),
        ("8. Least-Privilege IAM & Encryption", "IAM Execution Roles + SSE-AES256", "Scoped IAM policies; S3/DynamoDB/SQS/SNS server encryption", "IAM Role LambdaExecutionRole; SSE-AES256 enforced"),
        ("9. Infrastructure-as-Code (IaC)", "AWS SAM / CloudFormation", "template.yml defining 20+ cloud resources declaratively", "SAM deploy succeeded (UPDATE_COMPLETE)"),
        ("10. Dynamic Target Innovation", "DynamoDB Registry + Heuristic Parser", "Generic Auto-Extraction and Custom Selectors via UI", "Tested on Hacker News & Travel Books (Acceptance A & B)")
    ]
    t21 = doc.add_table(rows=len(t21_data) + 1, cols=4)
    for c_idx, h in enumerate(t21_headers):
        t21.cell(0, c_idx).paragraphs[0].text = h
    for r_idx, row in enumerate(t21_data):
        for c_idx, val in enumerate(row):
            t21.cell(r_idx + 1, c_idx).paragraphs[0].text = val

    format_table_header_and_rows(t21, [1.5, 1.6, 1.8, 1.6])
    doc.add_page_break()


def build_chapter_3(doc):
    """Chapter 3: Existing System vs. Proposed System"""
    add_custom_heading(doc, "Chapter 3: Existing System and Proposed System", level=1)
    
    add_custom_heading(doc, "3.1 Limitations of Traditional Web Scraping Implementations", level=2)
    add_body_paragraph(
        doc,
        "Prior to the widespread adoption of serverless architectures, organizations implemented web data extraction "
        "using dedicated virtual machines (e.g., EC2 instances running Linux, Scrapy daemons, or Celery task queues). "
        "While functionally capable of issuing HTTP requests, these legacy implementations exhibit five severe architectural flaws:"
    )
    add_bullet_item(doc, "Continuous Idle Resource Waste: Virtual machines run 24 hours a day, 7 days a week, consuming compute, memory, and operating system licensing fees even when data is collected only once every few hours.", "1. Economic Inefficiency: ")
    add_bullet_item(doc, "Monolithic Failure Coupling: Scraping, cleaning, and database insertions typically execute within a single monolithic process. An unhandled network timeout or parsing exception on one website terminates the entire Python process, failing all concurrent jobs.", "2. Brittle Fault Domains: ")
    add_bullet_item(doc, "Rigid Hard-Coded Targets: Scraping scripts embed target URLs and CSS selectors directly into Python source code. Adding a new website requires modifying code, running regression tests, and redeploying production servers.", "3. Lack of Configurability: ")
    add_bullet_item(doc, "Absence of Idempotency: Traditional scrapers append raw rows directly into tables without deterministic fingerprinting. Re-running a failed job results in duplicate records, bloating database tables and corrupting analytic aggregates.", "4. Redundant Ingestion: ")
    add_bullet_item(doc, "Black-Box Observability: Legacy cron scripts output unformatted stdout logs to local flat files. Cloud engineers have no real-time visibility into per-target error rates, execution latencies, or micro-dollar operational costs.", "5. Deficient Telemetry: ")

    add_custom_heading(doc, "3.2 The Serverless Paradigm Shift", level=2)
    add_body_paragraph(
        doc,
        "The Cloud Scraper completely refactors web data extraction by decomposing the traditional scraping monolith into "
        "stateless, ephemeral serverless microservices orchestrated by a distributed state machine. In this architecture, compute "
        "resources exist only for the exact duration of an HTTP fetch, validation check, or database write. When no scraping jobs "
        "are executing, compute utilization drops to absolute zero, eliminating 100% of idle infrastructure costs."
    )
    add_body_paragraph(
        doc,
        "Furthermore, by delegating workflow execution to AWS Step Functions, error handling becomes a declarative cloud primitive. "
        "Transient network errors are automatically retried using exponential backoff with jitter. Persistent failures are caught "
        "and isolated into a managed Dead-Letter Queue (Amazon SQS), allowing unaffected jobs to complete unimpeded."
    )

    add_custom_heading(doc, "3.3 Comparative Architectural Analysis", level=2)
    add_body_paragraph(
        doc,
        "Table 3.1 provides a detailed technical comparison contrasting traditional VM-based scraping architectures against "
        "The Cloud Scraper across six critical software engineering dimensions."
    )

    # Table 3.1
    t31_headers = ["Engineering Dimension", "Traditional VM / Server Scraping", "The Cloud Scraper (Proposed System)"]
    t31_data = [
        ("Compute Model", "Dedicated, always-on EC2 VM or Docker container", "Stateless, ephemeral AWS Lambda microservices"),
        ("Cost Profile", "Fixed monthly billing ($15–$70+/month for 24/7 VM)", "Pure pay-per-use micro-billing ($0.000165/run; $0.00 idle)"),
        ("Scaling Capability", "Vertical scaling capped by VM RAM/CPU; slow autoscaling", "Instant horizontal elasticity (0 to 1,000 concurrent Lambdas)"),
        ("Target Extensibility", "Hard-coded Python scripts requiring code redeployment", "Dynamic Target Registry (DynamoDB) + Generic Auto-Extraction"),
        ("Fault Isolation", "Process crashes kill all active and pending scraping jobs", "State Machine Catch blocks divert failures to SQS DLQ"),
        ("Data Quality & Hygiene", "Raw records written directly without pre-storage checks", "Dedicated Validation Gate microservice filters bad schema"),
        ("Data Deduplication", "Blind inserts requiring expensive downstream SQL dedup", "Deterministic SHA-256 content hashing at transformation"),
        ("Storage Strategy", "Single local disk or direct relational database table", "Dual-tier: Raw immutable S3 data lake + DynamoDB NoSQL")
    ]
    t31 = doc.add_table(rows=len(t31_data) + 1, cols=3)
    for c_idx, h in enumerate(t31_headers):
        t31.cell(0, c_idx).paragraphs[0].text = h
    for r_idx, row in enumerate(t31_data):
        for c_idx, val in enumerate(row):
            t31.cell(r_idx + 1, c_idx).paragraphs[0].text = val

    format_table_header_and_rows(t31, [1.8, 2.3, 2.4])

    add_custom_heading(doc, "3.4 Core Architectural Innovations", level=2)
    add_body_paragraph(
        doc,
        "In alignment with the innovation component articulated in our Review 1 proposal, The Cloud Scraper implements "
        "seven distinct technical innovations that distinguish it from standard scraping scripts:"
    )
    add_bullet_item(doc, "Every phase of the pipeline—ingestion, fetching, validation, transformation, storage, and notification—executes as an independent serverless invocation. Zero servers are provisioned.", "1. Zero-Server Event-Driven Architecture: ")
    add_bullet_item(doc, "The platform is not limited to pre-configured sandbox sites. Users can register arbitrary public website URLs dynamically through the web dashboard, persisting extraction rules in DynamoDB without redeploying code.", "2. Dynamic Target Registration Registry: ")
    add_bullet_item(doc, "When scraping unmapped websites with unfamiliar DOM structures, the scraper heuristically detects repeating cards, headings, links, and content paragraphs without requiring manual CSS selector authoring.", "3. Automatic Generic HTML Extraction Heuristics: ")
    add_bullet_item(doc, "Scheduled EventBridge triggers fan out multi-site batch requests into an Amazon SQS Job Queue, enabling independent, parallel state machine executions across distinct failure domains.", "4. Decoupled SQS Fan-Out Execution: ")
    add_bullet_item(doc, "Extracted records pass through an explicit validation microservice that verifies schema integrity, enforces non-empty string types, and isolates malformed records before storage.", "5. Automated Schema Validation Gate: ")
    add_bullet_item(doc, "Transient HTTP errors trigger exponential backoff retries. Unrecoverable errors are routed to an SQS Dead-Letter Queue with real-time SNS email notifications, ensuring zero pipeline stalling.", "6. Self-Healing DLQ Quarantine: ")
    add_bullet_item(doc, "A dedicated telemetry Lambda microservice calculates real-time execution costs across AWS compute, state transitions, storage, and networking, publishing micro-cost estimates to CloudWatch and SNS.", "7. FinOps Micro-Cost Telemetry: ")

    doc.add_page_break()


def build_chapter_4(doc):
    """Chapter 4: Requirements Analysis"""
    add_custom_heading(doc, "Chapter 4: Requirements Analysis", level=1)
    
    add_custom_heading(doc, "4.1 Functional Requirements", level=2)
    add_body_paragraph(
        doc,
        "The functional requirements define the specific operational behaviors and business capabilities that the platform must execute:"
    )
    add_bullet_item(doc, "The system must accept on-demand scraping requests via an HTTP POST /scrape endpoint on Amazon API Gateway, returning an HTTP 202 Accepted response with a unique Step Functions execution ARN.", "FR-1: On-Demand API Triggering: ")
    add_bullet_item(doc, "The system must support automated periodic execution of scraping batches based on configurable EventBridge cron schedules (default: cron(0 12 * * ? *)).", "FR-2: Scheduled Batch Ingestion: ")
    add_bullet_item(doc, "The system must allow users to register custom target URLs dynamically and persist their configuration (container selectors, fields, extraction mode) in Amazon DynamoDB.", "FR-3: Dynamic Target Configuration: ")
    add_bullet_item(doc, "The system must provide an Automatic Generic Extraction Mode that discovers repeating cards, titles, and links on unfamiliar websites without manual selector input.", "FR-4: Generic HTML Extraction: ")
    add_bullet_item(doc, "The scraper microservice must fetch target web content over HTTP/HTTPS, enforce robots.txt compliance, apply polite rate limits, and archive the raw HTML snapshot into Amazon S3.", "FR-5: Resilient Web Scraping: ")
    add_bullet_item(doc, "The system must validate extracted items against strict schema rules, partitioning records into valid and invalid sets to prevent corrupt data entry.", "FR-6: Schema Validation: ")
    add_bullet_item(doc, "The system must normalize text, fix character encoding mojibake, parse numeric ratings/prices, and generate a deterministic SHA-256 content hash per entity.", "FR-7: Data Transformation & Deduplication: ")
    add_bullet_item(doc, "The system must store processed records in Amazon DynamoDB using conditional writes (attribute_not_exists) and write clean versioned JSON to Amazon S3.", "FR-8: Dual-Tier Persistence: ")
    add_bullet_item(doc, "The system must trap failed executions via Step Functions catch blocks and quarantine the execution payload into an Amazon SQS Dead-Letter Queue.", "FR-9: Fault Isolation: ")
    add_bullet_item(doc, "The system must calculate estimated operational costs per execution and publish notifications to Amazon SNS.", "FR-10: FinOps Telemetry: ")
    add_bullet_item(doc, "The system must provide a public web dashboard that monitors Step Functions execution status in real time and allows client-side RFC 4180 CSV / JSON dataset downloads.", "FR-11: Web Dashboard & Export: ")

    add_custom_heading(doc, "4.2 Non-Functional Requirements", level=2)
    add_bullet_item(doc, "The pipeline must scale automatically from zero to concurrent executions under load, provisioning microservice instances on demand without manual capacity provisioning.", "NFR-1: Elasticity & Scalability: ")
    add_bullet_item(doc, "The system must achieve 99.9% availability for API ingestion and guarantee that transient network failures do not stall the state machine or cause silent data loss.", "NFR-2: Reliability & Fault Tolerance: ")
    add_bullet_item(doc, "Individual Lambda function stages must execute within configured task timeouts (Scraper: 60s, Validation: 15s, Transformation: 15s, Storage: 30s), maintaining end-to-end latency below 10 seconds for standard pages.", "NFR-3: Performance & Latency: ")
    add_bullet_item(doc, "The system must enforce strict multi-layer Server-Side Request Forgery (SSRF) protection, pre-flight DNS filtering, least-privilege IAM roles, and SSE-AES256 encryption at rest.", "NFR-4: Security & Privacy: ")
    add_bullet_item(doc, "The operational cost per scraping execution must remain below $0.001 USD, maintaining 100% eligibility for AWS Free Tier limits during evaluation.", "NFR-5: Cost Efficiency (FinOps): ")

    add_custom_heading(doc, "4.3 Software, Cloud, and Infrastructure Requirements", level=2)
    add_body_paragraph(
        doc,
        "The platform relies on the following software runtime and cloud infrastructure components:"
    )
    add_bullet_item(doc, "Python 3.10 runtime environment across all six AWS Lambda microservices, utilizing Requests (2.31.0), BeautifulSoup4 (4.12.3), and Boto3 (1.34.0).", "• Runtime Environment: ")
    add_bullet_item(doc, "AWS Serverless Application Model (SAM) CLI (v1.135.0) and AWS CloudFormation for Infrastructure as Code definition, packaging, and deployment.", "• IaC & Deployment: ")
    add_bullet_item(doc, "Vanilla ES6 JavaScript, HTML5, and CSS3 for the responsive web dashboard, served via Amazon CloudFront (CDN) with an Amazon S3 static website origin.", "• Frontend Stack: ")
    add_bullet_item(doc, "Pytest (v9.1.1) with unittest.mock for automated unit, integration, and security test execution.", "• Testing Framework: ")

    add_custom_heading(doc, "4.4 External System Dependencies & Ethical Constraints", level=2)
    add_body_paragraph(
        doc,
        "Because The Cloud Scraper interacts with external third-party web servers, it is strictly bound by ethical web harvesting policies. "
        "The scraper microservice identifies itself using a custom User-Agent header ('TheCloudScraper/1.0 (+https://github.com/...; CAD-Course-Project)'), "
        "evaluates target robots.txt permissions prior to issuance, and introduces configurable delay throttles (1.0 second default) "
        "between paginated requests to prevent aggressive server loading. The platform specifically restricts its scope to publicly accessible, "
        "unauthenticated web resources and does not attempt credential stuffing, CAPTCHA bypass, or private data harvesting."
    )
    doc.add_page_break()


def build_chapter_5(doc):
    """Chapter 5: System Architecture and Design"""
    add_custom_heading(doc, "Chapter 5: System Architecture and Design", level=1)
    
    add_custom_heading(doc, "5.1 Overall System Architecture", level=2)
    add_body_paragraph(
        doc,
        "The Cloud Scraper is architected as an event-driven serverless ecosystem partitioned into five decoupled tiers: "
        "(1) Public Client Delivery Layer, (2) Trigger and Ingestion Layer, (3) Orchestration Layer, (4) Microservice Processing Layer, "
        "and (5) Dual-Tier Cloud Storage and Telemetry Layer. Figure 5.1 illustrates the complete topology of deployed resources "
        "in the AWS Sydney region (ap-southeast-2)."
    )

    fig1_path = os.path.join(FIGURES_DIR, "fig1_overall_architecture.png")
    add_figure_with_caption(doc, fig1_path, "Figure 5.1: Overall AWS Serverless System Architecture deployed in ap-southeast-2 (Sydney).", width_inches=6.2)

    add_custom_heading(doc, "5.2 Component Responsibilities and Layered Design", level=2)
    add_body_paragraph(
        doc,
        "Each architectural layer enforces strict single-responsibility boundaries to prevent monolithic coupling:"
    )
    add_bullet_item(doc, "Provides global, low-latency SSL/TLS distribution of the responsive dashboard via Amazon CloudFront (Distribution ID: E63365QMCM5) backed by a private Amazon S3 static hosting bucket (the-cloud-scraper-web-893041508558).", "1. Client Delivery Layer: ")
    add_bullet_item(doc, "Exposes a public REST API endpoint via Amazon API Gateway (https://xehoja83gg.execute-api.ap-southeast-2.amazonaws.com/prod/scrape) and manages periodic triggers via Amazon EventBridge. Directs requests to the Job Dispatcher Lambda (the-cloud-scraper-dispatcher).", "2. Ingestion Layer: ")
    add_bullet_item(doc, "Governed by AWS Step Functions (the-cloud-scraper-pipeline-sm). Coordinates microservice task transitions, implements exponential retries, and executes fail-safe catches.", "3. Orchestration Layer: ")
    add_bullet_item(doc, "Consists of five discrete Lambda microservices: Web Scraper (scraper.py), Schema Validator (validation.py), Transformer & Deduplicator (transformation.py), Storage Writer (dynamodb_store.py), and FinOps Telemetry (notification.py).", "4. Microservice Layer: ")
    add_bullet_item(doc, "Dual-tier persistence comprising an immutable S3 Data Lake (the-cloud-scraper-bhumi-20261023) and an On-Demand Amazon DynamoDB table (the-cloud-scraper-records), alongside an Amazon SQS DLQ (the-cloud-scraper-scraper-dlq) and Amazon SNS.", "5. Storage & Telemetry Layer: ")

    add_custom_heading(doc, "5.3 End-to-End Serverless ETL Workflow", level=2)
    add_body_paragraph(
        doc,
        "The end-to-end data lifecycle progresses through six sequential phases. Figure 5.2 details the workflow stages, "
        "highlighting the quality filters, cryptographic hashing checkpoints, and storage partitioning."
    )

    fig2_path = os.path.join(FIGURES_DIR, "fig2_etl_workflow.png")
    add_figure_with_caption(doc, fig2_path, "Figure 5.2: Multi-stage serverless ETL execution sequence showing validation and deduplication checkpoints.", width_inches=6.2)

    add_custom_heading(doc, "5.4 Workflow Orchestration with AWS Step Functions", level=2)
    add_body_paragraph(
        doc,
        "In traditional pipelines, orchestration is hard-coded within application logic, creating brittle code that cannot gracefully "
        "recover from transient infrastructure exceptions. The Cloud Scraper delegates all state transitions to an AWS Step Functions "
        "Standard State Machine. Figure 5.3 depicts the state machine graph, illustrating the happy-path progression from scraping to "
        "notification alongside the catch blocks that divert failures to the Dead-Letter Queue."
    )

    fig3_path = os.path.join(FIGURES_DIR, "fig3_step_functions_flow.png")
    add_figure_with_caption(doc, fig3_path, "Figure 5.3: AWS Step Functions State Machine workflow showing exponential retry backoff and DLQ routing.", width_inches=5.8)

    add_custom_heading(doc, "5.5 Dual-Tier Cloud Storage Strategy", level=2)
    add_body_paragraph(
        doc,
        "A foundational design decision of The Cloud Scraper is the implementation of a dual-tier cloud storage architecture "
        "that reconciles the competing requirements of immutable compliance auditing and low-latency operational querying:"
    )
    add_bullet_item(doc, "Amazon S3 Data Lake: Serves as the immutable raw and processed repository. When a page is scraped, the exact raw HTML response and HTTP headers are archived immediately under s3://the-cloud-scraper-bhumi-20261023/raw/{site_id}/{timestamp}/page.html. Transformed datasets are saved under transform/{site_id}/{timestamp}/records.json. Both partitions enforce Server-Side Encryption (SSE-AES256).", "• Data Lake Tier (Amazon S3): ")
    add_bullet_item(doc, "Amazon DynamoDB Structured Store: Serves as the operational querying and deduplication tier. Clean records are indexed using partition key site_id and sort key record_id. DynamoDB conditional writes (attribute_not_exists(record_id)) reject duplicate records at the database engine level, guaranteeing write idempotency.", "• Operational Tier (Amazon DynamoDB): ")

    add_custom_heading(doc, "5.6 Infrastructure as Code Design (AWS SAM)", level=2)
    add_body_paragraph(
        doc,
        "The entire platform architecture is defined declaratively in template.yml using AWS Serverless Application Model (SAM). "
        "This includes all six Lambda functions, IAM execution roles, API Gateway REST definitions, Step Functions state machine JSON, "
        "DynamoDB table schemas, S3 bucket encryption configurations, SQS queues, and CloudWatch alarms. Packaging the stack as IaC "
        "enables 100% reproducible deployments across any AWS account with a single command (sam build && sam deploy)."
    )
    doc.add_page_break()


print("Chapters 1-5 generator defined.")
