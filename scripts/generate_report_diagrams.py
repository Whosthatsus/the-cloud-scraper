"""
Generate publication-quality diagrams for the CAD Final Project Report.
Uses matplotlib to generate clean, legible, professional diagrams at 300 DPI.
"""

import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches

os.makedirs("figures", exist_ok=True)
plt.rcParams['font.sans-serif'] = 'Arial'
plt.rcParams['font.family'] = 'sans-serif'

# Palette
C_NAVY = "#0f172a"
C_BLUE = "#0284c7"
C_CYAN = "#06b6d4"
C_PURPLE = "#7c3aed"
C_GREEN = "#16a34a"
C_RED = "#dc2626"
C_AMBER = "#d97706"
C_SLATE = "#475569"
C_LIGHT = "#f8fafc"
C_CARD_BG = "#f1f5f9"
C_BORDER = "#cbd5e1"


def fig1_overall_architecture():
    fig, ax = plt.subplots(figsize=(14, 9), dpi=300)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 9)
    ax.axis("off")

    # Title
    ax.text(7, 8.6, "The Cloud Scraper — Overall AWS Serverless System Architecture", 
            ha="center", va="center", fontsize=15, fontweight="bold", color=C_NAVY)
    ax.text(7, 8.3, "Deployed Region: ap-southeast-2 (Sydney) | Production CloudFormation Stack: the-cloud-scraper",
            ha="center", va="center", fontsize=10, color=C_SLATE)

    # Subgraphs / Bounding Boxes
    def draw_box(x, y, w, h, title, fill_color, border_color):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1,rounding_size=0.15",
                                      facecolor=fill_color, edgecolor=border_color, linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x + 0.2, y + h - 0.25, title, fontsize=10, fontweight="bold", color=border_color)

    # 1. Client & Delivery Layer
    draw_box(0.5, 5.5, 3.2, 2.5, "1. Client & Delivery Layer", "#f0f9ff", C_BLUE)
    # 2. Ingestion & Trigger Layer
    draw_box(4.0, 5.5, 4.4, 2.5, "2. Trigger & Ingestion Layer", "#f5f3ff", C_PURPLE)
    # 3. Observability & Telemetry
    draw_box(8.7, 5.5, 4.8, 2.5, "3. Observability & Telemetry", "#fef2f2", C_RED)
    # 4. Orchestration & Processing Layer
    draw_box(0.5, 1.8, 8.0, 3.4, "4. Orchestration & Microservices (AWS Step Functions)", "#f8fafc", C_SLATE)
    # 5. Dual-Tier Storage Layer
    draw_box(8.7, 1.8, 4.8, 3.4, "5. Dual-Tier Cloud Storage", "#f0fdf4", C_GREEN)

    # Nodes / Components
    def draw_node(x, y, w, h, title, sub, color):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.1",
                                      facecolor="white", edgecolor=color, linewidth=1.2)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h/2 + 0.12, title, ha="center", va="center", fontsize=8.5, fontweight="bold", color=C_NAVY)
        ax.text(x + w/2, y + h/2 - 0.14, sub, ha="center", va="center", fontsize=7, color=C_SLATE)

    # Layer 1
    draw_node(0.7, 6.8, 2.8, 0.9, "Amazon CloudFront CDN", "https://d3k1ttzl3bzy2k.cloudfront.net", C_BLUE)
    draw_node(0.7, 5.7, 2.8, 0.9, "Amazon S3 Static Bucket", "the-cloud-scraper-web-893041508558", C_BLUE)

    # Layer 2
    draw_node(4.2, 6.8, 1.9, 0.9, "Amazon API Gateway", "POST & GET /scrape", C_PURPLE)
    draw_node(6.3, 6.8, 1.9, 0.9, "EventBridge Scheduler", "cron(0 12 * * ? *) [DISABLED]", C_PURPLE)
    draw_node(4.2, 5.7, 4.0, 0.9, "AWS Lambda: Job Dispatcher", "the-cloud-scraper-dispatcher", C_PURPLE)

    # Layer 3
    draw_node(8.9, 6.8, 2.1, 0.9, "Amazon SQS DLQ", "the-cloud-scraper-scraper-dlq", C_RED)
    draw_node(11.2, 6.8, 2.1, 0.9, "CloudWatch Alarm", "DLQ Messages >= 1", C_RED)
    draw_node(8.9, 5.7, 4.4, 0.9, "Amazon SNS Notifications Topic", "bhumi.choudhary166@gmail.com", C_RED)

    # Layer 4 (Step Functions Microservices)
    draw_node(0.7, 4.0, 7.6, 0.65, "AWS Step Functions State Machine: the-cloud-scraper-pipeline-sm", "Coordinates workflow execution with exponential retries and fail-safe catch blocks", C_SLATE)
    draw_node(0.7, 2.7, 1.7, 1.0, "1. Scraper Lambda", "Requests + BS4\nSSRF & robots.txt", C_SLATE)
    draw_node(2.65, 2.7, 1.7, 1.0, "2. Validator Lambda", "Quality Gates\nSchema & Types", C_SLATE)
    draw_node(4.6, 2.7, 1.7, 1.0, "3. Transform Lambda", "Text Normalization\nSHA-256 Hashing", C_SLATE)
    draw_node(6.55, 2.7, 1.7, 1.0, "4. Storage Lambda", "Batch PutItem\nS3 Multi-part Upload", C_SLATE)
    draw_node(3.6, 2.0, 3.6, 0.55, "5. Telemetry Lambda: notification.py", "FinOps Micro-Cost Estimation & SNS Broadcast", C_AMBER)

    # Layer 5 (Storage)
    draw_node(8.9, 3.7, 4.4, 1.2, "Amazon S3 Data Lake (Private)", "the-cloud-scraper-bhumi-20261023 (SSE-AES256)\n• raw/{site_id}/{timestamp}/page.html\n• transform/{site_id}/{timestamp}/records.json", C_GREEN)
    draw_node(8.9, 2.1, 4.4, 1.3, "Amazon DynamoDB Structured Table", "the-cloud-scraper-records (On-Demand)\n• Partition Key: site_id | Sort Key: record_id\n• Dynamic Target Config: record_id = 'TARGET_CONFIG'", C_GREEN)

    # Connecting Arrows
    def arrow(x1, y1, x2, y2, label=""):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color=C_SLATE, lw=1.2, shrinkA=3, shrinkB=3))
        if label:
            mx, my = (x1 + x2)/2, (y1 + y2)/2
            ax.text(mx, my + 0.08, label, fontsize=6.5, ha="center", va="bottom", color=C_SLATE,
                    bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.85))

    arrow(2.1, 6.8, 2.1, 6.6)
    arrow(3.5, 7.25, 4.2, 7.25, "HTTPS")
    arrow(5.15, 6.8, 5.15, 6.6)
    arrow(7.25, 6.8, 7.25, 6.6)
    arrow(6.2, 5.7, 4.5, 4.65, "StartExecution")
    arrow(2.4, 3.2, 2.65, 3.2)
    arrow(4.35, 3.2, 4.6, 3.2)
    arrow(6.3, 3.2, 6.55, 3.2)
    arrow(1.55, 2.7, 8.9, 4.3, "Raw HTML")
    arrow(8.25, 3.2, 8.9, 2.75, "PutItem")
    arrow(8.25, 3.2, 8.9, 4.1, "Clean JSON")
    arrow(6.55, 4.0, 8.9, 7.25, "Catch (States.ALL)")
    arrow(11.0, 7.25, 11.2, 7.25)
    arrow(12.25, 6.8, 12.25, 6.6)
    arrow(7.2, 2.27, 8.9, 6.0, "Alert Payload")

    # Footer
    ax.text(7, 0.4, "Figure 5.1: Overall AWS Serverless System Architecture showing end-to-end component interactions.",
            ha="center", va="center", fontsize=9.5, fontstyle="italic", color=C_NAVY)

    plt.tight_layout()
    plt.savefig("figures/fig1_overall_architecture.png", dpi=300)
    plt.close()
    print("Generated fig1_overall_architecture.png")


def fig2_etl_workflow():
    fig, ax = plt.subplots(figsize=(13, 6.5), dpi=300)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 6.5)
    ax.axis("off")

    ax.text(6.5, 6.0, "The Cloud Scraper — Serverless Multi-Stage ETL Pipeline Lifecycle", 
            ha="center", va="center", fontsize=14, fontweight="bold", color=C_NAVY)
    ax.text(6.5, 5.65, "End-to-end data flow from triggering through validation, deduplication, dual-tier persistence and FinOps telemetry",
            ha="center", va="center", fontsize=9, color=C_SLATE)

    stages = [
        ("1. INGESTION", "EventBridge / API Gateway\nJob Dispatcher Lambda\nDynamic Config Lookup", C_BLUE, 0.6),
        ("2. EXTRACTION", "Requests + BeautifulSoup\nrobots.txt Compliance\nSSRF Pre-flight Check\nRaw HTML Archival", C_PURPLE, 2.6),
        ("3. VALIDATION", "Schema Hygiene Gate\nRequired Field Presence\nURL & Type Checks\nInvalid Partitioning", C_AMBER, 4.6),
        ("4. TRANSFORMATION", "Text & Mojibake Clean\nPrice & Rating Parsing\nSHA-256 Fingerprint\nIdempotent Deduplication", C_CYAN, 6.6),
        ("5. DUAL STORAGE", "S3 Clean Data Lake\nDynamoDB NoSQL Store\nConditional Writes\nAudit Lineage Metadata", C_GREEN, 8.6),
        ("6. TELEMETRY", "FinOps Micro-Costing\nCloudWatch Metrics\nAmazon SNS Alerts\nSQS DLQ Fault Isolation", C_RED, 10.6),
    ]

    for title, desc, col, x in stages:
        rect = patches.FancyBboxPatch((x, 1.8), 1.8, 3.2, boxstyle="round,pad=0.08,rounding_size=0.15",
                                      facecolor="white", edgecolor=col, linewidth=1.8)
        ax.add_patch(rect)
        hdr_rect = patches.FancyBboxPatch((x, 4.4), 1.8, 0.6, boxstyle="round,pad=0.04,rounding_size=0.08",
                                          facecolor=col, edgecolor=col)
        ax.add_patch(hdr_rect)
        ax.text(x + 0.9, 4.7, title, ha="center", va="center", fontsize=8.5, fontweight="bold", color="white")
        ax.text(x + 0.9, 3.1, desc, ha="center", va="center", fontsize=7.5, color=C_NAVY, linespacing=1.4)

        if x < 10.0:
            ax.annotate("", xy=(x + 2.0, 3.4), xytext=(x + 1.8, 3.4),
                        arrowprops=dict(arrowstyle="->", color=C_SLATE, lw=1.8))

    # Bottom notes
    note_rect = patches.FancyBboxPatch((0.6, 0.7), 11.8, 0.8, boxstyle="round,pad=0.08,rounding_size=0.1",
                                       facecolor=C_CARD_BG, edgecolor=C_BORDER, linewidth=1.0)
    ax.add_patch(note_rect)
    ax.text(6.5, 1.1, "Decoupled Execution Guarantees:", ha="center", va="center", fontsize=8.5, fontweight="bold", color=C_NAVY)
    ax.text(6.5, 0.85, "Every stage executes within an isolated AWS Lambda invocation. Failures in one stage trigger Step Functions Catch blocks, preventing data loss or pipeline hangs.",
            ha="center", va="center", fontsize=7.5, color=C_SLATE)

    ax.text(6.5, 0.25, "Figure 5.2: Detailed multi-stage serverless ETL execution sequence with quality and deduplication gates.",
            ha="center", va="center", fontsize=9.5, fontstyle="italic", color=C_NAVY)

    plt.tight_layout()
    plt.savefig("figures/fig2_etl_workflow.png", dpi=300)
    plt.close()
    print("Generated fig2_etl_workflow.png")


def fig3_step_functions_flow():
    fig, ax = plt.subplots(figsize=(11, 8.5), dpi=300)
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 8.5)
    ax.axis("off")

    ax.text(5.5, 8.0, "AWS Step Functions State Machine Execution Flow & Error Routing", 
            ha="center", va="center", fontsize=13, fontweight="bold", color=C_NAVY)
    ax.text(5.5, 7.65, "State Machine: the-cloud-scraper-pipeline-sm | Demonstrates retries, task timeouts, and fail-safe DLQ catches",
            ha="center", va="center", fontsize=8.5, color=C_SLATE)

    def draw_state(x, y, w, h, title, sub, color):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.12",
                                      facecolor="white", edgecolor=color, linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h/2 + 0.1, title, ha="center", va="center", fontsize=8.5, fontweight="bold", color=C_NAVY)
        ax.text(x + w/2, y + h/2 - 0.15, sub, ha="center", va="center", fontsize=7, color=C_SLATE)

    # Start
    circ_start = patches.Circle((2.5, 7.0), 0.3, facecolor=C_GREEN, edgecolor=C_NAVY, lw=1.2)
    ax.add_patch(circ_start)
    ax.text(2.5, 7.0, "Start", ha="center", va="center", fontsize=7.5, fontweight="bold", color="white")

    # Happy path states
    states = [
        ("ScrapeTargetWebsite", "Task: lambda/scraper.py\nTimeout: 60s | Retry: 2x backoff", 5.6),
        ("ValidateExtractedRecords", "Task: lambda/validation.py\nValidates schema & types", 4.3),
        ("TransformAndDeduplicate", "Task: lambda/transformation.py\nComputes SHA-256 fingerprint", 3.0),
        ("StoreInCloud", "Task: lambda/dynamodb_store.py\nWrites DynamoDB & S3 Data Lake", 1.7),
        ("PublishSuccessNotification", "Task: lambda/notification.py\nPublishes SNS Success Alert", 0.7),
    ]

    ax.annotate("", xy=(2.5, 6.35), xytext=(2.5, 6.7), arrowprops=dict(arrowstyle="->", lw=1.5, color=C_SLATE))

    for name, sub, y in states:
        draw_state(0.8, y, 3.4, 0.75, name, sub, C_BLUE)
        if y > 1.0:
            ax.annotate("", xy=(2.5, y - 0.55), xytext=(2.5, y), arrowprops=dict(arrowstyle="->", lw=1.5, color=C_SLATE))

    # Success End
    circ_succ = patches.Circle((2.5, 0.15), 0.25, facecolor=C_GREEN, edgecolor=C_NAVY, lw=1.2)
    ax.add_patch(circ_succ)
    ax.text(2.5, 0.15, "Pass", ha="center", va="center", fontsize=6.5, fontweight="bold", color="white")
    ax.annotate("", xy=(2.5, 0.4), xytext=(2.5, 0.7), arrowprops=dict(arrowstyle="->", lw=1.5, color=C_SLATE))

    # Error Catch Column
    draw_state(6.8, 3.8, 3.4, 1.1, "SendToDLQ (Catch Handler)", "Resource: arn:aws:states:::sqs:sendMessage\nQueue: the-cloud-scraper-scraper-dlq\nQuarantines execution context", C_RED)
    draw_state(6.8, 2.0, 3.4, 0.9, "PublishFailureNotification", "Task: lambda/notification.py\nSends critical email alert via SNS", C_RED)

    circ_fail = patches.Circle((8.5, 0.8), 0.3, facecolor=C_RED, edgecolor=C_NAVY, lw=1.2)
    ax.add_patch(circ_fail)
    ax.text(8.5, 0.8, "Fail", ha="center", va="center", fontsize=7.5, fontweight="bold", color="white")

    ax.annotate("", xy=(8.5, 2.9), xytext=(8.5, 3.8), arrowprops=dict(arrowstyle="->", lw=1.5, color=C_RED))
    ax.annotate("", xy=(8.5, 1.1), xytext=(8.5, 2.0), arrowprops=dict(arrowstyle="->", lw=1.5, color=C_RED))

    # Error arrows connecting tasks to SendToDLQ
    for _, _, y in states[:4]:
        ax.annotate("", xy=(6.8, 4.35), xytext=(4.2, y + 0.37),
                    arrowprops=dict(arrowstyle="->", lw=1.2, color=C_RED, linestyle="dashed"))
    
    ax.text(5.3, 5.0, "Catch: States.ALL\n(Timeout, Error, SSRF)", fontsize=7, color=C_RED, fontweight="bold", ha="center")

    ax.text(5.5, -0.3, "Figure 5.3: Step Functions State Machine workflow with exponential retry backoff and DLQ quarantine catch blocks.",
            ha="center", va="center", fontsize=9, fontstyle="italic", color=C_NAVY)

    plt.tight_layout()
    plt.savefig("figures/fig3_step_functions_flow.png", dpi=300)
    plt.close()
    print("Generated fig3_step_functions_flow.png")


def fig4_target_sequence():
    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=300)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6.5)
    ax.axis("off")

    ax.text(6, 6.1, "Dynamic Target Registration and Execution Sequence", 
            ha="center", va="center", fontsize=13, fontweight="bold", color=C_NAVY)

    lanes = [
        ("Dashboard (User)", 1.2),
        ("API Gateway", 3.4),
        ("Job Dispatcher Lambda", 5.8),
        ("Amazon DynamoDB", 8.2),
        ("AWS Step Functions", 10.6),
    ]

    for name, x in lanes:
        rect = patches.FancyBboxPatch((x - 0.9, 5.2), 1.8, 0.5, boxstyle="round,pad=0.04", facecolor=C_NAVY, edgecolor=C_NAVY)
        ax.add_patch(rect)
        ax.text(x, 5.45, name, ha="center", va="center", fontsize=7.5, fontweight="bold", color="white")
        ax.plot([x, x], [0.8, 5.2], color=C_BORDER, linestyle="dashed", lw=1.2)

    def seq_msg(y, x1, x2, text, col=C_BLUE, dashed=False):
        style = "--" if dashed else "-"
        ax.annotate("", xy=(x2, y), xytext=(x1, y),
                    arrowprops=dict(arrowstyle="->", color=col, lw=1.3, linestyle=style))
        ax.text((x1 + x2)/2, y + 0.1, text, ha="center", va="bottom", fontsize=7, color=col, fontweight="bold")

    # Sequence steps
    seq_msg(4.7, 1.2, 3.4, "1. POST /scrape {action: 'save_target', config}", C_PURPLE)
    seq_msg(4.4, 3.4, 5.8, "2. Invoke Dispatcher", C_PURPLE)
    seq_msg(4.1, 5.8, 8.2, "3. PutItem (PK=site_id, SK='TARGET_CONFIG')", C_GREEN)
    seq_msg(3.8, 8.2, 5.8, "4. 200 Target Registered", C_GREEN, dashed=True)
    seq_msg(3.5, 5.8, 1.2, "5. 200 OK (Target Persisted)", C_PURPLE, dashed=True)

    seq_msg(3.0, 1.2, 3.4, "6. POST /scrape {site_id, extraction_mode}", C_BLUE)
    seq_msg(2.7, 3.4, 5.8, "7. Route Job Request", C_BLUE)
    seq_msg(2.4, 5.8, 8.2, "8. Query Target Config", C_GREEN)
    seq_msg(2.1, 8.2, 5.8, "9. Return Target Selectors", C_GREEN, dashed=True)
    seq_msg(1.8, 5.8, 10.6, "10. StartExecution(config_override)", C_AMBER)
    seq_msg(1.5, 5.8, 1.2, "11. 202 Accepted {executionArn}", C_BLUE, dashed=True)
    seq_msg(1.1, 1.2, 3.4, "12. GET /scrape?execution_arn=... (Poll status)", C_SLATE)
    seq_msg(0.8, 3.4, 1.2, "13. 200 OK {status: 'SUCCEEDED'}", C_GREEN, dashed=True)

    ax.text(6, 0.3, "Figure 6.1: Sequence diagram showing dynamic target configuration persistence and Step Functions execution.",
            ha="center", va="center", fontsize=9, fontstyle="italic", color=C_NAVY)

    plt.tight_layout()
    plt.savefig("figures/fig4_target_sequence.png", dpi=300)
    plt.close()
    print("Generated fig4_target_sequence.png")


def fig5_storage_layout():
    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=300)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6.5)
    ax.axis("off")

    ax.text(6, 6.1, "Dual-Tier Storage Architecture: Amazon S3 Data Lake vs Amazon DynamoDB", 
            ha="center", va="center", fontsize=13, fontweight="bold", color=C_NAVY)
    ax.text(6, 5.75, "Immutable raw audit archives and clean versioned JSON in S3; operational queryable NoSQL records in DynamoDB",
            ha="center", va="center", fontsize=8.5, color=C_SLATE)

    # Left: S3
    s3_rect = patches.FancyBboxPatch((0.5, 1.2), 5.3, 4.2, boxstyle="round,pad=0.1", facecolor="#f0fdf4", edgecolor=C_GREEN, lw=1.5)
    ax.add_patch(s3_rect)
    ax.text(3.15, 5.05, "Tier 1: Amazon S3 Data Lake", ha="center", va="center", fontsize=10, fontweight="bold", color=C_GREEN)
    ax.text(3.15, 4.75, "Bucket: the-cloud-scraper-bhumi-20261023 (AES256)", ha="center", va="center", fontsize=7.5, color=C_SLATE)

    s3_tree = """Partition Layout:
s3://the-cloud-scraper-bhumi-20261023/
  raw/
    hacker_news_live/
      20261022T220016Z/
        page.html        (34,737 bytes - Raw HTML)
        metadata.json    (230 bytes - Timestamp & URL)
    travel_books_generic/
      20261022T220135Z/
        page.html        (37,040 bytes - Raw HTML)
  transform/
    hacker_news_live/
      20261022T220019Z/
        records.json     (17,327 bytes - 30 records)
    travel_books_generic/
      20261022T220137Z/
        records.json     (7,663 bytes - 11 records)"""
    ax.text(0.8, 2.9, s3_tree, fontfamily="monospace", fontsize=6.8, va="center", color=C_NAVY)

    # Right: DynamoDB
    ddb_rect = patches.FancyBboxPatch((6.2, 1.2), 5.3, 4.2, boxstyle="round,pad=0.1", facecolor="#eff6ff", edgecolor=C_BLUE, lw=1.5)
    ax.add_patch(ddb_rect)
    ax.text(8.85, 5.05, "Tier 2: Amazon DynamoDB Structured Store", ha="center", va="center", fontsize=10, fontweight="bold", color=C_BLUE)
    ax.text(8.85, 4.75, "Table: the-cloud-scraper-records (On-Demand)", ha="center", va="center", fontsize=7.5, color=C_SLATE)

    ddb_schema = """Primary Key & Attributes:
• Partition Key (PK): site_id (String)
• Sort Key (SK): record_id (String)
  Format: <site_id>#<sha256_16char_prefix>
  Example: hacker_news_live#7f1f29aad09c559b

Target Registry Record:
  PK: hacker_news_live
  SK: TARGET_CONFIG
  target_url: https://news.ycombinator.com/
  container_selector: tr.athing

Standard Ingested Record Attributes:
  title: "AI and the Enclosure of the Commons"
  detail_link: "https://arxiv.org/abs/2610..."
  content_hash: "7f1f29aad09c559b44d4f..."
  scraped_at: "2026-10-22T22:00:16.118Z"
  transformed_at: "2026-10-22T22:00:18.573Z" """
    ax.text(6.5, 2.9, ddb_schema, fontfamily="monospace", fontsize=6.8, va="center", color=C_NAVY)

    ax.text(6, 0.6, "Figure 6.2: Dual-tier cloud data layout showing partitioned object paths in S3 and primary key design in DynamoDB.",
            ha="center", va="center", fontsize=9, fontstyle="italic", color=C_NAVY)

    plt.tight_layout()
    plt.savefig("figures/fig5_storage_layout.png", dpi=300)
    plt.close()
    print("Generated fig5_storage_layout.png")


def fig6_ssrf_architecture():
    fig, ax = plt.subplots(figsize=(11, 6), dpi=300)
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 6)
    ax.axis("off")

    ax.text(5.5, 5.6, "Multi-Layer SSRF and Security Guardrail Architecture", 
            ha="center", va="center", fontsize=13, fontweight="bold", color=C_NAVY)
    ax.text(5.5, 5.25, "Enforced inside lambda/scraper.py before opening any network socket or fetching upstream content",
            ha="center", va="center", fontsize=8.5, color=C_SLATE)

    steps = [
        ("1. Scheme Check", "Only 'http' and 'https'\nRejects 'file://', 'gopher://'", 0.6),
        ("2. DNS Pre-Flight", "Resolves hostname to\nIPv4 & IPv6 addresses", 2.7),
        ("3. Subnet Filter", "Blocks 127.0.0.0/8, 10.0.0.0/8\n172.16.0.0/12, 192.168.0.0/16\nBlocks IMDS: 169.254.169.254", 4.8),
        ("4. Redirect Guard", "Re-evaluates 301/302\nredirect location target\nthrough Steps 1-3", 6.9),
        ("5. Payload Cap", "Requires 'text/html'\nCaps payload at 5MB\nProtects Lambda memory", 9.0),
    ]

    for title, desc, x in steps:
        rect = patches.FancyBboxPatch((x, 2.2), 1.7, 2.4, boxstyle="round,pad=0.06,rounding_size=0.12",
                                      facecolor="white", edgecolor=C_PURPLE, lw=1.5)
        ax.add_patch(rect)
        hdr = patches.FancyBboxPatch((x, 4.0), 1.7, 0.6, boxstyle="round,pad=0.04", facecolor=C_PURPLE, edgecolor=C_PURPLE)
        ax.add_patch(hdr)
        ax.text(x + 0.85, 4.3, title, ha="center", va="center", fontsize=7.5, fontweight="bold", color="white")
        ax.text(x + 0.85, 3.1, desc, ha="center", va="center", fontsize=7, color=C_NAVY, linespacing=1.3)

        if x < 8.5:
            ax.annotate("", xy=(x + 1.9, 3.4), xytext=(x + 1.7, 3.4),
                        arrowprops=dict(arrowstyle="->", color=C_SLATE, lw=1.5))

    # Reject box below
    rej_box = patches.FancyBboxPatch((2.7, 0.8), 5.8, 0.8, boxstyle="round,pad=0.06", facecolor="#fef2f2", edgecolor=C_RED, lw=1.2)
    ax.add_patch(rej_box)
    ax.text(5.6, 1.3, "On Any Security Violation: Immediate Exception", ha="center", va="center", fontsize=8, fontweight="bold", color=C_RED)
    ax.text(5.6, 1.0, "Trapped by Step Functions -> Quarantined in SQS DLQ -> Zero AWS Internal Exposure",
            ha="center", va="center", fontsize=7.5, color=C_SLATE)

    for x in [1.45, 3.55, 5.65, 7.75]:
        ax.annotate("", xy=(5.6, 1.6), xytext=(x, 2.2),
                    arrowprops=dict(arrowstyle="->", color=C_RED, lw=1.0, linestyle="dashed"))

    ax.text(5.5, 0.3, "Figure 10.1: Multi-layer SSRF validation pipeline enforced on every inbound target URL before HTTP dispatch.",
            ha="center", va="center", fontsize=9, fontstyle="italic", color=C_NAVY)

    plt.tight_layout()
    plt.savefig("figures/fig6_ssrf_architecture.png", dpi=300)
    plt.close()
    print("Generated fig6_ssrf_architecture.png")


if __name__ == "__main__":
    fig1_overall_architecture()
    fig2_etl_workflow()
    fig3_step_functions_flow()
    fig4_target_sequence()
    fig5_storage_layout()
    fig6_ssrf_architecture()
    print("All 6 publication diagrams generated successfully.")
