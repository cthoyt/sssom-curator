"""Blueprint."""

from __future__ import annotations

from typing import Any, cast

import flask
import werkzeug
from curies import Reference
from flask import current_app
from sssom_pydantic.process import MARKS, Mark
from werkzeug.local import LocalProxy

from .components import (
    AbstractController,
    PersistRemoteFailure,
    PersistRemoteSuccess,
    State,
    get_pagination_elements,
)

__all__ = [
    "blueprint",
    "url_for_state",
]


def get_state_from_flask() -> State:
    """Get the state from the flask current request."""
    request_dict: dict[str, Any] = flask.request.args.to_dict()
    if same_text := request_dict.get("same_text"):
        request_dict["same_text"] = same_text.lower() in {"true", "t"}
    if show_relations := request_dict.get("show_relations"):
        request_dict["show_relations"] = show_relations.lower() in {"true", "t"}
    else:
        request_dict["show_relations"] = current_app.config["SHOW_RELATIONS"]
    return State.model_validate(request_dict)


def _get_bool_arg(name: str) -> bool | None:
    value: str | None = flask.request.args.get(name, type=str)
    if value is not None:
        return value.lower() in {"true", "t"}
    return None


def url_for_state(endpoint: str, state: State, **kwargs: Any) -> str:
    """Get the URL for an endpoint based on the state class."""
    vv = state.model_dump(exclude_none=True, exclude_defaults=True, exclude_unset=True)
    vv.update(kwargs)  # make sure stuff explicitly set overrides state
    return flask.url_for(endpoint, **vv)


controller: AbstractController = cast(
    AbstractController, LocalProxy(lambda: current_app.config["controller"])
)
current_user_reference = cast(
    Reference, LocalProxy(lambda: current_app.config["get_current_user_reference"]())
)

blueprint = flask.Blueprint("ui", __name__)


@blueprint.route("/")
def home() -> str:
    """Serve the home page."""
    state = get_state_from_flask()
    predictions = controller.get_predictions(state)
    n_predictions = controller.count_predictions(state)
    return flask.render_template(
        "home.html",
        predictions=predictions,
        state=state,
        n_predictions=n_predictions,
        pagination_elements=get_pagination_elements(state, n_predictions),
    )


@blueprint.route("/summary")
def summary() -> str:
    """Serve the summary page."""
    state = get_state_from_flask()
    state.limit = None
    counter = controller.get_prefix_counter(state)
    rows = [
        (
            subject_prefix,
            object_prefix,
            count,
            url_for_state(
                ".home",
                state.model_copy(
                    update={"subject_prefix": subject_prefix, "object_prefix": object_prefix}
                ),
            ),
        )
        for (subject_prefix, object_prefix), count in counter.most_common()
    ]
    return flask.render_template("summary.html", state=state, rows=rows)


@blueprint.route("/commit")
def run_commit() -> werkzeug.Response:
    """Make a commit then redirect to the home page."""
    controller.persist()
    match controller.persist_remote(current_user_reference):
        case PersistRemoteSuccess(message):
            current_app.logger.info(message)
        case PersistRemoteFailure(_step, failure_text):
            flask.flash(failure_text)
            current_app.logger.warning(failure_text)
    return _go_home()


@blueprint.route("/mark/<curie>/<value>")
def mark(curie: str, value: Mark) -> werkzeug.Response:
    """Mark the given line as correct or not."""
    reference = Reference.from_curie(curie)
    if value not in MARKS:
        raise flask.abort(400)
    controller.mark(reference, value, authors=current_user_reference)
    if current_app.config["EAGER_PERSIST"]:
        controller.persist()
    return _go_home()


def _go_home() -> werkzeug.Response:
    state = get_state_from_flask()
    return flask.redirect(url_for_state(".home", state))
