"""Components."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any, Literal

import curies
import flask
import sssom_pydantic
from curies import NamableReference, Reference
from curies.vocabulary import broad_match, exact_match, manual_mapping_curation, narrow_match
from flask import current_app
from flask_wtf import FlaskForm
from pydantic import BaseModel, Field
from sssom_pydantic import SemanticMapping
from wtforms import StringField, SubmitField

from .utils import Mark
from ..constants import ensure_converter, insert
from ..repository import Repository

__all__ = [
    "Controller",
    "MappingForm",
    "State",
]


class State(BaseModel):
    """Contains the state for queries to the curation app."""

    limit: int | None = Field(10, description="If given, only iterate this number of predictions.")
    offset: int | None = Field(0, description="If given, offset the iteration by this number")
    query: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing as a substring "
        "in one of the source or target fields.",
    )
    source_query: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing as a substring "
        "in one of the source fields.",
    )
    source_prefix: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing in the "
        "source prefix field",
    )
    target_query: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing as a substring "
        "in one of the target fields.",
    )
    target_prefix: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing in the "
        "target prefix field",
    )
    # TODO rename, since this is about mapping tool
    provenance: str | None = Field(
        None, description="If given, filters to provenance values matching this"
    )
    prefix: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing as a "
        "substring in one of the prefixes.",
    )
    sort: Literal["asc", "desc", "subject", "object"] | None = Field(
        None,
        description="If `desc`, sorts in descending confidence order. If `asc`, sorts in "
        "increasing confidence order. Otherwise, do not sort.",
    )
    same_text: bool | None = Field(
        None, description="If true, filter to predictions with the same label"
    )
    show_relations: bool = True
    show_lines: bool = False

    @classmethod
    def from_flask_globals(cls) -> State:
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


class Controller:
    """A module for interacting with the predictions and mappings."""

    _user: Reference
    _predictions: list[SemanticMapping]
    converter: curies.Converter

    def __init__(
        self,
        *,
        target_references: Iterable[Reference] | None = None,
        repository: Repository,
        user: Reference,
        converter: curies.Converter | None = None,
    ) -> None:
        """Instantiate the web controller.

        :param target_references: References that are the
            target of curation. If this is given, pre-filters will be made before on
            predictions to only show ones where either the source or target appears in
            this set
        """
        self.repository = repository
        self._predictions, _, self._predictions_metadata = sssom_pydantic.read(
            self.repository.predictions_path
        )

        self._marked: dict[int, Mark] = {}
        self.total_curated = 0
        self._added_mappings: list[SemanticMapping] = []
        self.target_references = set(target_references or [])
        self.converter = ensure_converter(converter)

        self._current_author = user

    def _get_current_author(self) -> Reference:
        return self._current_author

    def get_predictions(self, state: State) -> Iterable[tuple[int, SemanticMapping]]:
        """Iterate over pairs of positions and predicted semantic mappings."""
        it = self._help_it_predictions(state)
        if state.offset is not None:
            try:
                for _ in range(state.offset):
                    next(it)
            except StopIteration:
                # if next() fails, then there are no remaining entries.
                # do not pass go, do not collect 200 euro $
                return
        if state.limit is None:
            yield from it
        else:
            for line_prediction, _ in zip(it, range(state.limit), strict=False):
                yield line_prediction

    def count_predictions_from_state(self, state: State) -> int:
        """Count the number of predictions to check for the given filters."""
        return self.count_predictions(state)

    def count_predictions(self, state: State) -> int:
        """Count the number of predictions to check for the given filters."""
        it = self._help_it_predictions(state)
        return sum(1 for _ in it)

    def _help_it_predictions(self, state: State) -> Iterator[tuple[int, SemanticMapping]]:  # noqa:C901
        mappings: Iterable[tuple[int, SemanticMapping]] = enumerate(self._predictions)
        if self.target_references:
            mappings = (
                (line, mapping)
                for (line, mapping) in mappings
                if mapping.subject in self.target_references
                or mapping.object in self.target_references
            )

        if state.query is not None:
            mappings = self._help_filter(
                state.query,
                mappings,
                lambda mapping: [
                    mapping.subject.curie,
                    mapping.subject_name,
                    mapping.object.curie,
                    mapping.object_name,
                    mapping.mapping_tool_name,
                ],
            )
        if state.source_prefix is not None:
            mappings = self._help_filter(
                state.source_prefix, mappings, lambda mapping: [mapping.subject.curie]
            )
        if state.source_query is not None:
            mappings = self._help_filter(
                state.source_query,
                mappings,
                lambda mapping: [mapping.subject.curie, mapping.subject_name],
            )
        if state.target_query is not None:
            mappings = self._help_filter(
                state.target_query,
                mappings,
                lambda mapping: [mapping.object.curie, mapping.object_name],
            )
        if state.target_prefix is not None:
            mappings = self._help_filter(
                state.target_prefix, mappings, lambda mapping: [mapping.object.curie]
            )
        if state.prefix is not None:
            mappings = self._help_filter(
                state.prefix,
                mappings,
                lambda mapping: [mapping.subject.curie, mapping.object.curie],
            )
        if state.provenance is not None:
            mappings = self._help_filter(
                state.provenance,
                mappings,
                lambda mapping: [mapping.mapping_tool_name],
            )

        def _get_confidence(t: tuple[int, SemanticMapping]) -> float:
            return t[1].confidence or 0.0

        if state.sort is not None:
            if state.sort == "desc":
                mappings = iter(sorted(mappings, key=_get_confidence, reverse=True))
            elif state.sort == "asc":
                mappings = iter(sorted(mappings, key=_get_confidence, reverse=False))
            elif state.sort == "subject":
                mappings = iter(sorted(mappings, key=lambda l_p: l_p[1].subject.curie))
            elif state.sort == "object":
                mappings = iter(sorted(mappings, key=lambda l_p: l_p[1].object.curie))
            else:
                raise ValueError(f"unknown sort type: {state.sort}")

        if state.same_text:
            mappings = (
                (line, mapping)
                for line, mapping in mappings
                if mapping.subject_name
                and mapping.object_name
                and mapping.subject_name.casefold() == mapping.object_name.casefold()
                and mapping.predicate.curie == "skos:exactMatch"
            )

        rv = ((line, mapping) for line, mapping in mappings if line not in self._marked)
        return rv

    @staticmethod
    def _help_filter(
        query: str,
        mappings: Iterable[tuple[int, SemanticMapping]],
        func: Callable[[SemanticMapping], list[str | None]],
    ) -> Iterable[tuple[int, SemanticMapping]]:
        query = query.casefold()
        for line, mapping in mappings:
            if any(query in element.casefold() for element in func(mapping) if element):
                yield line, mapping

    @property
    def total_predictions(self) -> int:
        """Return the total number of yet unmarked predictions."""
        return len(self._predictions) - len(self._marked)

    def mark(self, line: int, value: Mark) -> None:
        """Mark the given mapping as correct.

        :param line: Position of the prediction
        :param value: Value to mark the prediction with

        :raises ValueError: if an invalid value is used
        """
        if line > len(self._predictions):
            raise IndexError(
                f"given line {line} is larger than the number of "
                f"predictions {len(self._predictions):,}"
            )
        if line not in self._marked:
            self.total_curated += 1
        self._marked[line] = value

    def add_mapping(
        self,
        subject: Reference,
        obj: Reference,
    ) -> None:
        """Add manually curated new mappings."""
        self._added_mappings.append(
            SemanticMapping.model_validate(
                {
                    "subject": subject,
                    "predicate": exact_match,
                    "object": obj,
                    "authors": [self._get_current_author()],
                    "justification": manual_mapping_curation,
                }
            )
        )
        self.total_curated += 1

    def _insert(self, mappings: Iterable[SemanticMapping], path: Path) -> None:
        insert(path=path, converter=self.converter, include_mappings=mappings)

    def persist(self) -> None:  # noqa:C901
        """Save the current markings to the source files."""
        if not self._marked:
            # no need to persist if there are no marks
            return None

        entries: defaultdict[Literal["correct", "incorrect", "unsure"], list[SemanticMapping]] = (
            defaultdict(list)
        )

        for line, value in sorted(self._marked.items(), reverse=True):
            try:
                mapping = self._predictions.pop(line)
            except IndexError:
                raise IndexError(
                    f"you tried popping the {line} element from the predictions list, "
                    f"which only has {len(self._predictions):,} elements"
                ) from None

            update: dict[str, Any] = {
                "authors": [self._get_current_author()],
                "justification": manual_mapping_curation,
                # throw the following fields away, since it's been manually curated now
                "confidence": None,
                "mapping_tool": None,
            }

            entry_key: Literal["correct", "incorrect", "unsure"]
            # note these go backwards because of the way they are read
            if value == "broad":
                entry_key = "correct"
                update["predicate"] = narrow_match
            elif value == "narrow":
                entry_key = "correct"
                update["predicate"] = broad_match
            elif value == "incorrect":
                entry_key = "incorrect"
                update["predicate_modifier"] = "Not"
            elif value == "correct":
                entry_key = "correct"
            elif value == "unsure":
                entry_key = "unsure"
            else:
                raise NotImplementedError

            # replace some values using model_copy since the model is frozen
            new_mapping = mapping.model_copy(update=update)

            entries[entry_key].append(new_mapping)

        # no need to standardize since we assume everything was correct on load.
        # only write files that have some values to go in them!
        if entries["correct"]:
            self._insert(entries["correct"], path=self.repository.positives_path)
        if entries["incorrect"]:
            self._insert(entries["incorrect"], path=self.repository.negatives_path)
        if entries["unsure"]:
            self._insert(entries["unsure"], path=self.repository.unsure_path)

        sssom_pydantic.write(
            self._predictions,
            self.repository.predictions_path,
            metadata=self._predictions_metadata,
            converter=self.converter,
            drop_duplicates=True,
            sort=True,
        )
        self._marked.clear()

        # Now add manually curated mappings, if there are any
        if self._added_mappings:
            self._insert(self._added_mappings, path=self.repository.positives_path)
            self._added_mappings = []

        return None


class MappingForm(FlaskForm):  # type:ignore[misc]
    """Form for entering new mappings."""

    # TODO how to get types for flask-wtf

    source_prefix = StringField("Source Prefix", id="source_prefix")
    source_id = StringField("Source ID", id="source_id")
    source_name = StringField("Source Name", id="source_name")
    target_prefix = StringField("Target Prefix", id="target_prefix")
    target_id = StringField("Target ID", id="target_id")
    target_name = StringField("Target Name", id="target_name")
    submit = SubmitField("Add")

    def get_subject(self, converter: curies.Converter) -> NamableReference:
        """Get the subject."""
        return NamableReference.model_validate(
            {
                "prefix": self.data["source_prefix"],
                "identifier": self.data["source_id"],
                "name": self.data["source_name"],
            },
            context=converter,
        )

    def get_object(self, converter: curies.Converter) -> NamableReference:
        """Get the object."""
        return NamableReference.model_validate(
            {
                "prefix": self.data["target_prefix"],
                "identifier": self.data["target_id"],
                "name": self.data["target_name"],
            },
            context=converter,
        )
