"""Export Biomappings as SSSOM."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click
import curies
import sssom_pydantic
from sssom_pydantic import MappingSet, Metadata, SemanticMapping

if TYPE_CHECKING:
    from sssom import MappingSetDataFrame

    from ..repository import Repository

__all__ = [
    "merge",
]


def _sssom_dump(mapping_set: MappingSet) -> Metadata:
    return mapping_set.to_record().model_dump(exclude_none=True, exclude_unset=True)


def merge(
    repository: Repository,
    directory: Path,
    *,
    output_owl: bool = True,
    output_json: bool = True,
    sssompy_validate: bool = True,
) -> None:
    """Merge the SSSOM files together and output to a directory."""
    if repository.mapping_set is None:
        raise ValueError

    import yaml
    from sssom.writers import write_json, write_owl

    mappings, converter, msdf = _get_merged_sssom(repository, sssompy_validate=sssompy_validate)

    tsv_meta = {**_sssom_dump(repository.mapping_set), "curie_map": converter.bimap}

    if repository.basename:
        fname = repository.basename
    elif repository.mapping_set.title is not None:
        fname = repository.mapping_set.title.lower().replace(" ", "-")
    else:
        raise ValueError("basename or mapping set title must be se")

    stub = directory.joinpath(fname)
    tsv_path = stub.with_suffix(".sssom.tsv")
    json_path = stub.with_suffix(".sssom.json")
    owl_path = stub.with_suffix(".sssom.owl")
    metadata_path = stub.with_suffix(".sssom.yml")

    sssom_pydantic.write(
        mappings, path=tsv_path, converter=converter, metadata=repository.mapping_set
    )

    with open(metadata_path, "w") as file:
        yaml.safe_dump(tsv_meta, file)

    if output_owl or output_json:
        if not repository.purl_base:
            click.secho(
                "can not output JSON nor OWL because ``purl_base`` was not defined", fg="yellow"
            )
        else:
            _base = repository.purl_base.rstrip("/")
            if output_json:
                click.echo("Writing JSON")
                with json_path.open("w") as file:
                    msdf.metadata["mapping_set_id"] = f"{_base}/{fname}.sssom.json"
                    write_json(msdf, file)
            if output_owl:
                click.echo("Writing OWL")
                with owl_path.open("w") as file:
                    msdf.metadata["mapping_set_id"] = f"{_base}/{fname}.sssom.owl"
                    write_owl(msdf, file)


def _get_merged_sssom(
    repository: Repository,
    *,
    sssompy_validate: bool = True,
) -> tuple[list[SemanticMapping], curies.Converter, MappingSetDataFrame]:
    """Get an SSSOM dataframe."""
    if repository.mapping_set is None:
        raise ValueError

    from sssom_pydantic.contrib.sssompy import mappings_to_msdf

    from ..constants import ensure_converter

    converter = curies.chain(
        [
            ensure_converter(preferred=True),
            repository.get_converter(),
        ]
    )
    mappings: list[SemanticMapping] = [
        *repository.read_positive_mappings(),
        *repository.read_negative_mappings(),
        *repository.read_predicted_mappings(),
    ]
    mappings = [mapping.standardize(converter) for mapping in mappings]

    # this is also built-in to sssom-pydantic writing,
    # but needs to be done or the sssom-py code gets
    # confused
    prefixes = {p for m in mappings for p in m.get_prefixes()}
    converter = converter.get_subconverter(prefixes)

    try:
        msdf = mappings_to_msdf(
            mappings, converter=converter, metadata=repository.mapping_set, linkml_validate=False
        )
    except Exception as e:
        click.secho(f"SSSOM Export failed...\n{e}", fg="red")
        raise

    if sssompy_validate:
        import sssom.validators

        results = sssom.validators.validate(msdf=msdf, fail_on_error=False)
        for validator_type, validation_report in results.items():
            if validation_report.results:
                click.secho(f"SSSOM Validator Failed: {validator_type}", fg="red")
                for result in validation_report.results:
                    click.secho(f"- {result}", fg="red")
                click.echo("")

    return mappings, converter, msdf
