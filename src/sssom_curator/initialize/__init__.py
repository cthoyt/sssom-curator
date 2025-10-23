"""Initialize repositories."""

from pathlib import Path

import curies
import sssom_pydantic
from curies.vocabulary import charlie, manual_mapping_curation
from sssom_pydantic import MappingSet, SemanticMapping

from ..constants import NEGATIVES_NAME, POSITIVES_NAME, PREDICTIONS_NAME, UNSURE_NAME

__all__ = [
    "initialize_folder",
    "initialize_package",
]

HERE = Path(__file__).parent.resolve()
MAPPING_SET_FILE_NAME = "mapping_set.json"
SCRIPT_NAME = "main.py"
README_NAME = "README.md"


def initialize_folder(
    directory: str | Path,
    *,
    positive_name: str = POSITIVES_NAME,
    unsure_name: str = UNSURE_NAME,
    predictions_name: str = PREDICTIONS_NAME,
    negatives_name: str = NEGATIVES_NAME,
    mapping_set_filename: str = MAPPING_SET_FILE_NAME,
    mapping_set: MappingSet | None = None,
    base_purl: str | None = None,
    script_name: str = SCRIPT_NAME,
    readme_name: str = README_NAME,
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
    from jinja2 import Environment, FileSystemLoader

    converter = curies.Converter.from_prefix_map(
        {
            "ex": "https://example.org/",
            "skos": "http://www.w3.org/2004/02/skos/core#",
        }
    )

    base_example = SemanticMapping(
        subject=curies.NamedReference(prefix="ex", identifier="1", name="1"),
        predicate=curies.Reference(prefix="skos", identifier="exactMatch"),
        object=curies.NamedReference(prefix="ex", identifier="2", name="2"),
        justification=manual_mapping_curation,
        authors=[charlie],
    )
    name_to_example = {
        positive_name: base_example,
        negatives_name: base_example,
        unsure_name: base_example,
        predictions_name: base_example,
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

    if mapping_set is not None:
        mapping_set_path = directory.joinpath(mapping_set_filename)
        mapping_set_path.write_text(
            mapping_set.model_dump_json(exclude_none=True, exclude_unset=True)
        )
    else:
        mapping_set_path = None

    if mapping_set is not None and mapping_set.mapping_set_title:
        comment = f"SSSOM Curator for {mapping_set.mapping_set_title}"
    else:
        comment = "SSSOM Curator"

    script_template = environment.get_template("main.py.jinja2")
    script_text = script_template.render(
        comment=comment,
        mapping_set=mapping_set,
        mapping_set_path=mapping_set_path,
        positive_name=positive_name,
        negatives_name=negatives_name,
        unsure_name=unsure_name,
        predictions_name=predictions_name,
        base_purl=base_purl,
    )
    script_path = directory.joinpath(script_name)
    script_path.write_text(script_text + "\n")

    readme_template = environment.get_template("README.md.jinja2")
    readme_text = readme_template.render()
    readme_path = directory.joinpath(readme_name)
    readme_path.write_text(readme_text + "\n")


def initialize_package(directory: Path) -> None:
    """Initialize a package."""
    raise NotImplementedError
