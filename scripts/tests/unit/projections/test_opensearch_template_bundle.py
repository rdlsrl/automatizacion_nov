from __future__ import annotations

from pathlib import Path
import json
import unittest

from drilling_knowledge.projections.search import OpenSearchTemplateBundleLoader


class OpenSearchTemplateBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("/mnt/mariadb/autom_nov/autom_nov/scripts/db/opensearch")

    def test_bundle_loads_documented_templates_and_aliases(self) -> None:
        bundle = OpenSearchTemplateBundleLoader.load(self.root)

        self.assertEqual(
            {template.index_name for template in bundle.templates},
            {"ikc-variables-v1", "ikc-documents-v1", "ikc-fragments-v1", "ikc-assertions-v1", "ikc-facts-v1"},
        )
        self.assertIn(("ikc-variables-v1", "ikc-variables-current"), {(alias.index_name, alias.alias_name) for alias in bundle.aliases})

    def test_variables_template_matches_documented_fields(self) -> None:
        bundle = OpenSearchTemplateBundleLoader.load(self.root)
        template = next(item for item in bundle.templates if item.index_name == "ikc-variables-v1")

        self.assertIn("canonical_name", template.field_names())
        self.assertIn("embedding", template.field_names())
        self.assertEqual(template.body["mappings"]["dynamic"], "strict")

    def test_bundle_serialization_is_stable(self) -> None:
        first = OpenSearchTemplateBundleLoader.load(self.root)
        second = OpenSearchTemplateBundleLoader.load(self.root)

        self.assertEqual(json.dumps(first.as_serializable(), sort_keys=True), json.dumps(second.as_serializable(), sort_keys=True))