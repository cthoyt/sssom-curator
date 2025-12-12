"""Web curation interface for :mod:`biomappings`."""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import TYPE_CHECKING, Literal, TypeAlias

import flask
import flask_bootstrap

from .blueprint import blueprint, url_for_state
from .components import AbstractController, Controller, State
from .database import DatabaseController
from ..constants import DEFAULT_RESOLVER_BASE, ensure_converter
from ..repository import Repository

if TYPE_CHECKING:
    from curies import Converter, Reference

__all__ = [
    "get_app",
]

Implementation: TypeAlias = Literal["dict", "sqlite"]


def get_app(
    *,
    target_references: Iterable[Reference] | None = None,
    repository: Repository | None = None,
    controller: AbstractController | None = None,
    user: Reference | None = None,
    resolver_base: str | None = None,
    title: str | None = None,
    footer: str | None = None,
    converter: Converter | None = None,
    eager_persist: bool = True,
    implementation: Implementation | None = None,
) -> flask.Flask:
    """Get a curation flask app."""
    app = flask.Flask(__name__)
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = os.urandom(8)
    app.config["SHOW_RELATIONS"] = True
    app.config["EAGER_PERSIST"] = eager_persist
    if controller is None:
        if repository is None:
            raise ValueError
        impls = {"dict": Controller, "sqlite": DatabaseController}
        impl_cls = impls[implementation] if implementation else Controller
        converter = ensure_converter(converter)
        controller = impl_cls(
            target_references=target_references,
            repository=repository,
            converter=converter,
        )
        if not controller.count_predictions(State()):
            raise ValueError("There are no predictions to curate")

    app.config["controller"] = controller
    app.config["get_current_user_reference"] = lambda: user
    flask_bootstrap.Bootstrap5(app)
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
