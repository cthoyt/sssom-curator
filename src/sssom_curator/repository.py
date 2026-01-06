"""Repository."""

from __future__ import annotations

import sys
import typing
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, TypeAlias

import click
import curies
import sssom_pydantic
from pydantic import BaseModel, Field
from sssom_pydantic.process import Call
from typing_extensions import Self

from .constants import (
    DEFAULT_RESOLVER_BASE,
    NEGATIVES_NAME,
    POSITIVES_NAME,
    PREDICTIONS_NAME,
    UNSURE_NAME,
    PredictionMethod,
    ensure_converter,
    insert,
)

if TYPE_CHECKING:
    import curies
    from curies import Converter
    from sssom_pydantic import MappingTool, SemanticMapping, SemanticMappingPredicate

    from .testing import IntegrityTestCase

__all__ = [
    "OrcidNameGetter",
    "Repository",
    "UserGetter",
    "add_commands",
]

#: A function that returns the current user
UserGetter: TypeAlias = Callable[[], "curies.Reference"]

#: A function that returns a dictionary from ORCID to name
OrcidNameGetter: TypeAlias = Callable[[], dict[str, str]]

#: How to decide what converter to use
ConverterStrategy: TypeAlias = Literal["bioregistry", "bioregistry-preferred", "passthrough"]

#: Configuration file
CONFIGURATION_FILENAME = "sssom-curator.json"

strategy_option = click.option(
    "--strategy",
    type=click.Choice(list(typing.get_args(ConverterStrategy))),
    default="passthrough",
    show_default=True,
)


class Repository(BaseModel):
    """A data structure containing information about a SSSOM repository.

    There are two ways to configure a repository:

    1. Parse from a JSON file representing a configuration
    2. Configure using Python

    ####################################
     Configuring a Repository with JSON
    ####################################

    Since the :class:`Repository` class inherits from :class:`pydantic.BaseModel`, you
    can define the data externally in a JSON file and parse it. Given the following
    example configuration (corresponding to the Biomappings project), the following
    Python code can be used to load the repository and run the CLI.

    .. code-block:: json

        {
          "predictions_path": "predictions.sssom.tsv",
          "positives_path": "positive.sssom.tsv",
          "negatives_path": "negative.sssom.tsv",
          "unsure_path": "unsure.sssom.tsv",
          "purl_base": "https://w3id.org/biopragmatics/biomappings/sssom",
          "mapping_set": {
            "mapping_set_id": "https://w3id.org/biopragmatics/biomappings/sssom/biomappings.sssom.tsv",
            "mapping_set_description": "Biomappings is a repository of community curated and predicted equivalences and related mappings between named biological entities that are not available from primary sources. It's also a place where anyone can contribute curations of predicted mappings or their own novel mappings.",
            "mapping_set_title": "Biomappings",
            "license": "https://creativecommons.org/publicdomain/zero/1.0/",
            "creator_id": ["orcid:0000-0003-4423-4370"]
          }
        }

    .. code-block:: python

        from pathlib import Path
        from sssom_curator import Repository

        path = Path("sssom-curator.json")
        repository = Repository.model_validate_json(path.read_text())

        if __name__ == "__main__":
            repository.run_cli()

    ######################################
     Configuring a Repository with Python
    ######################################

    You can configure your repository using the `sssom_curator.Repository` object
    directly from within Python, which offers the full flexibility of a general purpose
    programming language. Again using Biomappings as an example, here's how the Python
    file would look:

    .. code-block:: python

        from sssom_pydantic import MappingSet
        from sssom_curator import Repository
        from pathlib import Path

        # Assume files are all in the same folder
        HERE = Path(__file__).parent.resolve()

        repository = Repository(
            positives_path=HERE.joinpath("positive.sssom.tsv"),
            negatives_path=HERE.joinpath("negative.sssom.tsv"),
            unsure_path=HERE.joinpath("unsure.sssom.tsv"),
            predictions_path=HERE.joinpath("predictions.sssom.tsv"),
            mapping_set=MappingSet(
                title="Biomappings",
                id="https://w3id.org/biopragmatics/biomappings/sssom/biomappings.sssom.tsv",
            ),
            # Add the beginning part of the PURL used to
            # construct exports.
            purl_base="https://w3id.org/biopragmatics/biomappings/sssom/",
        )

        if __name__ == "__main__":
            repository.run_cli()
    """  # noqa:E501

    predictions_path: Path
    positives_path: Path
    negatives_path: Path
    unsure_path: Path
    mapping_set: sssom_pydantic.MappingSet | None = None
    purl_base: str | None = None
    basename: str | None = None
    ndex_uuid: str | None = None

    web_title: str | None = None
    web_disabled_message: str | None = None
    web_footer: str | None = None

    merge_standardize_bioregistry: bool | None = Field(
        None,
        description="""\
            If set to true, uses the preferred prefixes in the Bioregistry
            to standardize the merged SSSOM output. This maintains backwards
            compatibility in the Biomappings repository. You shouldn't use this
            field.
        """,
    )

    def update_relative_paths(self, directory: Path) -> None:
        """Update paths relative to the directory."""
        if not self.predictions_path.is_file():
            self.predictions_path = directory.joinpath(self.predictions_path).resolve()
        if not self.positives_path.is_file():
            self.positives_path = directory.joinpath(self.positives_path).resolve()
        if not self.negatives_path.is_file():
            self.negatives_path = directory.joinpath(self.negatives_path).resolve()
        if not self.unsure_path.is_file():
            self.unsure_path = directory.joinpath(self.unsure_path).resolve()

    @classmethod
    def from_path(cls, path: str | Path) -> Self:
        """Load a configuration at a path."""
        path = Path(path).expanduser().resolve()
        repository = cls.model_validate_json(path.read_text())
        repository.update_relative_paths(directory=path.parent)
        return repository

    @classmethod
    def from_directory(cls, directory: str | Path) -> Self:
        """Load an implicit configuration from a directory."""
        directory = Path(directory).expanduser().resolve()
        path = directory.joinpath(CONFIGURATION_FILENAME)
        if path.is_file():
            return cls.from_path(path)

        positives_path = directory.joinpath(POSITIVES_NAME)
        negatives_path = directory.joinpath(NEGATIVES_NAME)
        predictions_path = directory.joinpath(PREDICTIONS_NAME)
        unsure_path = directory.joinpath(UNSURE_NAME)

        if (
            positives_path.is_file()
            and negatives_path.is_file()
            and predictions_path.is_file()
            and unsure_path.is_file()
        ):
            return cls(
                positives_path=positives_path,
                negatives_path=negatives_path,
                predictions_path=predictions_path,
                unsure_path=unsure_path,
            )

        raise FileNotFoundError(
            f"could not automatically construct a sssom-curator "
            f"repository from directory {directory}"
        )

    @property
    def curated_paths(self) -> list[Path]:
        """Get curated paths."""
        return [self.positives_path, self.negatives_path, self.unsure_path]

    @property
    def export_paths(self) -> list[Path]:
        """Get export paths."""
        return [self.positives_path, self.negatives_path, self.predictions_path]

    @property
    def paths(self) -> list[Path]:
        """Get all paths."""
        return [self.positives_path, self.negatives_path, self.unsure_path, self.predictions_path]

    @property
    def call_to_path(self) -> dict[Call, Path]:
        """Get a dictionary from calls to paths."""
        return {
            "unsure": self.unsure_path,
            "incorrect": self.negatives_path,
            "correct": self.positives_path,
        }

    def read_positive_mappings(self) -> list[SemanticMapping]:
        """Load the positive mappings."""
        return sssom_pydantic.read(self.positives_path)[0]

    def read_negative_mappings(self) -> list[SemanticMapping]:
        """Load the negative mappings."""
        return sssom_pydantic.read(self.negatives_path)[0]

    def read_unsure_mappings(self) -> list[SemanticMapping]:
        """Load the unsure mappings."""
        return sssom_pydantic.read(self.unsure_path)[0]

    def read_predicted_mappings(self) -> list[SemanticMapping]:
        """Load the predicted mappings."""
        return sssom_pydantic.read(self.predictions_path)[0]

    def get_converter(self) -> curies.Converter:
        """Get a converter chained from all files."""
        return curies.chain([sssom_pydantic.read(path)[1] for path in self.paths])

    def append_positive_mappings(
        self, mappings: Iterable[SemanticMapping], *, converter: curies.Converter | None = None
    ) -> None:
        """Append new lines to the positive mappings document."""
        converter = ensure_converter(converter)
        insert(
            self.positives_path,
            converter=converter,
            include_mappings=mappings,
        )

    def append_negative_mappings(
        self, mappings: Iterable[SemanticMapping], *, converter: curies.Converter | None = None
    ) -> None:
        """Append new lines to the negative mappings document."""
        converter = ensure_converter(converter)
        insert(
            self.negatives_path,
            converter=converter,
            include_mappings=mappings,
        )

    def append_predicted_mappings(
        self, mappings: Iterable[SemanticMapping], *, converter: curies.Converter | None = None
    ) -> None:
        """Append new lines to the predicted mappings document."""
        converter = ensure_converter(converter)
        # FIXME exclude what's already in others? or is it better just
        #  to do a cleanup lint/prune step?
        insert(
            self.predictions_path,
            converter=converter,
            include_mappings=mappings,
        )

    def run_cli(self, *args: Any, **kwargs: Any) -> None:
        """Run the CLI."""
        _cli = self.get_cli()
        _cli(*args, *kwargs)

    def get_cli(
        self,
        *,
        enable_web: bool = True,
        get_user: UserGetter | None = None,
        output_directory: Path | None = None,
        sssom_directory: Path | None = None,
        image_directory: Path | None = None,
        get_orcid_to_name: OrcidNameGetter | None = None,
    ) -> click.Group:
        """Get a CLI."""

        @click.group()
        @click.pass_context
        def main(ctx: click.Context) -> None:
            """Run the CLI."""
            ctx.obj = self

        add_commands(
            main,
            enable_web=enable_web,
            get_user=get_user,
            output_directory=output_directory,
            sssom_directory=sssom_directory,
            image_directory=image_directory,
            get_orcid_to_name=get_orcid_to_name,
        )

        @main.command()
        @click.pass_context
        def update(ctx: click.Context) -> None:
            """Run all summary, merge, and chart exports."""
            click.secho("Generating summaries", fg="green")
            ctx.invoke(main.commands["summarize"])
            click.secho("Exporting SSSOM", fg="green")
            ctx.invoke(main.commands["merge"])

        return main

    def lexical_prediction_cli(
        self,
        prefix: str,
        target: str | list[str],
        /,
        *,
        mapping_tool: str | MappingTool | None = None,
        **kwargs: Any,
    ) -> None:
        """Run the lexical predictions CLI."""
        from .predict import lexical

        return lexical.lexical_prediction_cli(
            prefix,
            target,
            mapping_tool=mapping_tool,
            path=self.predictions_path,
            curated_paths=self.curated_paths,
            **kwargs,
        )

    def append_lexical_predictions(
        self,
        prefix: str,
        target_prefixes: str | Iterable[str],
        *,
        mapping_tool: str | MappingTool | None = None,
        force: bool = False,
        force_process: bool = False,
        cache: bool = True,
        converter: curies.Converter | None = None,
        **kwargs: Any,
    ) -> None:
        """Append lexical predictions."""
        from .predict import lexical

        # TODO this should reuse repository function for appending
        return lexical.append_lexical_predictions(
            prefix,
            target_prefixes,
            mapping_tool=mapping_tool,
            path=self.predictions_path,
            curated_paths=self.curated_paths,
            force=force,
            force_process=force_process,
            cache=cache,
            converter=converter,
            **kwargs,
        )

    def get_test_class(
        self, converter_strategy: ConverterStrategy | None = None
    ) -> type[IntegrityTestCase]:
        """Get a test case class."""
        from .testing import RepositoryTestCase

        if converter_strategy is None or converter_strategy == "passthrough":

            class PassthroughTestCurator(RepositoryTestCase):
                """A test case for this repository."""

                repository: ClassVar[Repository] = self

            return PassthroughTestCurator
        elif converter_strategy == "bioregistry":

            class BioregistryTestCurator(RepositoryTestCase):
                """A test case for this repository."""

                repository: ClassVar[Repository] = self
                converter: ClassVar[Converter] = ensure_converter(preferred=False)

            return BioregistryTestCurator
        elif converter_strategy == "bioregistry-preferred":

            class BioregistryPreferredTestCurator(RepositoryTestCase):
                """A test case for this repository."""

                repository: ClassVar[Repository] = self
                converter: ClassVar[Converter] = ensure_converter(preferred=True)

            return BioregistryPreferredTestCurator
        else:
            raise ValueError(f"invalid converter strategy: {converter_strategy}")


def add_commands(
    main: click.Group,
    *,
    enable_web: bool = True,
    get_user: UserGetter | None = None,
    output_directory: Path | None = None,
    sssom_directory: Path | None = None,
    image_directory: Path | None = None,
    get_orcid_to_name: OrcidNameGetter | None = None,
) -> None:
    """Add parametrized commands."""
    main.add_command(get_lint_command())
    main.add_command(get_web_command(enable=enable_web, get_user=get_user))
    main.add_command(get_merge_command(sssom_directory=sssom_directory))
    main.add_command(get_ndex_command())
    main.add_command(
        get_summarize_command(
            output_directory=output_directory,
            image_directory=image_directory,
            get_orcid_to_name=get_orcid_to_name,
        )
    )
    main.add_command(get_predict_command())
    main.add_command(get_test_command())
    main.add_command(get_import_command())


def get_merge_command(sssom_directory: Path | None = None) -> click.Command:
    """Get the merge command."""

    @click.command(name="merge")
    @click.option(
        "--sssom-directory",
        type=click.Path(dir_okay=True, file_okay=False, exists=True),
        default=sssom_directory,
        required=True,
    )
    @click.pass_obj
    def main(obj: Repository, sssom_directory: Path) -> None:
        """Merge files together to a single SSSOM."""
        if sssom_directory is None:
            click.secho("--sssom-directory is required", fg="red")
            raise sys.exit(1)
        if obj.mapping_set is None:
            click.secho("repository doesn't configure ``mapping_set``", fg="red")
            raise sys.exit(1)
        if obj.purl_base is None:
            click.secho("repository doesn't configure ``purl_base``", fg="red")
            raise sys.exit(1)

        from .export.merge import merge

        merge(obj, directory=sssom_directory)

    return main


def get_summarize_command(
    output_directory: Path | None = None,
    image_directory: Path | None = None,
    get_orcid_to_name: OrcidNameGetter | None = None,
) -> click.Command:
    """Get the summary command."""

    @click.command()
    @click.option(
        "--output-directory",
        type=click.Path(file_okay=False, dir_okay=True, exists=True),
        default=output_directory,
        required=True,
    )
    @click.option(
        "--image-directory",
        type=click.Path(dir_okay=True, file_okay=False),
        default=image_directory,
    )
    @click.pass_obj
    def summarize(
        obj: Repository, output_directory: Path | None, image_directory: Path | None
    ) -> None:
        """Generate summary charts and tables."""
        if output_directory is None:
            click.secho("--output-directory is required", fg="red")
            raise sys.exit(1)
        from .export.charts import make_charts
        from .export.summary import summarize

        output_directory = Path(output_directory).expanduser().resolve()
        summarize(
            obj, output_directory.joinpath("summary.yml"), get_orcid_to_name=get_orcid_to_name
        )
        make_charts(obj, output_directory, image_directory=image_directory)

    return summarize


def get_lint_command(converter: curies.Converter | None = None) -> click.Command:
    """Get the lint command."""

    @click.command()
    @strategy_option
    @click.pass_obj
    def lint(obj: Repository, strategy: ConverterStrategy) -> None:
        """Sort files and remove duplicates."""
        import sssom_pydantic

        # nonlocal lets us mess with the variable even though
        # it comes from an outside scope
        nonlocal converter
        if strategy == "passthrough":
            pass
        else:
            converter = ensure_converter(preferred=strategy == "bioregistry-preferred")

        exclude_mappings = []
        for path in obj.curated_paths:
            sssom_pydantic.lint(path, converter=converter)
            exclude_mappings.extend(sssom_pydantic.read(path)[0])

        sssom_pydantic.lint(
            obj.predictions_path,
            exclude_mappings=exclude_mappings,
            drop_duplicates=True,
        )

    return lint


def get_web_command(*, enable: bool = True, get_user: UserGetter | None = None) -> click.Command:
    """Get the web command."""
    if enable:

        @click.command()
        @click.option(
            "--resolver-base",
            help="A custom resolver base URL. Defaults to the Bioregistry.",
            default=DEFAULT_RESOLVER_BASE,
            show_default=True,
        )
        @click.option("--orcid", help="Your ORCID, if not automatically loadable")
        @click.option("--host", type=str, default="127.0.0.1", show_default=True)
        @click.option("--port", type=int, default=8775, show_default=True)
        @click.option(
            "--eager-persist",
            is_flag=True,
            help="If set, will persist after each curation instead of waiting for the commit "
            "button to be pushed",
        )
        @click.option(
            "--implementation",
            type=click.Choice(["dict", "sqlite"]),
            default="dict",
            help="The type of backend for running the curation app. Dict means that data is stored "
            "in an in-memory dictionary data structure and SQLite means it uses a database w/ ORM",
        )
        @click.option(
            "--ssl-keyfile",
            type=Path,
            help="Path to SSL key file (with the -key.pem extension), which is used to enable the "
            "web application to serve HTTPS requests",
        )
        @click.option(
            "--ssl-certfile",
            type=Path,
            help="Path to a SSL certificate file (with the .pem extension) to "
            "go along with the key file.",
        )
        @click.option(
            "--ssl-certfile",
            type=Path,
            help="Path to a SSL certificate file (with the .pem extension) to "
            "go along with the key file.",
        )
        @click.option("--live-login", is_flag=True, help="If set, uses ORCiD for login")
        @click.option("--orcid-client-id")
        @click.option("--orcid-client-secret")
        @click.pass_obj
        def web(
            obj: Repository,
            resolver_base: str | None,
            orcid: str,
            host: str,
            port: int,
            eager_persist: bool,
            implementation: Literal["dict", "sqlite"],
            ssl_keyfile: Path | None,
            ssl_certfile: Path | None,
            live_login: bool,
            orcid_client_id: str | None,
            orcid_client_secret: str | None,
        ) -> None:
            """Run the semantic mappings curation app."""
            import webbrowser

            import fastapi
            import uvicorn
            from a2wsgi import WSGIMiddleware
            from curies import NamableReference

            from .web import get_app

            if live_login:
                import pystow

                orcid_client_id = pystow.get_config(
                    "orcid_client_id", raise_on_missing=True, passthrough=orcid_client_id
                )
                orcid_client_secret = pystow.get_config(
                    "orcid_client_secret", raise_on_missing=True, passthrough=orcid_client_secret
                )

                user = None
            elif orcid is not None:
                user = NamableReference(prefix="orcid", identifier=orcid)
            elif get_user is not None:
                user = get_user()
            else:
                orcid = (
                    click.prompt("What's your ORCID?").removeprefix("https://orcid.org").rstrip("/")
                )
                user = NamableReference(prefix="orcid", identifier=orcid)

            app = get_app(
                repository=obj,
                resolver_base=resolver_base,
                user=user,
                title=obj.web_title or "Semantic Mapping Curator",
                footer=obj.web_footer,
                eager_persist=eager_persist,
                implementation=implementation,
                live_login=live_login,
                orcid_client_secret=orcid_client_secret,
                orcid_client_id=orcid_client_id,
            )
            fastapi_app = fastapi.FastAPI()
            fastapi_app.mount("/", WSGIMiddleware(app))  # type:ignore[arg-type]
            protocol = "https" if ssl_keyfile and ssl_certfile else "http"
            url = f"{protocol}://{host}:{port}"
            webbrowser.open_new_tab(url)
            uvicorn.run(
                fastapi_app,
                host=host,
                port=port,
                ssl_keyfile=ssl_keyfile,
                ssl_certfile=ssl_certfile,
            )

    else:

        @click.command()
        @click.pass_obj
        def web(obj: Repository) -> None:
            """Show an error for the web interface."""
            click.secho(
                obj.web_disabled_message
                or "web-based curator is not enabled, maybe because you're not in an editable "
                "installation of a package that build on SSSOM-Curator?",
                fg="red",
            )
            sys.exit(1)

    return web


def get_ndex_command() -> click.Command:
    """Get a CLI for uploading to NDEx."""

    @click.command()
    @click.option("--username", help="NDEx username, also looks in pystow configuration")
    @click.option("--password", help="NDEx password, also looks in pystow configuration")
    @click.pass_obj
    def ndex(obj: Repository, username: str | None, password: str | None) -> None:
        """Upload to NDEx."""
        if not obj.ndex_uuid:
            click.secho("can not upload to NDEx, no NDEx UUID is set in the curator configuration.")
            raise sys.exit(1)

        from sssom_pydantic.contrib.ndex import update_ndex

        mappings = obj.read_positive_mappings()
        update_ndex(
            uuid=obj.ndex_uuid,
            mappings=mappings,
            metadata=obj.mapping_set,
            username=username,
            password=password,
        )
        click.echo(f"Uploaded to {DEFAULT_RESOLVER_BASE}/ndex:{obj.ndex_uuid}")

    return ndex


def get_predict_command(
    *,
    source_prefix: str | None = None,
    target_prefix: str | None | list[str] = None,
) -> click.Group:
    """Create a prediction command."""
    from more_click import verbose_option

    @click.group()
    def predict() -> None:
        """Predict semantic mappings."""

    if source_prefix is None:
        source_prefix_argument = click.argument("source_prefix")
    else:
        source_prefix_argument = click.option("--source-prefix", default=source_prefix)

    if target_prefix is None:
        target_prefix_argument = click.argument("target_prefix", nargs=-1)
    else:
        target_prefix_argument = click.option(
            "--target-prefix", multiple=True, default=[target_prefix]
        )

    @predict.command()
    @verbose_option
    @source_prefix_argument
    @target_prefix_argument
    @click.option("--relation", help="the predicate to assign to semantic mappings")
    @click.option(
        "--method",
        type=click.Choice(list(typing.get_args(PredictionMethod))),
        help="The prediction method to use",
    )
    @click.option(
        "--cutoff",
        type=float,
        help="The cosine similarity cutoff to use for calling mappings when "
        "using embedding predictions",
    )
    @click.option(
        "--filter-mutual-mappings",
        is_flag=True,
        help="Remove predictions that correspond to already existing mappings "
        "in either the subject or object resource",
    )
    @click.option(
        "--force", is_flag=True, help="Force re-downloading and re-processing of resources"
    )
    @click.option(
        "--force-process",
        is_flag=True,
        help="Force re-processing, but not re-downloading of resources",
    )
    @click.option(
        "--cache/--no-cache",
        is_flag=True,
        help="Should a cache be made",
    )
    @click.option(
        "--all-by-all",
        is_flag=True,
        help="Don't just predict from source to targets, but also between all targets",
    )
    @click.option(
        "--identifiers-are-names",
        is_flag=True,
        help="Consider identifiers as names. This is typical for data models/schemas",
    )
    @click.pass_obj
    def lexical(
        obj: Repository,
        source_prefix: str,
        target_prefix: str,
        relation: str | None,
        method: PredictionMethod | None,
        cutoff: float | None,
        filter_mutual_mappings: bool,
        cache: bool,
        force: bool,
        force_process: bool,
        all_by_all: bool,
        identifiers_are_names: bool,
    ) -> None:
        """Predict semantic mappings with lexical methods."""
        from .predict.lexical import append_lexical_predictions

        append_lexical_predictions(
            source_prefix,
            target_prefix,
            path=obj.predictions_path,
            curated_paths=obj.curated_paths,
            filter_mutual_mappings=filter_mutual_mappings,
            relation=relation,
            method=method,
            cutoff=cutoff,
            cache=cache,
            force=force,
            force_process=force_process,
            all_by_all=all_by_all,
            identifiers_are_names=identifiers_are_names,
        )

    return predict


def get_test_command() -> click.Command:
    """Get a command to run tests."""

    @click.command()
    @strategy_option
    @click.pass_obj
    def test(obj: Repository, strategy: ConverterStrategy) -> None:
        """Test the repository."""
        import unittest

        test_case_class = obj.get_test_class(converter_strategy=strategy)
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(test_case_class)

        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)

        # Exit with code 1 if tests failed, 0 otherwise
        sys.exit(not result.wasSuccessful())

    return test


def _get_latest_semra() -> tuple[str, None, int]:
    url = "https://zenodo.org/records/15504009/files/mappings.sssom.tsv.gz"
    version = None  # TODO
    count = 43_400_000
    return url, version, count


def get_import_command() -> click.Group:
    """Get a command for importing."""
    url, version, count = _get_latest_semra()

    @click.group(name="import")
    def import_group() -> None:
        """Import external SSSOM files."""

    preview_warning = (
        "This command is in preview mode, and functionality may change without warning"
    )

    @import_group.command(
        name="semra",
        help="Import raw mappings from SeMRA.\n\n"
        "Currently, this workflow is configured to only import semantic mappings from the "
        "SeMRA Raw Mapping database (https://doi.org/10.5281/zenodo.11082038) that are not "
        "already marked as manual mapping curations, have a CC0 license, and are either "
        f"an exact match or dbxref.\n\nNote: {preview_warning}",
    )
    @click.option(
        "-p",
        "--prefixes",
        multiple=True,
        help="Filter to mappings whose subject and objects are both in the prefix list."
        "Must pass at least two.",
    )
    @click.pass_obj
    def import_semra(obj: Repository, prefixes: list[str]) -> None:
        """Import mappings from SeMRA."""
        if len(prefixes) < 2:
            click.secho("requires two or more prefixes", fg="red")
            raise sys.exit(1)

        click.secho(preview_warning, fg="yellow")

        import bioregistry
        import pystow

        path = pystow.ensure("semra", "cache", url=url, version=version)
        converter = bioregistry.get_converter()
        mappings, _, _ = sssom_pydantic.read(
            path,
            metadata={"mapping_set_id": url},
            progress=True,
            progress_kwargs={"total": count},
            semantic_mapping_predicate=_get_predicate(prefixes),
            converter=converter,
        )
        obj.append_predicted_mappings(mappings, converter=converter)

    @import_group.command(
        name="ontoportal",
        help="Import uncurated mappings from an OntoPortal instance",
    )
    @click.argument("ontology_1")
    @click.argument("ontology_2")
    @click.option(
        "--instance",
        type=click.Choice(["bioportal", "agroportal", "ecoportal"]),
        default="bioportal",
        show_default=True,
    )
    @click.pass_obj
    def import_ontoportal(obj: Repository, ontology_1: str, ontology_2: str, instance: str) -> None:
        """Import mappings from an OntoPortal instance."""
        import bioregistry
        from ontoportal_client import ontoportal_resolver
        from sssom_pydantic.contrib.ontoportal import from_ontoportal

        client = ontoportal_resolver.make(instance)
        registry = bioregistry.get_registry(instance)
        if registry is None:
            click.secho(f"{instance} is not a valid Bioregistry registry", fg="red")
            sys.exit(1)

        left_resource = bioregistry.get_resource(ontology_1, strict=True)
        left_bioportal = left_resource.get_mapped_prefix(instance)
        if left_bioportal is None:
            click.secho(
                f"{ontology_1} does not have a {registry.get_short_name()} mapping", fg="red"
            )
            sys.exit(1)

        right_resource = bioregistry.get_resource(ontology_2, strict=True)
        right_bioportal = right_resource.get_mapped_prefix(instance)
        if right_bioportal is None:
            click.secho(
                f"{ontology_2} does not have a {registry.get_short_name()} mapping", fg="red"
            )
            sys.exit(1)

        converter = bioregistry.get_converter()

        mappings = from_ontoportal(
            left_bioportal, right_bioportal, converter=converter, client=client, progress=True
        )

        # Filter to only be mappings incident to the given prefixes
        mappings_filtered = _keep_only_prefixes(
            mappings, {left_resource.prefix, right_resource.prefix}
        )

        obj.append_predicted_mappings(mappings_filtered, converter=converter)

    return import_group


def _keep_only_prefixes(
    mappings: Iterable[SemanticMapping], kk: set[str]
) -> Iterable[SemanticMapping]:
    for m in mappings:
        if m.subject.prefix in kk and m.object.prefix in kk:
            yield m


def _get_predicate(prefixes: list[str]) -> SemanticMappingPredicate:
    from curies.vocabulary import exact_match, has_dbxref, manual_mapping_curation

    prefix_checker = set(prefixes).__contains__
    predicate_checker = {exact_match, has_dbxref}.__contains__
    license_checker = "CC0".__eq__

    def _justification_checker(x: curies.Reference) -> bool:
        return x != manual_mapping_curation

    if prefixes:

        def _predicate(m: SemanticMapping) -> bool:
            return (
                _justification_checker(m.justification)
                and predicate_checker(m.predicate)
                and prefix_checker(m.subject.prefix)
                and prefix_checker(m.object.prefix)
                and license_checker(m.license)
            )
    else:

        def _predicate(m: SemanticMapping) -> bool:
            return (
                _justification_checker(m.justification)
                and predicate_checker(m.predicate)
                and license_checker(m.license)
            )

    return _predicate
