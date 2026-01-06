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
    live_login: bool = False,
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
        import pystow
        from flask_dance.contrib.orcid import make_orcid_blueprint
        from flask_dance.contrib.orcid import orcid as orcid_session

        client_id = pystow.get_config("conferret", "orcid_client_id", raise_on_missing=True)
        client_secret = pystow.get_config("conferret", "orcid_client_secret", raise_on_missing=True)

        # see https://info.orcid.org/documentation/integration-guide/getting-started-with-your-orcid-integration/
        auth_blueprint = make_orcid_blueprint(
            client_id=client_id,
            client_secret=client_secret,
            scope="/authenticate",
        )
        app.register_blueprint(auth_blueprint, url_prefix="/login")

        @app.before_request
        def require_login() -> None | werkzeug.Response:
            """Intercept requests to require login."""
            # Allow the login routes themselves
            if request.endpoint and request.endpoint.startswith(f"{auth_blueprint.name}."):
                return None

            # Allow static files
            if request.endpoint == "static":
                return None

            if not orcid_session.authorized:
                return redirect(url_for(f"{auth_blueprint.name}.login"))

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
