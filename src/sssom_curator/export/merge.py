"""Export Biomappings as SSSOM."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
import curies
from sssom_pydantic import MappingSet

if TYPE_CHECKING:
    import pandas as pd
    from sssom import MappingSetDataFrame

    from ..repository import Repository

__all__ = [
    "merge",
]

columns = [
    "subject_id",
    "subject_label",
    "predicate_id",
    "predicate_modifier",
    "object_id",
    "object_label",
    "mapping_justification",
    "author_id",
    "confidence",
    "mapping_tool",
]


def _sssom_dump(mapping_set: MappingSet) -> dict[str, Any]:
    metadata = mapping_set.model_dump(exclude_none=True, exclude_unset=True)
    # fix dumping
    metadata["creator_id"] = [
        creator["prefix"] + ":" + creator["identifier"] for creator in metadata["creator_id"]
    ]
    return metadata


def merge(repository: Repository, directory: Path) -> None:
    """Merge the SSSOM files together and output to a directory."""
    if repository.mapping_set is None:
        raise ValueError

    import yaml
    from sssom.writers import write_json, write_owl

    converter, df, msdf = get_merged_sssom(repository)

    tsv_meta = {**_sssom_dump(repository.mapping_set), "curie_map": converter.bimap}

    if repository.basename:
        fname = repository.basename
    elif repository.mapping_set.mapping_set_title is not None:
        fname = repository.mapping_set.mapping_set_title.lower().replace(" ", "-")
    else:
        raise ValueError("basename or mapping set title must be se")

    stub = directory.joinpath(fname)
    tsv_path = stub.with_suffix(".sssom.tsv")
    json_path = stub.with_suffix(".sssom.json")
    owl_path = stub.with_suffix(".sssom.owl")
    metadata_path = stub.with_suffix(".sssom.yml")

    with tsv_path.open("w") as file:
        for line in yaml.safe_dump(tsv_meta).splitlines():
            print(f"# {line}", file=file)
        df.to_csv(file, sep="\t", index=False)

    with open(metadata_path, "w") as file:
        yaml.safe_dump(tsv_meta, file)

    if not repository.purl_base:
        click.secho(
            "can not output JSON nor OWL because ``purl_base`` was not defined", fg="yellow"
        )
    else:
        _base = repository.purl_base.rstrip("/")
        click.echo("Writing JSON")
        with json_path.open("w") as file:
            msdf.metadata["mapping_set_id"] = f"{_base}/{fname}.sssom.json"
            write_json(msdf, file)
        click.echo("Writing OWL")
        with owl_path.open("w") as file:
            msdf.metadata["mapping_set_id"] = f"{_base}/{fname}.sssom.owl"
            write_owl(msdf, file)


def get_merged_sssom(
    repository: Repository, *, use_tqdm: bool = False, converter: curies.Converter | None = None
) -> tuple[curies.Converter, pd.DataFrame, MappingSetDataFrame]:
    """Get an SSSOM dataframe."""
    if repository.mapping_set is None:
        raise ValueError

    import pandas as pd
    from curies.utils import _prefix_from_curie
    from tqdm.auto import tqdm

    from ..constants import ensure_converter

    converter = ensure_converter(converter, preferred=True)
    prefixes: set[str] = {"semapv"}

    # NEW WAY: load all DFs, concat them, reorder columns

    a = pd.read_csv(repository.positives_path, sep="\t", comment="#")
    b = pd.read_csv(repository.negatives_path, sep="\t", comment="#")
    c = pd.read_csv(repository.predictions_path, sep="\t", comment="#")
    df = pd.concat([a, b, c])
    df = df[columns]

    for column in ["subject_id", "object_id", "predicate_id"]:
        converter.pd_standardize_curie(df, column=column, strict=True)

    for _, mapping in tqdm(
        df.iterrows(), desc="tabulating prefixes & authors", disable=not use_tqdm
    ):
        prefixes.add(_prefix_from_curie(mapping["subject_id"]))
        prefixes.add(_prefix_from_curie(mapping["predicate_id"]))
        prefixes.add(_prefix_from_curie(mapping["object_id"]))
        author_id = mapping["author_id"]
        if pd.notna(author_id) and any(author_id.startswith(x) for x in ["orcid:", "wikidata:"]):
            prefixes.add(_prefix_from_curie(author_id))
        # TODO add justification:

    converter = converter.get_subconverter(prefixes)

    from sssom.constants import DEFAULT_VALIDATION_TYPES
    from sssom.parsers import from_sssom_dataframe
    from sssom.validators import validate

    try:
        msdf = from_sssom_dataframe(
            df, prefix_map=converter, meta=_sssom_dump(repository.mapping_set)
        )
    except Exception as e:
        click.secho(f"SSSOM Export failed...\n{e}", fg="red")
        raise

    results = validate(msdf=msdf, validation_types=DEFAULT_VALIDATION_TYPES, fail_on_error=False)
    for validator_type, validation_report in results.items():
        if validation_report.results:
            click.secho(f"SSSOM Validator Failed: {validator_type}", fg="red")
            for result in validation_report.results:
                click.secho(f"- {result}", fg="red")
            click.echo("")

    return converter, df, msdf
