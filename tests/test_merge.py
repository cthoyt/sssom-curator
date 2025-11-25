"""Tests for merging."""

from textwrap import dedent

from sssom_curator.export.merge import merge
from tests import cases


class TestMerge(cases.RepositoryTestCase):
    """Test merge."""

    def test_empty_merge(self) -> None:
        """Test merge works directly after initialization."""
        directory = self.directory.joinpath("output")
        directory.mkdir()
        merge(self.repository, directory)

        tsv_path = directory.joinpath(f"{self.directory.name}.sssom.tsv")
        self.assertTrue(tsv_path.is_file())
        self.assertEqual(
            dedent(f"""\
                #curie_map:
                #  ex: https://example.org/
                #  orcid: https://orcid.org/
                #  semapv: https://w3id.org/semapv/vocab/
                #  skos: http://www.w3.org/2004/02/skos/core#
                #license: spdx:CC0-1.0
                #mapping_set_id: {self.mapping_set.id}
                #mapping_set_title: {self.directory.name}
                subject_id\tsubject_label\tpredicate_id\tpredicate_modifier\tobject_id\tobject_label\tmapping_justification\tauthor_id\tconfidence
                ex:1\t1\tskos:exactMatch\t\tex:2\t2\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t
                ex:3\t3\tskos:exactMatch\tNot\tex:4\t4\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t
                ex:7\t7\tskos:exactMatch\t\tex:8\t8\tsemapv:LexicalMatching\t\t0.77
            """).rstrip(),
            tsv_path.read_text().rstrip(),
        )
