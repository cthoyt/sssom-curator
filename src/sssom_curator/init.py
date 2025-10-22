"""Initialize repositories."""

from pathlib import Path
from textwrap import dedent

from .constants import (
    NEGATIVES_NAME,
    POSITIVES_NAME,
    PREDICTIONS_NAME,
    STUB_SSSOM_COLUMNS,
    UNSURE_NAME,
)

__all__ = [
    "initialize_folder",
    "initialize_package",
]


def initialize_folder(
    directory: str | Path,
    purl_base: str,
    positive_name: str = POSITIVES_NAME,
    unsure_name: str = UNSURE_NAME,
    predictions_name: str = PREDICTIONS_NAME,
    negatives_name: str = NEGATIVES_NAME,
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
    directory = Path(directory).expanduser().resolve()
    purl_base = purl_base.rstrip("/")
    for name in [positive_name, negatives_name, unsure_name, predictions_name]:
        path = directory.joinpath(name)
        if path.exists():
            raise FileExistsError
        with path.open("w") as file:
            # TODO add prefixes? depends on strategy
            print(f"#mapping_set_id: {purl_base}/{path.name}", file=file)
            print(*STUB_SSSOM_COLUMNS, sep="\t", file=file)

    python_template = dedent(f"""\
        # /// script
        # requires-python = ">=3.10"
        # dependencies = [
        #     "sssom-curator[web,predict-lexical,exports]",
        # ]
        # ///

        \"\"\"Hello somthing something\"\"\"

        from sssom_curator import Repository
        from pathlib import Path

        HERE = Path(__file__).parent.resolve()

        repository = Repository(
            positives_path=HERE.joinpath("{positive_name}"),
            negatives_path=HERE.joinpath("{negatives_name}"),
            predictions_path=HERE.joinpath("{predictions_name}"),
            unsure_path=HERE.joinpath("{unsure_name}"),
        )
    """)
    python_path = directory.joinpath("main.py")
    python_path.write_text(python_template)

    readme_template = dedent("""\
        # SSSOM Curator

        Run the curator with:

        ```console
        $ uv run main.py web
        ```

        Predict new mappings, e.g., between Medical Subject Headings (MeSH)
        and the Medical Actions Ontology (MaxO) with:

        ```console
        $ uv run main.py predict mesh maxo
        ```

        ## Colophon

        This repository was generated using SSSOM-Curator.
    """)
    readme_path = directory.joinpath("README.md")
    readme_path.write_text(readme_template)


def initialize_package(directory: Path) -> None:
    """Initialize a package."""
    raise NotImplementedError
