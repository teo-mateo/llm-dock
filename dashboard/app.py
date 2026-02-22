#!/usr/bin/env python3
import os
import logging
from flask import Flask, send_from_directory, abort
from flask_cors import CORS

from config import init_config, DASHBOARD_HOST, DASHBOARD_PORT, LOG_LEVEL
from routes import gpu_bp, services_bp, system_bp, openwebui_bp
from benchmarking.routes import benchmarks_bp, init_benchmarking


def create_app(config=None):
    """Application factory."""
    init_config()

    app = Flask(__name__)
    app.json.sort_keys = False
    CORS(app)

    if config:
        app.config.update(config)

    # Store token on app config for request-time access
    from config import DASHBOARD_TOKEN, COMPOSE_FILE
    app.config.setdefault("DASHBOARD_TOKEN", DASHBOARD_TOKEN)

    # Register blueprints
    app.register_blueprint(system_bp)
    app.register_blueprint(gpu_bp)
    app.register_blueprint(services_bp)
    app.register_blueprint(openwebui_bp)
    app.register_blueprint(benchmarks_bp)

    # Initialize benchmarking subsystem
    compose_file = app.config.get("COMPOSE_FILE", COMPOSE_FILE)
    db_path = app.config.get("BENCHMARK_DB_PATH")
    init_benchmarking(app, compose_file, db_path=db_path)

    @app.route("/")
    def index():
        """Serve the frontend"""
        return send_from_directory("static", "index.html")

    @app.route("/benchmark")
    def benchmark_page():
        """Serve the benchmark page"""
        return send_from_directory("static", "benchmark.html")

    @app.route("/design-preview")
    def design_preview():
        """Serve the design preview page"""
        return send_from_directory("static", "design-preview.html")

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

    @app.route("/v2")
    def serve_v2_index():
        return send_from_directory("frontend/dist", "index.html")
    
    @app.route("/v2/<path:whatever>")
    def serve_v2_static(whatever):
        dist_dir = os.path.realpath(os.path.join(app.root_path, "frontend", "dist"))
        file_path = os.path.realpath(os.path.join(dist_dir, whatever))
        if file_path.startswith(dist_dir) and os.path.isfile(file_path):
            return send_from_directory("frontend/dist", whatever)
        # Only fall back to index.html for client-side routes (no file extension).
        # Asset requests (.js, .css, etc.) must 404 so browsers don't cache HTML
        # as a JS/CSS resource after deploys.
        if '.' in whatever.split('/')[-1]:
            abort(404)
        return send_from_directory("frontend/dist", "index.html")

    return app


logger = logging.getLogger(__name__)

# Module-level app for WSGI servers (e.g. gunicorn app:app)
app = create_app()

if __name__ == "__main__":
    logger.info(f"Starting LLM Dashboard on {DASHBOARD_HOST}:{DASHBOARD_PORT}")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=(LOG_LEVEL == "DEBUG"))
