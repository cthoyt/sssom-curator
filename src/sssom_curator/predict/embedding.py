"""Embedding-based mapping prediction."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

import curies
from curies.vocabulary import lexical_matching_process
from sssom_pydantic import MappingTool, SemanticMapping
from tqdm.asyncio import tqdm

from .utils import resolve_mapping_tool

if TYPE_CHECKING:
    import pandas as pd
    from bioregistry import NormalizedNamableReference

__all__ = [
    "predict_embedding_mappings",
]


def predict_embedding_mappings(
    prefix: str,
    target_prefixes: str | Iterable[str],
    mapping_tool: str | MappingTool,
    *,
    relation: str | None | curies.NamableReference = None,
    cutoff: float | None = None,
    batch_size: int | None = None,
    progress: bool = True,
    force: bool = False,
    force_process: bool = False,
) -> list[SemanticMapping]:
    """Predict semantic mappings with embeddings."""
    import pyobo.api.embedding

    if isinstance(target_prefixes, str):
        targets = [target_prefixes]
    else:
        targets = list(target_prefixes)
    if cutoff is None:
        cutoff = 0.65
    if batch_size is None:
        batch_size = 10_000

    model = pyobo.api.embedding.get_text_embedding_model()
    source_df = pyobo.get_text_embeddings_df(
        prefix, model=model, force=force, force_process=force_process
    )

    mapping_tool = resolve_mapping_tool(mapping_tool)

    predictions = []
    for target in tqdm(targets, disable=len(targets) == 1):
        target_df = pyobo.get_text_embeddings_df(
            target, model=model, force=force, force_process=force_process
        )
        for source_id, target_id, confidence in _calculate_similarities(
            source_df, target_df, batch_size, cutoff, progress=progress
        ):
            predictions.append(
                SemanticMapping(
                    subject=_r(prefix=prefix, identifier=source_id),
                    predicate=relation,
                    object=_r(prefix=target, identifier=target_id),
                    justification=lexical_matching_process,
                    confidence=confidence,
                    mapping_tool=mapping_tool,
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
        prefix=prefix, identifier=identifier, name=pyobo.get_name(prefix, identifier)
    )
