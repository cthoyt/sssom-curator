"""SSSOM Curator web application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypeAlias

if TYPE_CHECKING:
    from collections.abc import Iterable

    import flask
    from curies import Converter, Reference

    from .backends import Controller
    from ..repository import Repository

__all__ = [
    "get_app",
]

#: Keys for different implementation types
Implementation: TypeAlias = Literal["dict", "sqlite"]


def get_app(
    *,
    target_references: Iterable[Reference] | None = None,
    repository: Repository | None = None,
    controller: Controller | None = None,
    user: Reference | None = None,
    resolver_base: str | None = None,
    title: str | None = None,
    footer: str | None = None,
    converter: Converter | None = None,
    eager_persist: bool = True,
    implementation: Implementation | None = None,
) -> flask.Flask:
    """Get a curation flask app."""
    import os

    import flask
    import flask_bootstrap

    from .blueprint import blueprint, url_for_state
    from ..constants import DEFAULT_RESOLVER_BASE, ensure_converter

    app = flask.Flask(__name__)
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = os.urandom(8)
    app.config["SHOW_RELATIONS"] = True
    app.config["EAGER_PERSIST"] = eager_persist
    if controller is None:
        if repository is None:
            raise ValueError

        match implementation:
            case "dict" | None:
                from .backends.memory import DictController

                controller = DictController(
                    target_references=target_references,
                    repository=repository,
                    converter=ensure_converter(converter),
                )
            case "sqlite":
                from .backends.database import DatabaseController

                controller = DatabaseController(
                    target_references=target_references,
                    repository=repository,
                    converter=ensure_converter(converter),
                    populate=True,
                )

    if not controller.count_predictions():
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
