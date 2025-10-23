"""Initialize repositories."""

from pathlib import Path

import curies
import sssom_pydantic
from curies.vocabulary import charlie, lexical_matching_process, manual_mapping_curation
from sssom_pydantic import MappingSet, SemanticMapping

from sssom_curator import Repository
from sssom_curator.constants import NEGATIVES_NAME, POSITIVES_NAME, PREDICTIONS_NAME, UNSURE_NAME

__all__ = [
    "initialize_folder",
    "initialize_package",
]

HERE = Path(__file__).parent.resolve()
MAPPING_SET_FILE_NAME = "sssom-curator.json"
SCRIPT_NAME = "main.py"
README_NAME = "README.md"
CC0_CURIE = "spdx:CC0-1.0"
SKIPS = {
    "extension_definitions",
    "creator_label",
    "publication_date",
    "sssom_version",
    "issue_tracker",
    "other",
}


def initialize_folder(
    directory: str | Path,
    *,
    positive_mappings_filename: str = POSITIVES_NAME,
    unsure_mappings_filename: str = UNSURE_NAME,
    predicted_mappings_filename: str = PREDICTIONS_NAME,
    negative_mappings_filename: str = NEGATIVES_NAME,
    repository_filename: str = MAPPING_SET_FILE_NAME,
    mapping_set: MappingSet | None = None,
    base_purl: str | None = None,
    script_filename: str = SCRIPT_NAME,
    readme_filename: str = README_NAME,
    add_license: bool = True,
    mapping_set_id: str | None = None,
) -> None:
    """Create a curation repository in a folder.

    :param directory: The directory where to create it.

    Creates the following:

    1. Four curation files, each loaded up with Bioregistry (preferred) prefixes
       according to the selected strategy
    2. A python script, loaded with `PEP 723 <https://peps.python.org/pep-0723/>`_
       inline metadata, a pre-instantiated Repository object, and more
    3. A README.md file with explanation about how the code was generated, how to use
       it, etc.
    """
    if mapping_set is None and mapping_set_id is None:
        raise ValueError("either a mapping set or a mapping set ID should be given")

    from jinja2 import Environment, FileSystemLoader

    converter = curies.Converter.from_prefix_map(
        {
            "ex": "https://example.org/",
            "skos": "http://www.w3.org/2004/02/skos/core#",
        }
    )

    name_to_example = {
        positive_mappings_filename: SemanticMapping(
            subject=curies.NamedReference(prefix="ex", identifier="1", name="1"),
            predicate=curies.Reference(prefix="skos", identifier="exactMatch"),
            object=curies.NamedReference(prefix="ex", identifier="2", name="2"),
            justification=manual_mapping_curation,
            authors=[charlie],
        ),
        negative_mappings_filename: SemanticMapping(
            subject=curies.NamedReference(prefix="ex", identifier="3", name="3"),
            predicate=curies.Reference(prefix="skos", identifier="exactMatch"),
            object=curies.NamedReference(prefix="ex", identifier="4", name="4"),
            justification=manual_mapping_curation,
            authors=[charlie],
        ),
        unsure_mappings_filename: SemanticMapping(
            subject=curies.NamedReference(prefix="ex", identifier="5", name="5"),
            predicate=curies.Reference(prefix="skos", identifier="exactMatch"),
            object=curies.NamedReference(prefix="ex", identifier="6", name="6"),
            justification=manual_mapping_curation,
            authors=[charlie],
        ),
        predicted_mappings_filename: SemanticMapping(
            subject=curies.NamedReference(prefix="ex", identifier="7", name="7"),
            predicate=curies.Reference(prefix="skos", identifier="exactMatch"),
            object=curies.NamedReference(prefix="ex", identifier="8", name="8"),
            justification=lexical_matching_process,
        ),
    }

    if base_purl:
        internal_base_purl = base_purl.rstrip("/")
    else:
        internal_base_purl = "https://example.org/mapping-set"
    directory = Path(directory).expanduser().resolve()
    for name, mapping in name_to_example.items():
        path = directory.joinpath(name)
        if path.exists():
            raise FileExistsError(f"{path} already exists. cowardly refusing to overwrite.")

        metadata = MappingSet(mapping_set_id=f"{internal_base_purl}/{name}")
        sssom_pydantic.write([mapping], path, metadata=metadata, converter=converter)

    environment = Environment(
        autoescape=True, loader=FileSystemLoader(HERE), trim_blocks=True, lstrip_blocks=True
    )

    if mapping_set is None:
        mapping_set = MappingSet(
            mapping_set_id=mapping_set_id,
            mapping_set_version="1",
        )

    if mapping_set.license is None and add_license:
        mapping_set = mapping_set.model_copy(update={"license": CC0_CURIE})

    repository = Repository(
        positives_path=positive_mappings_filename,
        negatives_path=negative_mappings_filename,
        predictions_path=predicted_mappings_filename,
        unsure_path=unsure_mappings_filename,
        mapping_set=mapping_set,
    )
    repository_path = directory.joinpath(repository_filename)
    repository_path.write_text(repository.model_dump_json(indent=2, exclude=SKIPS) + "\n")

    if mapping_set is not None and mapping_set.mapping_set_title:
        comment = f"SSSOM Curator for {mapping_set.mapping_set_title}"
    else:
        comment = "SSSOM Curator"

    script_template = environment.get_template("main.py.jinja2")
    script_text = script_template.render(
        comment=comment,
        repository_filename=repository_filename,
    )
    script_path = directory.joinpath(script_filename)
    script_path.write_text(script_text + "\n")

    readme_template = environment.get_template("README.md.jinja2")
    readme_text = readme_template.render(mapping_set=mapping_set, cco_curie=CC0_CURIE)
    readme_path = directory.joinpath(readme_filename)
    readme_path.write_text(readme_text + "\n")

    if mapping_set.license == CC0_CURIE:
        license_path = directory.joinpath("LICENSE")
        license_path.write_text(HERE.joinpath("cc0.txt").read_text())


def initialize_package(directory: Path) -> None:
    """Initialize a package."""
    raise NotImplementedError


if __name__ == "__main__":
    x = HERE.parent.parent.parent.resolve().joinpath("example")
    if x.is_dir():
        for p in x.glob("*"):
            p.unlink()
        x.rmdir()
    x.mkdir(exist_ok=True)
    initialize_folder(
        x,
        mapping_set=MappingSet(
            mapping_set_id="https://example.org/test.tsv", mapping_set_title="Test"
        ),
    )
