"""Initialize repositories."""

from pathlib import Path

from sssom_pydantic import MappingSet

from ..constants import (
    NEGATIVES_NAME,
    POSITIVES_NAME,
    PREDICTIONS_NAME,
    STUB_SSSOM_COLUMNS,
    UNSURE_NAME,
    sssom_mapping_set_model_dump,
)

__all__ = [
    "initialize_folder",
    "initialize_package",
]

HERE = Path(__file__).parent.resolve()
MAPPING_SET_FILE_NAME = "mapping_set.json"


def initialize_folder(
    directory: str | Path,
    *,
    positive_name: str = POSITIVES_NAME,
    unsure_name: str = UNSURE_NAME,
    predictions_name: str = PREDICTIONS_NAME,
    negatives_name: str = NEGATIVES_NAME,
    mapping_set_filename: str = MAPPING_SET_FILE_NAME,
    mapping_set: MappingSet | None = None,
    script_name: str = "main.py",
    readme_name: str = "README.md",
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
    import yaml
    from jinja2 import Environment, FileSystemLoader

    directory = Path(directory).expanduser().resolve()
    for name in [positive_name, negatives_name, unsure_name, predictions_name]:
        path = directory.joinpath(name)
        if path.exists():
            raise FileExistsError
        with path.open("w") as file:
            if mapping_set is not None:
                for line in yaml.safe_dump(sssom_mapping_set_model_dump(mapping_set)).splitlines():
                    print(line, file=file)
            print(*STUB_SSSOM_COLUMNS, sep="\t", file=file)

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
    )
    script_path = directory.joinpath(script_name)
    script_path.write_text(script_text)

    readme_template = environment.get_template("README.md.jinja2")
    readme_text = readme_template.render()
    readme_path = directory.joinpath(readme_name)
    readme_path.write_text(readme_text)


def initialize_package(directory: Path) -> None:
    """Initialize a package."""
    raise NotImplementedError
