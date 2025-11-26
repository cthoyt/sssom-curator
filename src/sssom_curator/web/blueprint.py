"""Blueprint."""

from __future__ import annotations

import getpass
from collections import Counter
from copy import deepcopy
from typing import Any, cast

import flask
import pydantic
import werkzeug
from flask import current_app
from werkzeug.local import LocalProxy

from .components import Controller, MappingForm, State
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
        show_lines=_get_bool_arg("show_lines") or current_app.config["SHOW_LINES"],
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


CONTROLLER: Controller = cast(Controller, LocalProxy(lambda: current_app.config["controller"]))
blueprint = flask.Blueprint("ui", __name__)


@blueprint.route("/")
def home() -> str:
    """Serve the home page."""
    form = MappingForm()
    state = get_state_from_flask()
    predictions = CONTROLLER.iterate_predictions(state)
    remaining_rows = CONTROLLER.count_predictions(state)
    return flask.render_template(
        "home.html",
        predictions=predictions,
        form=form,
        state=state,
        remaining_rows=remaining_rows,
    )


@blueprint.route("/summary")
def summary() -> str:
    """Serve the summary page."""
    state = get_state_from_flask()
    state.limit = None
    predictions = CONTROLLER.iterate_predictions(state)
    counter = Counter((mapping.subject.prefix, mapping.object.prefix) for _, mapping in predictions)
    rows = []
    for (source_prefix, target_prefix), count in counter.most_common():
        row_state = deepcopy(state)
        row_state.source_prefix = source_prefix
        row_state.target_prefix = target_prefix
        rows.append((source_prefix, target_prefix, count, url_for_state(".home", row_state)))

    return flask.render_template(
        "summary.html",
        state=state,
        rows=rows,
    )


@blueprint.route("/add_mapping", methods=["POST"])
def add_mapping() -> werkzeug.Response:
    """Add a new mapping manually."""
    form = MappingForm()
    if form.is_submitted():
        try:
            subject = form.get_subject(CONTROLLER.converter)
        except pydantic.ValidationError as e:
            flask.flash(f"Problem with source CURIE {e}", category="warning")
            return _go_home()

        try:
            obj = form.get_object(CONTROLLER.converter)
        except pydantic.ValidationError as e:
            flask.flash(f"Problem with source CURIE {e}", category="warning")
            return _go_home()

        CONTROLLER.add_mapping(subject, obj)
        CONTROLLER.persist()
    else:
        flask.flash("missing form data", category="warning")
    return _go_home()


@blueprint.route("/commit")
def run_commit() -> werkzeug.Response:
    """Make a commit then redirect to the home page."""
    commit_info = commit(
        f"Curated {CONTROLLER.total_curated} mapping"
        f"{'s' if CONTROLLER.total_curated > 1 else ''}"
        f" ({getpass.getuser()})",
    )
    current_app.logger.warning("git commit res: %s", commit_info)
    if not_main():
        branch = get_branch()
        push_output = push(branch_name=branch)
        current_app.logger.warning("git push res: %s", push_output)
    else:
        flask.flash("did not push because on master branch")
        current_app.logger.warning("did not push because on master branch")
    CONTROLLER.total_curated = 0
    return _go_home()


@blueprint.route("/mark/<int:line>/<value>")
def mark(line: int, value: str) -> werkzeug.Response:
    """Mark the given line as correct or not."""
    CONTROLLER.mark(line, normalize_mark(value))
    CONTROLLER.persist()
    return _go_home()


def _go_home() -> werkzeug.Response:
    state = get_state_from_flask()
    return flask.redirect(url_for_state(".home", state))
