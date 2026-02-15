#!/usr/bin/env python3
import logging
from flask import Flask, send_from_directory
from flask_cors import CORS

from config import DASHBOARD_HOST, DASHBOARD_PORT, COMPOSE_FILE, LOG_LEVEL
from routes import gpu_bp, services_bp, system_bp, openwebui_bp
from benchmarking.routes import benchmarks_bp, init_benchmarking

app = Flask(__name__)
CORS(app)

logger = logging.getLogger(__name__)

# Register blueprints
app.register_blueprint(system_bp)
app.register_blueprint(gpu_bp)
app.register_blueprint(services_bp)
app.register_blueprint(openwebui_bp)
app.register_blueprint(benchmarks_bp)

# Initialize benchmarking subsystem
init_benchmarking(COMPOSE_FILE)


@app.route("/")
def index():
    """Serve the frontend"""
    return send_from_directory("static", "index.html")


@app.route("/benchmark")
def benchmark_page():
    """Serve the benchmark page"""
    return send_from_directory("static", "benchmark.html")


@app.route("/static/<path:path>")
def serve_static(path):
    """Serve static files"""
    return send_from_directory("static", path)


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


if __name__ == "__main__":
    logger.info(f"Starting LLM Dashboard on {DASHBOARD_HOST}:{DASHBOARD_PORT}")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=(LOG_LEVEL == "DEBUG"))
