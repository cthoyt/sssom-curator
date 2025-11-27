"""Blueprint."""

from __future__ import annotations

import getpass
from typing import Any, cast

import flask
import werkzeug
from curies import Reference
from flask import current_app
from werkzeug.local import LocalProxy

from .components import Controller, State, get_pagination_elements
from .utils import commit, get_branch, normalize_mark, not_main, push

__all__ = [
    "blueprint",
    "url_for_state",
]


def get_state_from_flask() -> State:
    """Get the state from the flask current request."""
    return State(
        limit=flask.request.args.get("limit", type=int, default=10),
        offset=flask.request.args.get("offset", type=int, default=0),
        query=flask.request.args.get("query"),
        source_query=flask.request.args.get("source_query"),
        source_prefix=flask.request.args.get("source_prefix"),
        target_query=flask.request.args.get("target_query"),
        target_prefix=flask.request.args.get("target_prefix"),
        provenance=flask.request.args.get("provenance"),
        prefix=flask.request.args.get("prefix"),
        sort=flask.request.args.get("sort"),
        same_text=_get_bool_arg("same_text"),
        show_relations=_get_bool_arg("show_relations") or current_app.config["SHOW_RELATIONS"],
    )


def _get_bool_arg(name: str) -> bool | None:
    value: str | None = flask.request.args.get(name, type=str)
    if value is not None:
        return value.lower() in {"true", "t"}
    return None


def url_for_state(endpoint: str, state: State, **kwargs: Any) -> str:
    """Get the URL for an endpoint based on the state class."""
    vv = state.model_dump(exclude_none=True, exclude_defaults=True)
    vv.update(kwargs)  # make sure stuff explicitly set overrides state
    return flask.url_for(endpoint, **vv)


controller: Controller = cast(Controller, LocalProxy(lambda: current_app.config["controller"]))
blueprint = flask.Blueprint("ui", __name__)


@blueprint.route("/")
def home() -> str:
    """Serve the home page."""
    state = get_state_from_flask()
    predictions = controller.iterate_predictions(state)
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
            source_prefix,
            target_prefix,
            count,
            url_for_state(
                ".home",
                state.model_copy(
                    update={"source_prefix": source_prefix, "target_prefix": target_prefix}
                ),
            ),
        )
        for (source_prefix, target_prefix), count in counter.most_common()
    ]
    return flask.render_template("summary.html", state=state, rows=rows)


@blueprint.route("/commit")
def run_commit() -> werkzeug.Response:
    """Make a commit then redirect to the home page."""
    label = "mappings" if controller.total_curated > 1 else "mapping"
    message = f"Curated {controller.total_curated} {label} ({getpass.getuser()})"
    commit_info = commit(message)
    current_app.logger.warning("git commit res: %s", commit_info)
    if not_main():
        branch = get_branch()
        push_output = push(branch_name=branch)
        current_app.logger.warning("git push res: %s", push_output)
    else:
        flask.flash("did not push because on master branch")
        current_app.logger.warning("did not push because on master branch")
    controller.total_curated = 0
    return _go_home()


@blueprint.route("/mark/<curie>/<value>")
def mark(curie: str, value: str) -> werkzeug.Response:
    """Mark the given line as correct or not."""
    reference = Reference.from_curie(curie)
    controller.mark(reference, normalize_mark(value))
    return _go_home()


def _go_home() -> werkzeug.Response:
    state = get_state_from_flask()
    return flask.redirect(url_for_state(".home", state))
