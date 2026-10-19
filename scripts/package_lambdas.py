"""
The Cloud Scraper - Lambda Packaging & Build Utility
Packages Lambda code and Python dependencies (requests, beautifulsoup4, etc.)
into a deployable artifact structure for AWS SAM or CloudFormation packaging.
"""

import os
import sys
import shutil
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAMBDA_DIR = os.path.join(PROJECT_ROOT, "lambda")
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
PACKAGE_DIR = os.path.join(BUILD_DIR, "lambda_package")


def build_deployment_package():
    print(f"[*] Project root: {PROJECT_ROOT}")
    print(f"[*] Packaging directory: {PACKAGE_DIR}")

    # Clean build directory
    if os.path.exists(PACKAGE_DIR):
        shutil.rmtree(PACKAGE_DIR)
    os.makedirs(PACKAGE_DIR, exist_ok=True)

    # 1. Install production dependencies into package directory
    req_file = os.path.join(LAMBDA_DIR, "requirements.txt")
    if os.path.exists(req_file):
        print(f"[*] Installing production dependencies from {req_file}...")
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            req_file,
            "--target",
            PACKAGE_DIR,
            "--no-user",
            "--upgrade",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[!] Warning during pip install: {result.stderr}")
        else:
            print("[+] Dependencies installed successfully.")

    # 2. Copy all Lambda source files
    print("[*] Copying Lambda source files...")
    for item in os.listdir(LAMBDA_DIR):
        src = os.path.join(LAMBDA_DIR, item)
        dst = os.path.join(PACKAGE_DIR, item)
        if item.endswith(".py"):
            shutil.copy2(src, dst)
            print(f"  -> {item}")

    # 3. Copy config directory into package
    target_config = os.path.join(PACKAGE_DIR, "config")
    if os.path.exists(target_config):
        shutil.rmtree(target_config)
    shutil.copytree(CONFIG_DIR, target_config)
    print("  -> config/sites_config.json")

    # 4. Create ZIP archive
    zip_path = os.path.join(BUILD_DIR, "the-cloud-scraper-lambda.zip")
    print(f"[*] Creating deployment zip: {zip_path}")
    shutil.make_archive(os.path.splitext(zip_path)[0], "zip", PACKAGE_DIR)
    zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[+] Successfully built deployable artifact: {zip_path} ({zip_size_mb:.2f} MB)")
    return zip_path


if __name__ == "__main__":
    build_deployment_package()
