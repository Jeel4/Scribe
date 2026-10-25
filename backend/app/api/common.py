"""Small helpers shared by the API blueprints."""
import json

from flask import abort, current_app

from ..db import connect


def cfg():
    return current_app.extensions["scribe.config"]


def registry():
    return current_app.extensions["scribe.registry"]


def index():
    return current_app.extensions["scribe.index"]


def jobs():
    return current_app.extensions["scribe.jobs"]


def db():
    return connect(cfg().DATABASE_PATH)


def bad_request(message):
    abort(400, description=message)


def parse_bool(value, default):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_int(value, name, default, lo, hi):
    if value is None or value == "":
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        bad_request(f"'{name}' must be a whole number.")
    if not lo <= n <= hi:
        bad_request(f"'{name}' must be between {lo} and {hi}.")
    return n


def loads(text, default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default
