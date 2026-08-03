"""
Tests unitaires — features/transfert/importer.py

Couvre : import_metaobject_definitions, import_metafield_definitions,
         import_files, import_metaobjects, _build_product_payload,
         _link_variant_images, import_products, import_product_metafields
"""
import unittest
from unittest.mock import patch, MagicMock, call

from features.transfert.importer import (
    import_metaobject_definitions,
    import_metafield_definitions,
    import_files,
    import_metaobjects,
    _build_product_payload,
    _link_variant_images,
    import_products,
    import_product_metafields,
)


class TestImportMetaobjectDefinitions(unittest.TestCase):
    @patch("features.transfert.importer.create_metaobject_type", return_value="gid://dest/def/1")
    @patch("features.transfert.importer.get_all_metaobject_definitions", return_value={})
    def test_creates_missing_definition_and_remaps(self, mock_existing, mock_create):
        mo_defs = [{
            "source_id": "gid://src/def/1", "type": "avis_client", "name": "Avis",
            "fieldDefinitions": [{"key": "note", "name": "Note", "type": "single_line_text_field"}],
        }]
        remap = import_metaobject_definitions(mo_defs, "http://dest", {})

        mock_create.assert_called_once()
        self.assertEqual(remap["gid://src/def/1"], "gid://dest/def/1")

    @patch("features.transfert.importer.create_metaobject_type")
    @patch("features.transfert.importer.get_all_metaobject_definitions",
           return_value={"avis_client": "gid://dest/existing"})
    def test_reuses_existing_definition(self, mock_existing, mock_create):
        mo_defs = [{"source_id": "gid://src/1", "type": "avis_client", "name": "Avis", "fieldDefinitions": []}]
        remap = import_metaobject_definitions(mo_defs, "http://dest", {})

        mock_create.assert_not_called()
        self.assertEqual(remap["gid://src/1"], "gid://dest/existing")

    @patch("features.transfert.importer.create_metaobject_type")
    @patch("features.transfert.importer.get_all_metaobject_definitions", return_value={})
    def test_skips_shopify_reserved_types(self, mock_existing, mock_create):
        mo_defs = [{"source_id": "gid://src/1", "type": "shopify--color-pattern", "name": "X", "fieldDefinitions": []}]
        remap = import_metaobject_definitions(mo_defs, "http://dest", {})

        mock_create.assert_not_called()
        self.assertEqual(remap, {})


class TestImportMetafieldDefinitions(unittest.TestCase):
    @patch("features.transfert.importer.create_metafield_definition")
    def test_remaps_metaobject_definition_id_in_validations(self, mock_create):
        mf_defs = [{
            "name": "Avis 1", "key": "avis_clients_1", "type": "metaobject_reference",
            "validations": [{"name": "metaobject_definition_id", "value": "gid://src/def/1"}],
        }]
        mo_def_remap = {"gid://src/def/1": "gid://dest/def/1"}

        import_metafield_definitions(mf_defs, mo_def_remap, "http://dest", {})

        _, kwargs = mock_create.call_args
        self.assertEqual(kwargs["mo_def_id"], "gid://dest/def/1")

    @patch("features.transfert.importer.create_metafield_definition")
    def test_non_reference_type_has_no_mo_def_id(self, mock_create):
        mf_defs = [{"name": "Texte", "key": "specs", "type": "single_line_text_field", "validations": []}]

        import_metafield_definitions(mf_defs, {}, "http://dest", {})

        _, kwargs = mock_create.call_args
        self.assertIsNone(kwargs["mo_def_id"])


class TestImportFiles(unittest.TestCase):
    def test_empty_input_returns_empty(self):
        self.assertEqual(import_files({}, "http://dest", {}), {})

    @patch("features.transfert.importer.time.sleep")
    @patch("features.transfert.importer.graphql_request")
    def test_remaps_source_gid_to_new_gid(self, mock_gql, mock_sleep):
        mock_gql.return_value = {"data": {"fileCreate": {
            "files": [{"id": "gid://dest/file/1", "alt": ""}], "userErrors": [],
        }}}
        remap = import_files({"gid://src/file/1": "https://cdn/1.jpg"}, "http://dest", {})

        self.assertEqual(remap["gid://src/file/1"], "gid://dest/file/1")

    @patch("features.transfert.importer.time.sleep")
    @patch("features.transfert.importer.graphql_request")
    def test_user_errors_skip_file(self, mock_gql, mock_sleep):
        mock_gql.return_value = {"data": {"fileCreate": {
            "files": [], "userErrors": [{"field": "originalSource", "message": "bad url"}],
        }}}
        remap = import_files({"gid://src/1": "https://bad"}, "http://dest", {})

        self.assertEqual(remap, {})


class TestImportMetaobjects(unittest.TestCase):
    @patch("features.transfert.importer.time.sleep")
    @patch("features.transfert.importer.create_metaobject_generic", return_value="gid://dest/mo/1")
    def test_remaps_file_reference_field(self, mock_create, mock_sleep):
        metaobjects = {"avis_client": [{
            "source_id": "gid://src/mo/1",
            "fields": [
                {"key": "note",    "value": "5.0",          "type": "single_line_text_field"},
                {"key": "photo_1", "value": "gid://src/file/1", "type": "file_reference"},
            ],
        }]}
        file_remap = {"gid://src/file/1": "gid://dest/file/1"}

        remap = import_metaobjects(metaobjects, file_remap, "http://dest", {})

        self.assertEqual(remap["gid://src/mo/1"], "gid://dest/mo/1")
        sent_fields = mock_create.call_args[0][1]
        photo = next(f for f in sent_fields if f["key"] == "photo_1")
        self.assertEqual(photo["value"], "gid://dest/file/1")

    @patch("features.transfert.importer.time.sleep")
    @patch("features.transfert.importer.create_metaobject_generic", return_value="gid://dest/mo/1")
    def test_drops_file_reference_without_remap(self, mock_create, mock_sleep):
        metaobjects = {"t": [{
            "source_id": "gid://src/mo/1",
            "fields": [{"key": "photo_1", "value": "gid://src/file/unknown", "type": "file_reference"}],
        }]}
        import_metaobjects(metaobjects, {}, "http://dest", {})

        sent_fields = mock_create.call_args[0][1]
        self.assertNotIn("photo_1", [f["key"] for f in sent_fields])

    @patch("features.transfert.importer.time.sleep")
    @patch("features.transfert.importer.create_metaobject_generic")
    def test_skips_shopify_reserved_types(self, mock_create, mock_sleep):
        metaobjects = {"shopify--color-pattern": [{"source_id": "gid://1", "fields": []}]}
        import_metaobjects(metaobjects, {}, "http://dest", {})

        mock_create.assert_not_called()


class TestBuildProductPayload(unittest.TestCase):
    def test_maps_core_fields(self):
        product = {"title": "Prod", "body_html": "<p>x</p>", "vendor": "V",
                   "handle": "prod", "status": "active"}
        payload = _build_product_payload(product)

        self.assertEqual(payload["title"], "Prod")
        self.assertEqual(payload["body_html"], "<p>x</p>")
        self.assertEqual(payload["handle"], "prod")

    def test_variants_are_mapped(self):
        product = {"title": "P", "variants": [
            {"price": "10.00", "option1": "Rouge", "sku": "SKU1", "taxable": False},
        ]}
        payload = _build_product_payload(product)

        self.assertEqual(payload["variants"][0]["price"], "10.00")
        self.assertEqual(payload["variants"][0]["option1"], "Rouge")
        self.assertFalse(payload["variants"][0]["taxable"])

    def test_images_without_src_are_dropped(self):
        product = {"title": "P", "images": [
            {"src": "https://cdn/1.jpg", "position": 1},
            {"src": "", "position": 2},
        ]}
        payload = _build_product_payload(product)

        self.assertEqual(len(payload["images"]), 1)


class TestLinkVariantImages(unittest.TestCase):
    @patch("features.transfert.importer.shopify_put")
    def test_links_variant_to_dest_image_by_position(self, mock_put):
        source = {
            "images":   [{"id": 11, "position": 1}],
            "variants": [{"id": 21, "image_id": 11}],
        }
        dest = {
            "id": 999,
            "images":   [{"id": 91, "position": 1}],
            "variants": [{"id": 81}],
        }
        _link_variant_images(source, dest, "http://dest", {})

        payload = mock_put.call_args[0][2]
        self.assertEqual(payload["variant"]["image_id"], 91)

    @patch("features.transfert.importer.shopify_put")
    def test_no_images_does_nothing(self, mock_put):
        _link_variant_images({"images": [], "variants": [{"id": 1}]}, {"images": []}, "http://dest", {})
        mock_put.assert_not_called()


class TestImportProducts(unittest.TestCase):
    @patch("features.transfert.importer.time.sleep")
    @patch("features.transfert.importer._link_variant_images")
    @patch("features.transfert.importer.shopify_post")
    def test_remaps_source_id_to_dest_id(self, mock_post, mock_link, mock_sleep):
        mock_post.return_value = {"product": {"id": 999, "handle": "prod", "images": [], "variants": []}}
        products = [{"id": 1, "handle": "prod", "title": "P"}]

        remap = import_products(products, "http://dest", {})

        self.assertEqual(remap[1], 999)

    @patch("features.transfert.importer.time.sleep")
    @patch("features.transfert.importer.shopify_post", side_effect=Exception("boom"))
    def test_failed_product_absent_from_remap(self, mock_post, mock_sleep):
        remap = import_products([{"id": 1, "handle": "prod", "title": "P"}], "http://dest", {})

        self.assertEqual(remap, {})


class TestImportProductMetafields(unittest.TestCase):
    @patch("features.transfert.importer.time.sleep")
    @patch("features.transfert.importer.set_product_metafield")
    def test_remaps_metaobject_reference(self, mock_set, mock_sleep):
        product_mfs = {1: [
            {"key": "avis_clients_1", "value": "gid://src/mo/1",
             "type": "metaobject_reference", "namespace": "custom"},
        ]}
        product_remap    = {1: 999}
        metaobject_remap = {"gid://src/mo/1": "gid://dest/mo/1"}

        import_product_metafields(product_mfs, product_remap, metaobject_remap, {}, "http://dest", {})

        args = mock_set.call_args[0]
        self.assertEqual(args[0], 999)                 # dest product id
        self.assertEqual(args[3], "gid://dest/mo/1")   # value remappée

    @patch("features.transfert.importer.time.sleep")
    @patch("features.transfert.importer.set_product_metafield")
    def test_skips_unremapped_metaobject_reference(self, mock_set, mock_sleep):
        product_mfs = {1: [
            {"key": "avis_clients_1", "value": "gid://src/mo/unknown",
             "type": "metaobject_reference", "namespace": "custom"},
        ]}
        import_product_metafields(product_mfs, {1: 999}, {}, {}, "http://dest", {})

        mock_set.assert_not_called()

    @patch("features.transfert.importer.time.sleep")
    @patch("features.transfert.importer.set_product_metafield")
    def test_skips_product_not_in_remap(self, mock_set, mock_sleep):
        product_mfs = {1: [{"key": "k", "value": "v", "type": "single_line_text_field", "namespace": "custom"}]}
        import_product_metafields(product_mfs, {}, {}, {}, "http://dest", {})

        mock_set.assert_not_called()

    @patch("features.transfert.importer.time.sleep")
    @patch("features.transfert.importer.set_product_metafield")
    def test_plain_metafield_is_injected(self, mock_set, mock_sleep):
        product_mfs = {1: [
            {"key": "specs", "value": "180cm", "type": "single_line_text_field", "namespace": "custom"},
        ]}
        import_product_metafields(product_mfs, {1: 999}, {}, {}, "http://dest", {})

        mock_set.assert_called_once()
        self.assertEqual(mock_set.call_args[0][3], "180cm")


if __name__ == "__main__":
    unittest.main()
