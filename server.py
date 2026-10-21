"""
The Cloud Scraper - Local Web Server & REST API
Provides a lightweight HTTP API and static file server for the
Cloud Scraper Frontend Dashboard. Implemented using Python's built-in
http.server with ZERO extra external dependencies.
"""

import os
import sys
import json
import mimetypes
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Add current directory and lambda to sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "lambda"))

import pipeline_runner

WEB_DIR = os.path.join(PROJECT_ROOT, "web")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "sites_config.json")


class CloudScraperRequestHandler(BaseHTTPRequestHandler):

    def end_headers(self):
        # Enable CORS for local API access
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, file_path: str, content_type: str = None, as_attachment: bool = False, filename: str = ""):
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            self._send_json(404, {"error": "File not found", "path": file_path})
            return

        if not content_type:
            content_type, _ = mimetypes.guess_type(file_path)
            content_type = content_type or "application/octet-stream"

        with open(file_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if "text" in content_type or "json" in content_type or "javascript" in content_type else content_type)
        self.send_header("Content-Length", str(len(content)))
        if as_attachment:
            fname = filename or os.path.basename(file_path)
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if not path:
            path = "/"

        # 1. API: List configured target sites
        if path == "/api/sites":
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self._send_json(200, {"status": "SUCCESS", "sites": cfg.get("sites", [])})
            except Exception as e:
                self._send_json(500, {"error": f"Failed reading site config: {str(e)}"})
            return

        # 2. API: System health & AWS status
        if path == "/api/status":
            local_files = []
            if os.path.exists(OUTPUT_DIR):
                local_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".json")]

            self._send_json(200, {
                "status": "ONLINE",
                "mode": "Zero-Cost Local Demonstration Mode",
                "aws_configured": False,
                "aws_credentials_status": "Not configured (Operating locally at $0.00 cost)",
                "local_output_files": local_files,
                "project_root": PROJECT_ROOT,
            })
            return

        # 3. API: Download JSON file
        if path.startswith("/api/download/"):
            site_id = path.replace("/api/download/", "").strip()
            # Clean path to prevent path traversal
            safe_site_id = "".join(c for c in site_id if c.isalnum() or c in ("_", "-"))
            json_file = os.path.join(OUTPUT_DIR, f"{safe_site_id}.json")
            if os.path.exists(json_file):
                self._serve_file(json_file, content_type="application/json", as_attachment=True, filename=f"{safe_site_id}.json")
            else:
                self._send_json(404, {"error": f"No stored JSON data found for '{safe_site_id}'. Run a scrape first."})
            return

        # 4. API: Read stored JSON data
        if path.startswith("/api/data/"):
            site_id = path.replace("/api/data/", "").strip()
            safe_site_id = "".join(c for c in site_id if c.isalnum() or c in ("_", "-"))
            json_file = os.path.join(OUTPUT_DIR, f"{safe_site_id}.json")
            if os.path.exists(json_file):
                self._serve_file(json_file, content_type="application/json")
            else:
                self._send_json(404, {"error": f"No stored JSON data found for '{safe_site_id}'."})
            return

        # 5. Frontend UI: Static assets
        if path in ("/", "/index.html"):
            index_path = os.path.join(WEB_DIR, "index.html")
            self._serve_file(index_path, content_type="text/html")
            return

        # Serve other files from web directory (style.css, app.js, images, etc.)
        relative_path = path.lstrip("/")
        if relative_path.startswith("web/"):
            relative_path = relative_path[4:]
        file_path = os.path.join(WEB_DIR, relative_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            self._serve_file(file_path)
            return

        self._send_json(404, {"error": "Endpoint or resource not found", "path": path})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        # API: Trigger scrape pipeline
        if path in ("/api/scrape", "/scrape"):
            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(post_body.decode("utf-8")) if post_body else {}
            except Exception:
                payload = {}

            site_id = payload.get("site_id", "books_toscrape")
            use_fixture = bool(payload.get("fixture", False))
            simulate_failure = bool(payload.get("simulate_failure", False))

            # Run the serverless pipeline locally
            try:
                result = pipeline_runner.run_pipeline(
                    site_id=site_id,
                    use_fixture=use_fixture,
                    simulate_failure=simulate_failure,
                )
                self._send_json(200, result)
            except Exception as e:
                self._send_json(500, {
                    "status": "FAILURE",
                    "site_id": site_id,
                    "error": f"Pipeline execution error: {str(e)}",
                })
            return

        self._send_json(404, {"error": "POST endpoint not found", "path": path})

    def log_message(self, format, *args):
        # Clean logging format
        sys.stderr.write(f"[{self.log_date_time_string()}] {args[0]} {args[1]} -> {args[2]}\n")


def run_server(port: int = 8000, host: str = "127.0.0.1"):
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, CloudScraperRequestHandler)
    print("=" * 70)
    print("  🚀 THE CLOUD SCRAPER - LOCAL WEB DASHBOARD & REST API")
    print("=" * 70)
    print(f"  * UI Dashboard:  http://localhost:{port}/")
    print(f"  * REST API:      http://localhost:{port}/api/sites")
    print(f"  * Scrape Route:  POST http://localhost:{port}/api/scrape")
    print(f"  * Zero-Cost Mode: Local server active, no AWS cloud charges incurred.")
    print("=" * 70)
    print("Press Ctrl+C to stop the server.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()
        print("Server stopped cleanly.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="The Cloud Scraper - Local Web Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    args = parser.parse_args()
    run_server(port=args.port, host=args.host)
