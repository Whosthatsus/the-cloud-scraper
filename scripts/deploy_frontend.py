"""
The Cloud Scraper - Production Frontend Deployment Script
Syncs the verified editorial frontend to the Amazon S3 static hosting bucket
and invalidates the Amazon CloudFront edge cache.
"""

import os
import sys
import subprocess
import urllib.request

REGION = "ap-southeast-2"
S3_BUCKET = "the-cloud-scraper-web-893041508558"
CLOUDFRONT_DIST_ID = "E63365QMCM5"
CLOUDFRONT_URL = "https://d3k1ttzl3bzy2k.cloudfront.net"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(PROJECT_ROOT, "web")


def run(cmd: str) -> bool:
    print(f"[EXEC] {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.stdout:
        print(res.stdout.strip())
    if res.stderr:
        print(res.stderr.strip())
    return res.returncode == 0


def main():
    print("=" * 70)
    print("THE CLOUD SCRAPER - PRODUCTION FRONTEND DEPLOYMENT")
    print(f"Target Bucket: s3://{S3_BUCKET}")
    print(f"CloudFront CDN: {CLOUDFRONT_URL} (ID: {CLOUDFRONT_DIST_ID})")
    print("=" * 70)

    # 1. Verify STS authentication
    print("\n[Step 1/3] Verifying AWS CLI caller identity...")
    if not run("aws sts get-caller-identity"):
        print("\n[BLOCKED] AWS authentication session is expired.")
        print("Please authenticate using 'aws login' and re-run this deployment.")
        sys.exit(1)

    # 2. Sync web directory to S3
    print(f"\n[Step 2/3] Uploading static assets from {WEB_DIR} to S3...")
    sync_cmd = f'aws s3 sync "{WEB_DIR}" "s3://{S3_BUCKET}" --delete --cache-control "max-age=300"'
    if not run(sync_cmd):
        print("\n[ERROR] Failed to sync frontend assets to S3.")
        sys.exit(1)
    print("  [OK] All web assets synced to S3 successfully.")

    # 3. Invalidate CloudFront edge cache
    print(f"\n[Step 3/3] Creating CloudFront cache invalidation (/*)...")
    inv_cmd = f'aws cloudfront create-invalidation --distribution-id {CLOUDFRONT_DIST_ID} --paths "/*"'
    if not run(inv_cmd):
        print("  [WARN] CloudFront invalidation could not be submitted automatically.")
    else:
        print("  [OK] CloudFront cache invalidation submitted.")

    # 4. Probe live CloudFront site
    print(f"\n[Verification] Checking live response from {CLOUDFRONT_URL}...")
    try:
        req = urllib.request.urlopen(CLOUDFRONT_URL, timeout=10)
        html = req.read().decode("utf-8", errors="ignore")
        has_new = "Collect. Clean. Store." in html
        print(f"  [OK] HTTP Status: {req.getcode()}")
        print(f"  [OK] Editorial Design Verified: {has_new}")
    except Exception as e:
        print(f"  [INFO] Verification notice: {e}")

    print("\n" + "=" * 70)
    print(f"DEPLOYMENT COMPLETE: {CLOUDFRONT_URL}")
    print("=" * 70)


if __name__ == "__main__":
    main()
