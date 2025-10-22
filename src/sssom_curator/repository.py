"""Repository."""

from __future__ import annotations

import sys
import typing
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, TypeAlias

import click
import sssom_pydantic
from pydantic import BaseModel
from sssom_pydantic import MappingSet
from typing_extensions import Self

from .constants import DEFAULT_RESOLVER_BASE, ensure_converter

if TYPE_CHECKING:
    import curies
    from curies import Converter
    from sssom_pydantic import MappingTool, SemanticMapping

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
NAME = "sssom-curator.json"

strategy_option = click.option(
    "--strategy",
    type=click.Choice(list(typing.get_args(ConverterStrategy))),
    default="passthrough",
    show_default=True,
)


class Repository(BaseModel):
    """A data structure containing information about a SSSOM repository."""

    predictions_path: Path
    positives_path: Path
    negatives_path: Path
    unsure_path: Path
    mapping_set: MappingSet | None = None
    purl_base: str | None = None
    basename: str | None = None
    ndex_uuid: str | None = None

    web_title: str | None = None
    web_disabled_message: str | None = None
    web_footer: str | None = None

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
        path = directory.joinpath(NAME)
        if path.is_file():
            return cls.from_path(path)

        positives_path = directory.joinpath("positive.sssom.tsv")
        negatives_path = directory.joinpath("negative.sssom.tsv")
        predictions_path = directory.joinpath("predictions.sssom.tsv")
        unsure_path = directory.joinpath("unsure.sssom.tsv")

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

    def append_positive_mappings(
        self, mappings: Iterable[SemanticMapping], *, converter: curies.Converter | None = None
    ) -> None:
        """Append new lines to the positive mappings document."""
        from .constants import ensure_converter
        from .web.wsgi_utils import insert

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
        from .constants import ensure_converter
        from .web.wsgi_utils import insert

        converter = ensure_converter(converter)
        insert(
            self.negatives_path,
            converter=converter,
            include_mappings=mappings,
        )

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
            click.secho("Building general exports", fg="green")
            ctx.invoke(main.commands["summary"])
            click.secho("Building SSSOM export", fg="green")
            ctx.invoke(main.commands["merge"])
            click.secho("Generating charts", fg="green")
            ctx.invoke(main.commands["charts"])

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
        **kwargs: Any,
    ) -> None:
        """Append lexical predictions."""
        from .predict import lexical

        return lexical.append_lexical_predictions(
            prefix,
            target_prefixes,
            mapping_tool=mapping_tool,
            path=self.positives_path,
            curated_paths=self.curated_paths,
            **kwargs,
        )

    def get_test_class(
        self,
        converter_strategy: Literal["bioregistry", "bioregistry-preferred", "passthrough"]
        | None = None,
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
        get_summary_command(output_directory=output_directory, get_orcid_to_name=get_orcid_to_name)
    )
    main.add_command(
        get_charts_command(output_directory=output_directory, image_directory=image_directory)
    )
    main.add_command(get_predict_command())
    main.add_command(get_test_command())


def get_charts_command(
    output_directory: Path | None = None, image_directory: Path | None = None
) -> click.Command:
    """Get the charts command."""

    @click.command()
    @click.option(
        "--directory", type=click.Path(dir_okay=True, file_okay=False), default=output_directory
    )
    @click.option(
        "--image-directory",
        type=click.Path(dir_okay=True, file_okay=False),
        default=image_directory,
    )
    @click.pass_obj
    def charts(obj: Repository, directory: Path, image_directory: Path) -> None:
        """Make charts."""
        from .export.charts import make_charts

        make_charts(obj, directory, image_directory)

    return charts


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


def get_summary_command(
    output_directory: Path | None = None,
    get_orcid_to_name: OrcidNameGetter | None = None,
) -> click.Command:
    """Get the summary command."""
    from .export.summary import summarize

    @click.command()
    @click.option(
        "--output",
        type=click.Path(file_okay=True, dir_okay=False, exists=True),
        default=output_directory.joinpath("summary.yml") if output_directory else None,
        required=True,
    )
    @click.pass_obj
    def summary(obj: Repository, output: Path | None) -> None:
        """Create export data file."""
        if output is None:
            click.secho("--output is required")
            raise sys.exit(1)
        summarize(obj, output, get_orcid_to_name=get_orcid_to_name)

    return summary


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
            from .constants import ensure_converter

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
        @click.option("--port", type=int, default=5003, show_default=True)
        @click.pass_obj
        def web(obj: Repository, resolver_base: str | None, orcid: str, port: int) -> None:
            """Run the semantic mappings curation app."""
            import webbrowser

            from curies import NamableReference
            from more_click import run_app

            from .web.wsgi import get_app

            if orcid is not None:
                user = NamableReference(prefix="orcid", identifier=orcid)
            elif get_user is not None:
                user = get_user()
            else:
                orcid = click.prompt("What's your ORCID?")
                user = NamableReference(prefix="orcid", identifier=orcid)

            app = get_app(
                predictions_path=obj.predictions_path,
                positives_path=obj.positives_path,
                negatives_path=obj.negatives_path,
                unsure_path=obj.unsure_path,
                resolver_base=resolver_base,
                user=user,
                title=obj.web_title or "Semantic Mapping Curator",
                footer=obj.web_footer,
            )

            webbrowser.open_new_tab(f"http://localhost:{port}")

            run_app(app, with_gunicorn=False, port=str(port))

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
) -> click.Command:
    """Create a prediction command."""
    from more_click import verbose_option

    from .constants import PredictionMethod

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

    @click.command()
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
    @click.pass_obj
    def predict(
        obj: Repository,
        source_prefix: str,
        target_prefix: str,
        relation: str | None,
        method: PredictionMethod | None,
        cutoff: float | None,
        filter_mutual_mappings: bool,
    ) -> None:
        """Predict semantic mappings."""
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
