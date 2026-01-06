"""SSSOM Curator web application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypeAlias

if TYPE_CHECKING:
    from collections.abc import Iterable

    import flask
    import werkzeug
    from curies import Converter, Reference

    from .backends import Controller
    from ..repository import Repository

__all__ = [
    "get_app",
]

#: Keys for different implementation types
Implementation: TypeAlias = Literal["dict", "sqlite"]


def get_app(  # noqa:C901
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
    # Used for live login with ORCiD
    live_login: bool = False,
    orcid_client_id: str | None = None,
    orcid_client_secret: str | None = None,
) -> flask.Flask:
    """Get a curation flask app."""
    import os

    import flask
    import flask_bootstrap
    from curies import NamableReference
    from flask import redirect, request, url_for

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

    if live_login and user:
        raise NotImplementedError("can't specify a user and have login")
    elif live_login:
        from flask_dance.contrib.orcid import make_orcid_blueprint
        from flask_dance.contrib.orcid import orcid as orcid_session

        if not orcid_client_id or not orcid_client_secret:
            raise ValueError("orcid_client_id and orcid_client_secret are required for live login")

        # see https://info.orcid.org/documentation/integration-guide/getting-started-with-your-orcid-integration/
        orcid_blueprint = make_orcid_blueprint(
            client_id=orcid_client_id,
            client_secret=orcid_client_secret,
            scope="/authenticate",
        )
        app.register_blueprint(orcid_blueprint, url_prefix="/login")

        @app.before_request
        def require_login() -> None | werkzeug.Response:
            """Intercept requests to require login."""
            # Allow the login routes themselves
            if request.endpoint and request.endpoint.startswith(f"{orcid_blueprint.name}."):
                return None

            # Allow static files
            if request.endpoint == "static":
                return None

            if not orcid_session.authorized:
                return redirect(url_for(f"{orcid_blueprint.name}.login"))

            return None

        app.config["get_current_user_reference"] = lambda: NamableReference(
            prefix="orcid",
            identifier=orcid_session.token["orcid"],
            name=orcid_session.token.get("name"),
        )

    elif user:
        app.config["get_current_user_reference"] = lambda: user
    else:
        raise NotImplementedError("you must either pass a user or turn on live login")

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
