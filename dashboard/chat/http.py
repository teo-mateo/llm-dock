from flask import jsonify

from .outcomes import PolicyError


def error_response(error: PolicyError):
    return jsonify(error.body()), error.status
