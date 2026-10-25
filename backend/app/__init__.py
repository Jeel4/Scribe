"""Flask application factory.

`create_app()` wires together configuration, the SQLite schema, the model
registry (models load lazily, once per process), the retrieval index and
the background job runner, then registers the API blueprints.
"""
import logging
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from .config import BACKEND_DIR, Config
from .db import init_db
from .models import ModelRegistry
from .services.analysis import JobRunner
from .services.retrieval import RetrievalIndex

log = logging.getLogger(__name__)


def create_app(config_overrides=None, registry=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    # A plain object view of the config for the services (they are Flask-free).
    cfg = type("RuntimeConfig", (), {k: app.config[k] for k in app.config if k.isupper()})

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db(cfg.DATABASE_PATH)

    app.extensions["scribe.config"] = cfg
    app.extensions["scribe.registry"] = registry or ModelRegistry(cfg)
    app.extensions["scribe.index"] = RetrievalIndex(cfg.DATABASE_PATH)
    app.extensions["scribe.jobs"] = JobRunner(
        cfg, app.extensions["scribe.registry"], app.extensions["scribe.index"]
    )

    CORS(app, resources={r"/api/*": {"origins": cfg.CORS_ORIGINS}})

    from .api import evaluation, meetings, search, system

    for bp in (meetings.bp, search.bp, evaluation.bp, system.bp):
        app.register_blueprint(bp, url_prefix="/api")

    _register_error_handlers(app)
    _serve_frontend_build(app)

    if cfg.PRELOAD_MODELS:
        app.extensions["scribe.registry"].preload()
    return app


def _register_error_handlers(app):
    @app.errorhandler(HTTPException)
    def http_error(exc):
        if exc.code == 413:
            message = f"File is too large. The limit is {app.config['MAX_UPLOAD_MB']:g} MB."
        else:
            message = exc.description or exc.name
        return jsonify(error=message), exc.code

    @app.errorhandler(Exception)
    def unexpected(exc):
        # Full traceback goes to the server log only — never to the client.
        log.exception("Unhandled error")
        return jsonify(error="Internal server error. Check the backend log for details."), 500


def _serve_frontend_build(app):
    """If `frontend/dist` exists (after `npm run build`), serve it from Flask
    so the whole app can run on one port. In development Vite serves it."""
    dist = Path(BACKEND_DIR).parent / "frontend" / "dist"

    @app.get("/")
    @app.get("/<path:path>")
    def frontend(path=""):
        if path.startswith("api/"):
            return jsonify(error="Unknown API endpoint."), 404
        if not dist.is_dir():
            return jsonify(
                message="Scribe API is running. Start the frontend with `npm run dev` "
                "in the frontend folder, or run `npm run build` to serve it from here."
            )
        target = dist / path
        if path and target.is_file() and dist in target.resolve().parents:
            return send_from_directory(dist, path)
        return send_from_directory(dist, "index.html")
