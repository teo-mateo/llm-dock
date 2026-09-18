"""The flag-metadata route serves every service template_type.

ik_llamacpp was missing from the allow-list: the pure get_flag_metadata()
handles it (sharing LLAMACPP_LLAMA_SERVER_FLAGS), so the 400 silently
blanked the parameter reference for 1 of 6 engines — on the details page
and in the create-service modal (issue #232 verification). The invariant
pinned here: a template_type POST /api/services accepts must also serve
its flag metadata, or the config UI degrades without any error surfacing.
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-flag-metadata")

from flag_metadata import MANDATORY_FIELDS, get_flag_metadata

TOKEN = "test-token-flag-metadata"

SERVICE_TEMPLATE_TYPES = sorted(MANDATORY_FIELDS)


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    from routes.services import services_bp
    app.register_blueprint(services_bp)
    app.testing = True
    return app.test_client()


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_every_service_template_type_serves_flag_metadata(client):
    for template_type in SERVICE_TEMPLATE_TYPES:
        r = client.get(f"/api/flag-metadata/{template_type}", headers=_auth())
        assert r.status_code == 200, f"{template_type} -> {r.status_code}: {r.get_json()}"
        assert r.get_json()["template_type"] == template_type
        assert r.get_json()["optional_flags"] == get_flag_metadata(template_type)
        assert r.get_json()["mandatory_fields"], template_type


def test_unknown_template_type_is_rejected(client):
    r = client.get("/api/flag-metadata/otherengine", headers=_auth())
    assert r.status_code == 400
