"""
Tests unitaires — features/transfert/exporter.py

Couvre : export_metaobject_definitions, export_metaobjects,
         export_metafield_definitions, export_products,
         export_product_metafields, _collect_file_gids, export_file_urls
"""
import unittest
from unittest.mock import patch, MagicMock

from features.transfert.exporter import (
    export_metaobject_definitions,
    export_metaobjects,
    export_metafield_definitions,
    export_products,
    export_product_metafields,
    _collect_file_gids,
    export_file_urls,
)


class TestExportMetaobjectDefinitions(unittest.TestCase):
    @patch("features.transfert.exporter.graphql_request")
    def test_flattens_field_definitions(self, mock_gql):
        mock_gql.return_value = {"data": {"metaobjectDefinitions": {
            "edges": [{
                "node": {
                    "id": "gid://def/1", "type": "avis_client", "name": "Avis client",
                    "fieldDefinitions": [
                        {"key": "note", "name": "Note", "type": {"name": "single_line_text_field"},
                         "required": True, "validations": []},
                    ],
                },
                "cursor": "C1",
            }],
            "pageInfo": {"hasNextPage": False},
        }}}
        result = export_metaobject_definitions("http://base", {})

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_id"], "gid://def/1")
        self.assertEqual(result[0]["type"], "avis_client")
        self.assertEqual(result[0]["fieldDefinitions"][0]["type"], "single_line_text_field")

    @patch("features.transfert.exporter.graphql_request")
    def test_paginates(self, mock_gql):
        mock_gql.side_effect = [
            {"data": {"metaobjectDefinitions": {
                "edges": [{"node": {"id": "gid://1", "type": "a", "name": "A", "fieldDefinitions": []}, "cursor": "C1"}],
                "pageInfo": {"hasNextPage": True},
            }}},
            {"data": {"metaobjectDefinitions": {
                "edges": [{"node": {"id": "gid://2", "type": "b", "name": "B", "fieldDefinitions": []}, "cursor": "C2"}],
                "pageInfo": {"hasNextPage": False},
            }}},
        ]
        result = export_metaobject_definitions("http://base", {})

        self.assertEqual(len(result), 2)
        self.assertEqual(mock_gql.call_count, 2)


class TestExportMetaobjects(unittest.TestCase):
    @patch("features.transfert.exporter.graphql_request")
    def test_groups_instances_by_type(self, mock_gql):
        mock_gql.return_value = {"data": {"metaobjects": {
            "edges": [{
                "node": {"id": "gid://mo/1", "type": "avis_client", "handle": "avis-1",
                         "fields": [{"key": "note", "value": "5.0", "type": "single_line_text_field"}]},
                "cursor": "C1",
            }],
            "pageInfo": {"hasNextPage": False},
        }}}
        result = export_metaobjects("http://base", {}, ["avis_client"])

        self.assertIn("avis_client", result)
        self.assertEqual(len(result["avis_client"]), 1)
        self.assertEqual(result["avis_client"][0]["source_id"], "gid://mo/1")

    @patch("features.transfert.exporter.graphql_request")
    def test_multiple_types(self, mock_gql):
        mock_gql.return_value = {"data": {"metaobjects": {
            "edges": [], "pageInfo": {"hasNextPage": False},
        }}}
        result = export_metaobjects("http://base", {}, ["type_a", "type_b"])

        self.assertEqual(set(result), {"type_a", "type_b"})
        self.assertEqual(mock_gql.call_count, 2)


class TestExportMetafieldDefinitions(unittest.TestCase):
    @patch("features.transfert.exporter.graphql_request")
    def test_extracts_type_name(self, mock_gql):
        mock_gql.return_value = {"data": {"metafieldDefinitions": {
            "edges": [{
                "node": {"id": "gid://mf/1", "name": "Avis 1", "namespace": "custom",
                         "key": "avis_clients_1", "type": {"name": "metaobject_reference"},
                         "validations": [{"name": "metaobject_definition_id", "value": "gid://def/1"}]},
                "cursor": "C1",
            }],
            "pageInfo": {"hasNextPage": False},
        }}}
        result = export_metafield_definitions("http://base", {})

        self.assertEqual(result[0]["type"], "metaobject_reference")
        self.assertEqual(result[0]["validations"][0]["value"], "gid://def/1")


class TestExportProducts(unittest.TestCase):
    @patch("features.transfert.exporter.shopify_get_paginated")
    def test_fetches_all_statuses(self, mock_get):
        # 3 status (active, draft, archived), une page chacun sans "next"
        mock_get.return_value = ({"products": [{"id": 1}]}, "")
        products = export_products("http://base", {})

        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(len(products), 3)

    @patch("features.transfert.exporter.shopify_get_paginated")
    def test_follows_next_link(self, mock_get):
        next_link = '<http://base/products.json?page_info=XYZ>; rel="next"'
        mock_get.side_effect = [
            ({"products": [{"id": 1}]}, next_link),   # active page 1 → next
            ({"products": [{"id": 2}]}, ""),          # active page 2 → fin
            ({"products": []}, ""),                    # draft
            ({"products": []}, ""),                    # archived
        ]
        products = export_products("http://base", {})

        self.assertEqual(len(products), 2)
        self.assertEqual(mock_get.call_count, 4)


class TestExportProductMetafields(unittest.TestCase):
    @patch("features.transfert.exporter.shopify_get")
    def test_filters_by_namespace(self, mock_get):
        mock_get.return_value = {"metafields": [
            {"namespace": "custom", "key": "k1", "value": "v1", "type": "single_line_text_field"},
            {"namespace": "seo",    "key": "k2", "value": "v2", "type": "single_line_text_field"},
            {"namespace": "global", "key": "title_tag", "value": "T", "type": "single_line_text_field"},
        ]}
        result = export_product_metafields([{"id": 101}], "http://base", {})

        keys = [mf["key"] for mf in result[101]]
        self.assertIn("k1", keys)         # custom → gardé
        self.assertIn("title_tag", keys)  # global → gardé
        self.assertNotIn("k2", keys)      # seo → exclu

    @patch("features.transfert.exporter.shopify_get")
    def test_products_without_metafields_absent(self, mock_get):
        mock_get.return_value = {"metafields": []}
        result = export_product_metafields([{"id": 101}], "http://base", {})

        self.assertNotIn(101, result)


class TestCollectFileGids(unittest.TestCase):
    def test_collects_from_metaobjects_and_metafields(self):
        metaobjects = {"avis_client": [
            {"fields": [
                {"key": "photo_1", "value": "gid://file/1", "type": "file_reference"},
                {"key": "note",    "value": "5.0",          "type": "single_line_text_field"},
            ]},
        ]}
        product_mfs = {101: [
            {"key": "img", "value": "gid://file/2", "type": "file_reference"},
        ]}
        gids = _collect_file_gids(metaobjects, product_mfs)

        self.assertEqual(set(gids), {"gid://file/1", "gid://file/2"})

    def test_ignores_empty_file_values(self):
        metaobjects = {"t": [{"fields": [{"key": "photo_1", "value": "", "type": "file_reference"}]}]}
        gids = _collect_file_gids(metaobjects, {})

        self.assertEqual(gids, [])


class TestExportFileUrls(unittest.TestCase):
    def test_empty_input_returns_empty(self):
        self.assertEqual(export_file_urls("http://base", {}, []), {})

    @patch("features.transfert.exporter.graphql_request")
    def test_resolves_image_url(self, mock_gql):
        mock_gql.return_value = {"data": {"nodes": [
            {"id": "gid://file/1", "image": {"url": "https://cdn/1.jpg"}},
        ]}}
        result = export_file_urls("http://base", {}, ["gid://file/1"])

        self.assertEqual(result["gid://file/1"], "https://cdn/1.jpg")

    @patch("features.transfert.exporter.graphql_request")
    def test_skips_null_nodes(self, mock_gql):
        mock_gql.return_value = {"data": {"nodes": [
            None,
            {"id": "gid://file/2", "url": "https://cdn/2.pdf"},
        ]}}
        result = export_file_urls("http://base", {}, ["gid://file/1", "gid://file/2"])

        self.assertEqual(result, {"gid://file/2": "https://cdn/2.pdf"})


if __name__ == "__main__":
    unittest.main()
