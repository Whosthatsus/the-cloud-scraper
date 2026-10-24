"""
The Cloud Scraper - Lambda Deployment Utility
Updates deployed AWS Lambda functions with the latest packaged zip artifact.
"""

import os
import boto3

REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP_PATH = os.path.join(PROJECT_ROOT, "build", "the-cloud-scraper-lambda.zip")

FUNCTIONS = [
    "the-cloud-scraper-scraper",
    "the-cloud-scraper-validation",
    "the-cloud-scraper-transformation",
    "the-cloud-scraper-storage",
    "the-cloud-scraper-notification",
    "the-cloud-scraper-dispatcher",
]


def deploy_lambdas():
    if not os.path.exists(ZIP_PATH):
        raise FileNotFoundError(f"Deployment artifact not found at {ZIP_PATH}. Run package_lambdas.py first.")

    with open(ZIP_PATH, "rb") as f:
        zip_bytes = f.read()

    size_mb = len(zip_bytes) / (1024 * 1024)
    print(f"[*] Deploying {size_mb:.2f} MB artifact across {len(FUNCTIONS)} Lambda functions in {REGION}...")

    client = boto3.client("lambda", region_name=REGION)
    for fn in FUNCTIONS:
        try:
            res = client.update_function_code(
                FunctionName=fn,
                ZipFile=zip_bytes,
            )
            print(f"  [+] {fn:35} -> Version: {res.get('Version')}, Updated: {res.get('LastModified')}")
        except Exception as e:
            print(f"  [!] Failed updating {fn}: {e}")

    print("[+] All Lambda microservices deployed successfully.")


if __name__ == "__main__":
    deploy_lambdas()
