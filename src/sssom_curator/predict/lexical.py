"""Utilities for generating predictions with lexical predictions."""

from __future__ import annotations

import itertools as itt
import logging
import typing
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias, cast

import click
import curies
import ssslm
import sssom_pydantic
from bioregistry import NormalizedNamedReference
from curies.vocabulary import lexical_matching_process
from more_click import verbose_option
from sssom_pydantic import MappingTool, SemanticMapping
from tqdm.auto import tqdm

from .embedding import predict_embedding_mappings
from .utils import TOOL_NAME, resolve_mapping_tool, resolve_predicate
from ..constants import PredictionMethod, RecognitionMethod

if TYPE_CHECKING:
    import gilda
    import networkx as nx

__all__ = [
    "TOOL_NAME",
    "append_lexical_predictions",
    "append_predictions",
    "filter_custom",
    "filter_existing_xrefs",
    "get_predictions",
    "lexical_prediction_cli",
    "predict_embedding_mappings",
    "predict_lexical_mappings",
]

logger = logging.getLogger(__name__)

#: A filter 3-dictionary of source prefix to target prefix to source identifier to target identifier
NestedMappingDict: TypeAlias = Mapping[str, Mapping[str, Mapping[str, str]]]

#: A callable that gets matches
MatchCallable: TypeAlias = Callable[[str], list[ssslm.Match]]


def get_predictions(
    prefix: str,
    target_prefixes: str | Iterable[str],
    *,
    relation: str | None | curies.NamableReference = None,
    identifiers_are_names: bool = False,
    method: PredictionMethod | None = None,
    cutoff: float | None = None,
    batch_size: int | None = None,
    custom_filter_function: Callable[[SemanticMapping], bool] | None = None,
    progress: bool = True,
    filter_mutual_mappings: bool = False,
    mapping_tool: str | MappingTool | None = None,
    force: bool = False,
    cache: bool = True,
    force_process: bool = False,
    all_by_all: bool = False,
) -> list[SemanticMapping]:
    """Add lexical matching-based predictions to the Biomappings predictions.tsv file.

    :param prefix: The source prefix
    :param target_prefixes: The target prefix or prefixes
    :param mapping_tool: The name of the mapping tool. Defaults to :data:``
    :param relation: The relationship. Defaults to ``skos:exactMatch``.
    :param identifiers_are_names: The source prefix's identifiers should be considered
        as names
    :param method: The lexical predication method to use
    :param cutoff: an optional minimum prediction confidence cutoff
    :param batch_size: The batch size for embeddings
    :param custom_filter_function: A custom function that decides if semantic mappings
        should be kept, applied after all other logic.
    :param progress: Should progress be shown?
    :param filter_mutual_mappings: Should mappings between entities in the given
        namespaces be filtered out?
    :param force: Should the ontologies be re-downloaded/processed?
    :param force_process: Should the ontologies be re-processed? Subsumed by ``force``
    :param cache: Should the results of processing the resources be cached?
    :param all_by_all: Enable all-by-all prediction mode, which doesn't just check
        between the given prefix and target_prefixes (1-n) but does all against all

    :returns: A list of predicted semantic mappings
    """
    if isinstance(target_prefixes, str):
        targets = [target_prefixes]
    else:
        targets = list(target_prefixes)

    mapping_tool = resolve_mapping_tool(mapping_tool)

    if method is None or method in typing.get_args(RecognitionMethod):
        import pyobo

        if all_by_all:
            grounder = pyobo.get_grounder(
                [prefix, *targets],
                raise_on_missing=False,
                force=force,
                force_process=force_process,
                cache=cache,
            )
            predictions = _predict_lexical_mappings_all_by_all(
                grounder,
                predicate=relation,
                mapping_tool=mapping_tool,
                method=cast(RecognitionMethod | None, method),
            )
        else:
            # by default, PyOBO wraps a gilda grounder, but
            # can be configured to use other NER/NEN systems
            grounder = pyobo.get_grounder(
                targets,
                raise_on_missing=False,
                force=force,
                force_process=force_process,
                cache=cache,
            )
            predictions = predict_lexical_mappings(
                prefix,
                predicate=relation,
                grounder=grounder,
                mapping_tool=mapping_tool,
                identifiers_are_names=identifiers_are_names,
                method=cast(RecognitionMethod | None, method),
            )
    elif method == "embedding":
        if all_by_all:
            raise NotImplementedError(
                "all-by-all prediction not implemented for embedding workflow"
            )
        predictions = predict_embedding_mappings(
            prefix,
            target_prefixes,
            mapping_tool=mapping_tool,
            relation=relation,
            cutoff=cutoff,
            batch_size=batch_size,
            progress=progress,
        )
    else:
        raise ValueError(f"invalid lexical prediction method: {method}")

    if filter_mutual_mappings:
        mutual_mapping_filter = _get_mutual_mapping_filter(prefix, target_prefixes)
        predictions = filter_custom(predictions, mutual_mapping_filter)

    predictions = filter_existing_xrefs(predictions, [prefix, *targets])

    if custom_filter_function:
        predictions = list(filter(custom_filter_function, predictions))

    predictions = sorted(predictions)
    return predictions


def _get_get_matches(method: RecognitionMethod | None, grounder: ssslm.Grounder) -> MatchCallable:
    if method is None or method == "grounding":
        return grounder.get_matches
    elif method == "ner":

        def _get_matches(s: str) -> list[ssslm.Match]:
            return [a.match for a in grounder.annotate(s)]

        return _get_matches

    else:
        raise ValueError(f"invalid lexical method: {method}")


def _predict_lexical_mappings_all_by_all(
    grounder: ssslm.Grounder,
    *,
    predicate: str | curies.Reference | None = None,
    method: RecognitionMethod | None = None,
    mapping_tool: str | MappingTool | None = None,
) -> Iterable[SemanticMapping]:
    """Iterate over predictions."""
    predicate = resolve_predicate(predicate)
    mapping_tool = resolve_mapping_tool(mapping_tool)
    if method not in {None, "grounding"}:
        raise NotImplementedError(f"all-by-all requires grounding method, {method} not allowed")
    if not isinstance(grounder, ssslm.GildaGrounder):
        raise NotImplementedError(f"all-by-all requires gilda grounder. got: {type(grounder)}")
    yield from _all_by_all_gilda(grounder._grounder, predicate, mapping_tool)


def _all_by_all_gilda(
    grounder: gilda.Grounder, predicate: curies.Reference, mapping_tool: MappingTool | None = None
) -> Iterable[SemanticMapping]:
    from gilda.scorer import generate_match
    from gilda.scorer import score as get_score

    for values in grounder.entries.values():
        for s, o in itt.combinations(values, 2):
            if s.db == o.db:
                continue
            match = generate_match(s.text, o.text)
            score = get_score(match, o)  # FIXME not symmetric
            yield SemanticMapping(
                subject=NormalizedNamedReference(prefix=s.db, identifier=s.id, name=s.entry_name),
                predicate=predicate,
                object=NormalizedNamedReference(prefix=o.db, identifier=o.id, name=o.entry_name),
                justification=lexical_matching_process,
                confidence=round(score, 3),
                mapping_tool=mapping_tool,
            )


def predict_lexical_mappings(
    prefix: str,
    *,
    predicate: str | curies.Reference | None = None,
    grounder: ssslm.Grounder,
    identifiers_are_names: bool = False,
    strict: bool = False,
    method: RecognitionMethod | None = None,
    mapping_tool: str | MappingTool | None = None,
) -> Iterable[SemanticMapping]:
    """Iterate over prediction tuples for a given prefix."""
    import pyobo

    id_name_mapping = pyobo.get_id_name_mapping(prefix, strict=strict)
    it = tqdm(
        id_name_mapping.items(), desc=f"[{prefix}] lexical tuples", unit_scale=True, unit="name"
    )

    predicate = resolve_predicate(predicate)
    get_matches = _get_get_matches(method, grounder)
    mapping_tool = resolve_mapping_tool(mapping_tool)

    name_prediction_count = 0
    for identifier, name in it:
        for scored_match in get_matches(name):
            name_prediction_count += 1
            yield SemanticMapping(
                subject=NormalizedNamedReference(prefix=prefix, identifier=identifier, name=name),
                predicate=predicate,
                object=scored_match.reference,
                justification=lexical_matching_process,
                confidence=round(scored_match.score, 3),
                mapping_tool=mapping_tool,
            )

    tqdm.write(f"[{prefix}] generated {name_prediction_count:,} predictions from names")

    if identifiers_are_names:
        it = tqdm(
            pyobo.get_ids(prefix), desc=f"[{prefix}] lexical tuples", unit_scale=True, unit="id"
        )
        identifier_prediction_count = 0
        for identifier in it:
            for scored_match in get_matches(identifier):
                name_prediction_count += 1
                yield SemanticMapping(
                    subject=NormalizedNamedReference(
                        prefix=prefix, identifier=identifier, name=identifier
                    ),
                    predicate=predicate,
                    object=scored_match.reference,
                    justification=lexical_matching_process,
                    confidence=round(scored_match.score, 3),
                    mapping_tool=mapping_tool,
                )
        tqdm.write(
            f"[{prefix}] generated {identifier_prediction_count:,} predictions from identifiers"
        )


def filter_custom(
    mappings: Iterable[SemanticMapping],
    custom_filter: NestedMappingDict,
) -> Iterable[SemanticMapping]:
    """Filter out custom mappings."""
    counter = 0
    for mapping in mappings:
        if (
            custom_filter.get(mapping.subject.prefix, {})
            .get(mapping.object.prefix, {})
            .get(mapping.subject.identifier)
        ):
            counter += 1
            continue
        yield mapping
    logger.info("filtered out %d custom mapped matches", counter)


def filter_existing_xrefs(
    mappings: Iterable[SemanticMapping], prefixes: Iterable[str]
) -> Iterable[SemanticMapping]:
    """Filter predictions that match xrefs already loaded through PyOBO.

    :param mappings: Semantic mappings to filter
    :param prefixes: Prefixes for resources to check for existing mappings

    :yields: Filtered semantic mappings
    """
    entity_to_mapped_prefixes = _get_entity_to_mapped_prefixes(prefixes)

    n_predictions = 0
    for mapping in tqdm(mappings, desc="filtering predictions", leave=False):
        if (
            mapping.subject in entity_to_mapped_prefixes
            and mapping.object.prefix in entity_to_mapped_prefixes[mapping.subject]
        ) or (
            mapping.object in entity_to_mapped_prefixes
            and mapping.subject.prefix in entity_to_mapped_prefixes[mapping.object]
        ):
            n_predictions += 1
            continue
        yield mapping

    if n_predictions:
        tqdm.write(f"filtered out {n_predictions:,} pre-mapped matches")


def _get_entity_to_mapped_prefixes(prefixes: Iterable[str]) -> dict[curies.Reference, set[str]]:
    import pyobo

    entity_to_mapped_prefixes: defaultdict[curies.Reference, set[str]] = defaultdict(set)
    for prefix in prefixes:
        for mapping in pyobo.get_semantic_mappings(prefix):
            entity_to_mapped_prefixes[mapping.subject].add(mapping.object.prefix)
            entity_to_mapped_prefixes[mapping.object].add(mapping.subject.prefix)
    return dict(entity_to_mapped_prefixes)


def _get_mutual_mapping_filter(prefix: str, targets: str | Iterable[str]) -> NestedMappingDict:
    """Get a custom filter dictionary.

    This is induced over the mutual mapping graph with all target prefixes.

    :param prefix: The source prefix
    :param targets: All potential target prefixes

    :returns: A filter 3-dictionary of source prefix to target prefix to source
        identifier to target identifier
    """
    try:
        import networkx as nx
    except ImportError as e:
        raise ImportError(
            "NetworkX is required for mapping filtering, install with pip install networkx"
        ) from e

    if isinstance(targets, str):
        targets = [targets]
    graph = _mutual_mapping_graph([prefix, *targets])
    rv: defaultdict[str, dict[str, str]] = defaultdict(dict)
    for node in graph:
        if node.prefix != prefix:
            continue
        for xref_prefix, xref_identifier in nx.single_source_shortest_path(graph, node):
            rv[xref_prefix][node.identifier] = xref_identifier
    return {prefix: dict(rv)}


def _mutual_mapping_graph(prefixes: Iterable[str]) -> nx.Graph:
    """Get the undirected mapping graph between the given prefixes.

    :param prefixes: A list of prefixes to use with :func:`pyobo.get_filtered_xrefs` to
        get xrefs.

    :returns: The undirected mapping graph containing mappings between entries in the
        given namespaces.
    """
    import networkx as nx
    import pyobo

    prefixes = set(prefixes)
    graph = nx.Graph()
    for prefix in sorted(prefixes):
        for mapping in pyobo.get_semantic_mappings(prefix):
            if mapping.object.prefix not in prefixes:
                continue
            graph.add_edge(mapping.subject, mapping.object)
    return graph


def _upgrade_set(values: Iterable[str] | None = None) -> set[str]:
    return set() if values is None else set(values)


def append_predictions(
    new_mappings: Iterable[SemanticMapping],
    *,
    path: Path,
    curated_paths: list[Path] | None = None,
    converter: curies.Converter | None = None,
) -> None:
    """Append new lines to the predictions table."""
    mappings, converter, metadata = sssom_pydantic.read(path, converter=converter)

    prefixes: set[str] = set()
    for mapping in new_mappings:
        prefixes.update(mapping.get_prefixes())
        mappings.append(mapping)

    prefixes_to_add = {prefix for prefix in prefixes if not converter.standardize_prefix(prefix)}
    if prefixes_to_add:
        try:
            import bioregistry
        except ImportError as e:
            raise ImportError("amending prefixes requires the bioregistry to be installed") from e

        for prefix in prefixes_to_add:
            resource = bioregistry.get_resource(prefix)
            if resource is None:
                raise ValueError(
                    f"can not automatically extend because {prefix} is not registered in the "
                    f"bioregistry.\n\nSolution: add a CURIE prefix-URI prefix mapping manually "
                    f"to the file {path}"
                )

            uri_prefix = resource.get_rdf_uri_prefix() or resource.get_uri_prefix()
            if not uri_prefix:
                raise ValueError(
                    f"can not automatically extend because {prefix} does not have a valid URI "
                    f"prefix in the bioregistry.\n\nSolution: add a CURIE prefix-URI prefix "
                    f"mapping manually to the file {path}"
                )
            converter.add_prefix(
                resource.prefix,
                uri_prefix,
            )

    if curated_paths is not None:
        exclude_mappings = itt.chain.from_iterable(
            sssom_pydantic.read(path)[0] for path in curated_paths
        )
    else:
        exclude_mappings = None

    sssom_pydantic.write(
        mappings,
        path,
        metadata=metadata,
        converter=converter,
        drop_duplicates=True,
        sort=True,
        exclude_mappings=exclude_mappings,
    )


def append_lexical_predictions(
    prefix: str,
    target_prefixes: str | Iterable[str],
    *,
    relation: str | None | curies.NamableReference = None,
    identifiers_are_names: bool = False,
    path: Path,
    method: PredictionMethod | None = None,
    cutoff: float | None = None,
    batch_size: int | None = None,
    custom_filter_function: Callable[[SemanticMapping], bool] | None = None,
    progress: bool = True,
    filter_mutual_mappings: bool = False,
    curated_paths: list[Path] | None = None,
    mapping_tool: str | MappingTool | None = None,
    force: bool = False,
    force_process: bool = False,
    cache: bool = True,
    converter: curies.Converter | None = None,
    all_by_all: bool = False,
) -> None:
    """Add lexical matching-based predictions to the Biomappings predictions.tsv file.

    :param prefix: The source prefix
    :param target_prefixes: The target prefix or prefixes
    :param relation: The relationship. Defaults to ``skos:exactMatch``.
    :param identifiers_are_names: The source prefix's identifiers should be considered
        as names
    :param path: A custom path to predictions TSV file
    :param method: The lexical predication method to use
    :param cutoff: an optional minimum prediction confidence cutoff
    :param batch_size: The batch size for embeddings
    :param custom_filter_function: A custom function that decides if semantic mappings
        should be kept, applied after all other logic.
    :param progress: Should progress be shown?
    :param filter_mutual_mappings: Should mappings between entities in the given
        namespaces be filtered out?
    :param mapping_tool: The name of the mapping tool
    :param curated_paths: The paths to curated documents that are used to remove zombie
        mappings (i.e., predictions that were already curated)
    """
    predictions = get_predictions(
        prefix,
        target_prefixes,
        mapping_tool=mapping_tool,
        relation=relation,
        identifiers_are_names=identifiers_are_names,
        method=method,
        cutoff=cutoff,
        batch_size=batch_size,
        custom_filter_function=custom_filter_function,
        progress=progress,
        filter_mutual_mappings=filter_mutual_mappings,
        force=force,
        force_process=force_process,
        cache=cache,
        all_by_all=all_by_all,
    )
    tqdm.write(f"[{prefix}] generated {len(predictions):,} predictions")

    # since the function that constructs the predictions already
    # pre-standardizes, we don't have to worry about standardizing again
    append_predictions(predictions, path=path, curated_paths=curated_paths, converter=converter)


def lexical_prediction_cli(
    prefix: str,
    target: str | list[str],
    *,
    path: Path,
    curated_paths: list[Path] | None = None,
    filter_mutual_mappings: bool = False,
    identifiers_are_names: bool = False,
    predicate: str | None | curies.NamableReference = None,
    method: PredictionMethod | None = None,
    cutoff: float | None = None,
    custom_filter_function: Callable[[SemanticMapping], bool] | None = None,
    mapping_tool: str | MappingTool | None = None,
) -> None:
    """Construct a CLI and run it."""
    tt = target if isinstance(target, str) else ", ".join(target)

    @click.command(help=f"Generate mappings from {prefix} to {tt}")
    @click.option("--force", is_flag=True)
    @verbose_option
    def main(force: bool) -> None:
        """Generate mappings."""
        append_lexical_predictions(
            prefix,
            target,
            path=path,
            curated_paths=curated_paths,
            filter_mutual_mappings=filter_mutual_mappings,
            identifiers_are_names=identifiers_are_names,
            relation=predicate,
            method=method,
            cutoff=cutoff,
            custom_filter_function=custom_filter_function,
            mapping_tool=mapping_tool,
            force=force,
        )

    main()
