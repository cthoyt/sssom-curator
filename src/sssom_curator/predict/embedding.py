"""Embedding-based mapping prediction."""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from typing import TYPE_CHECKING, Unpack

import curies
import pystow
from curies import ReferenceTuple
from curies.vocabulary import exact_match, lexical_similarity_threshold_based_matching_process
from pyobo.constants import GetOntologyKwargs
from sssom_pydantic import MappingTool, SemanticMapping
from tqdm.asyncio import tqdm

from .utils import resolve_mapping_tool

if TYPE_CHECKING:
    import pandas as pd
    import sentence_transformers
    from bioregistry import NormalizedNamableReference

__all__ = [
    "predict_embedding_mappings",
]

#: The default similarity cutoff
DEFAULT_CUTOFF = 0.65

#: The default batch size
DEFAULT_BATCH_SIZE = 10_000


def predict_embedding_mappings(
    prefix: str,
    target_prefixes: str | Iterable[str],
    *,
    mapping_tool: str | MappingTool | None = None,
    relation: str | curies.NamableReference | None = None,
    cutoff: float | None = None,
    batch_size: int | None = None,
    versions: dict[str, str] | None = None,
    model: str | sentence_transformers.SentenceTransformer | None = None,
    **kwargs: Unpack[GetOntologyKwargs],
) -> list[SemanticMapping]:
    """Predict semantic mappings with text embedding-based cosine similarity.

    :param prefix: The prefix for the source
    :param target_prefixes: The prefix for one or more target resources
    :param mapping_tool: The mapping tool annotation. If not given, adds
        the default SSSOM Curator annotation
    :param relation: The mapping predicate to use. Defaults to ``skos:exactMatch``
    :param cutoff: The similarity cutoff, i.e., predictions with similarity under
        this value are discarded. Defaults to :data:`DEFAULT_CUTOFF`
    :param batch_size: The batch size for predictions, defaults to :data:`DEFAULT_BATCH_SIZE`.
        This is needed to decide how many calculations are done with the GPU at a time
    :param versions: Explicit versions to be passed
    :param model: The sentence transformer model to use
    :param kwargs: Keyword arguments for getting the ontology

    :return: A list of semantic mapping objects
    """
    import pyobo

    from ..constants import CC0_URL

    if relation is None:
        relation = curies.NamableReference.from_reference(exact_match.without_name())
    elif isinstance(relation, str):
        relation = curies.NamableReference.from_curie(relation)

    if versions is None:
        versions = {}

    if isinstance(target_prefixes, str):
        targets = [target_prefixes]
    else:
        targets = list(target_prefixes)
    if cutoff is None:
        cutoff = DEFAULT_CUTOFF
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE

    model = pystow.get_sentence_transformer(model)
    # TODO what about injecting versions in here?
    source_df = pyobo.get_text_embeddings_df(prefix, model=model, **kwargs)

    mapping_tool = resolve_mapping_tool(mapping_tool)

    predictions = []
    today = datetime.date.today()
    for target in tqdm(targets, disable=len(targets) == 1):
        target_df = pyobo.get_text_embeddings_df(target, model=model, **kwargs)
        for source_id, target_id, similarity in _calculate_similarities(
            source_df, target_df, batch_size, cutoff, progress=kwargs.get("progress", True)
        ):
            predictions.append(
                SemanticMapping(
                    subject=_r(prefix=prefix, identifier=source_id),
                    subject_source_version=versions.get(prefix),
                    predicate=relation,
                    object=_r(prefix=target, identifier=target_id),
                    object_source_version=versions.get(target),
                    justification=lexical_similarity_threshold_based_matching_process,
                    # TODO change from `confidence` to `similarity_score`,
                    #  see (https://w3id.org/sssom/similarity_score)
                    confidence=similarity,
                    mapping_tool=mapping_tool,
                    mapping_date=today,
                    license=CC0_URL,
                )
            )
    return predictions


def _calculate_similarities(
    source_df: pd.DataFrame,
    target_df: pd.DataFrame,
    batch_size: int | None,
    cutoff: float,
    progress: bool = True,
) -> list[tuple[str, str, float]]:
    if batch_size is not None:
        return _calculate_similarities_batched(
            source_df, target_df, batch_size=batch_size, cutoff=cutoff, progress=progress
        )
    else:
        return _calculate_similarities_unbatched(source_df, target_df, cutoff=cutoff)


def _calculate_similarities_batched(
    source_df: pd.DataFrame,
    target_df: pd.DataFrame,
    *,
    batch_size: int,
    cutoff: float,
    progress: bool = True,
) -> list[tuple[str, str, float]]:
    import torch
    from sentence_transformers.util import cos_sim

    similarities = []
    source_df_numpy = source_df.to_numpy()
    for target_start in tqdm(
        range(0, len(target_df), batch_size), unit="target batch", disable=not progress
    ):
        target_end = target_start + batch_size
        target_batch_df = target_df.iloc[target_start:target_end]
        similarity = cos_sim(
            source_df_numpy,
            target_batch_df.to_numpy(),
        )
        source_target_pairs = torch.nonzero(similarity >= cutoff, as_tuple=False)
        for source_idx, target_idx in source_target_pairs:
            source_id: str = source_df.index[source_idx.item()]
            target_id: str = target_batch_df.index[target_idx.item()]
            similarities.append(
                (
                    source_id,
                    target_id,
                    similarity[source_idx, target_idx].item(),
                )
            )
    return similarities


def _calculate_similarities_unbatched(
    source_df: pd.DataFrame, target_df: pd.DataFrame, *, cutoff: float
) -> list[tuple[str, str, float]]:
    import torch
    from sentence_transformers.util import cos_sim

    similarities = []
    similarity = cos_sim(source_df.to_numpy(), target_df.to_numpy())
    source_target_pairs = torch.nonzero(similarity >= cutoff, as_tuple=False)
    for source_idx, target_idx in source_target_pairs:
        source_id: str = source_df.index[source_idx.item()]
        target_id: str = target_df.index[target_idx.item()]
        similarities.append(
            (
                source_id,
                target_id,
                similarity[source_idx, target_idx].item(),
            )
        )
    return similarities


def _r(prefix: str, identifier: str) -> NormalizedNamableReference:
    import bioregistry
    import pyobo

    return bioregistry.NormalizedNamableReference(
        prefix=prefix,
        identifier=identifier,
        name=pyobo.get_name(ReferenceTuple(prefix, identifier)),
    )
