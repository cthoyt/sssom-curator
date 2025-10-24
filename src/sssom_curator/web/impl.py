"""Web curation interface for :mod:`biomappings`."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

import flask
import flask_bootstrap

from .blueprint import blueprint, url_for_state
from .components import Controller
from ..constants import DEFAULT_RESOLVER_BASE

if TYPE_CHECKING:
    from curies import Converter, Reference

__all__ = [
    "get_app",
]


def get_app(
    *,
    target_references: Iterable[Reference] | None = None,
    predictions_path: Path | None = None,
    positives_path: Path | None = None,
    negatives_path: Path | None = None,
    unsure_path: Path | None = None,
    controller: Controller | None = None,
    user: Reference | None = None,
    resolver_base: str | None = None,
    title: str | None = None,
    footer: str | None = None,
    converter: Converter | None = None,
) -> flask.Flask:
    """Get a curation flask app."""
    app = flask.Flask(__name__)
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = os.urandom(8)
    app.config["SHOW_RELATIONS"] = True
    app.config["SHOW_LINES"] = False
    if controller is None:
        if (
            predictions_path is None
            or positives_path is None
            or negatives_path is None
            or unsure_path is None
            or user is None
        ):
            raise ValueError
        controller = Controller(
            target_references=target_references,
            predictions_path=predictions_path,
            positives_path=positives_path,
            negatives_path=negatives_path,
            unsure_path=unsure_path,
            user=user,
            converter=converter,
        )
    if not controller._predictions and predictions_path is not None:
        raise RuntimeError(f"There are no predictions to curate in {predictions_path}")
    app.config["controller"] = controller
    flask_bootstrap.Bootstrap4(app)
    app.register_blueprint(blueprint)

    if not resolver_base:
        resolver_base = DEFAULT_RESOLVER_BASE

    app.jinja_env.globals.update(
        controller=controller,
        url_for_state=url_for_state,
        resolver_base=resolver_base,
        title=title,
        footer=footer,
    )
    return app
