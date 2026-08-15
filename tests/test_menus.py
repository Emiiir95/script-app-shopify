"""
Tests unitaires — features/menus/injector.py

Couvre : _fetch_collection_gids, _fetch_page_gids, _fetch_policy_gids,
         fetch_menu_gid, _build_items, upsert_menu
"""
import unittest
from unittest.mock import patch, MagicMock

from features.menus.injector import (
    _fetch_collection_gids,
    _fetch_page_gids,
    _fetch_policy_gids,
    fetch_menu_gid,
    _build_items,
    upsert_menu,
)


COLLECTION_MAP = {"griffoirs": "gid://shopify/Collection/1", "arbres": "gid://shopify/Collection/2"}
PAGE_MAP       = {"a-propos": "gid://shopify/Page/10"}
BLOG_MAP       = {"news": "gid://shopify/Blog/20"}
POLICY_MAP     = {"REFUND_POLICY": "gid://shopify/ShopPolicy/30"}


class TestFetchGids(unittest.TestCase):
    @patch("features.menus.injector.graphql_request")
    def test_fetch_collection_gids_maps_handle_to_gid(self, mock_gql):
        mock_gql.return_value = {"data": {"collections": {
            "nodes": [{"id": "gid://1", "handle": "griffoirs"}, {"id": "gid://2", "handle": "arbres"}],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }}}
        result = _fetch_collection_gids("http://base", {})

        self.assertEqual(result, {"griffoirs": "gid://1", "arbres": "gid://2"})

    @patch("features.menus.injector.graphql_request")
    def test_fetch_collection_gids_paginates(self, mock_gql):
        mock_gql.side_effect = [
            {"data": {"collections": {
                "nodes": [{"id": "gid://1", "handle": "a"}],
                "pageInfo": {"hasNextPage": True, "endCursor": "C1"},
            }}},
            {"data": {"collections": {
                "nodes": [{"id": "gid://2", "handle": "b"}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }}},
        ]
        result = _fetch_collection_gids("http://base", {})

        self.assertEqual(len(result), 2)
        self.assertEqual(mock_gql.call_count, 2)

    @patch("features.menus.injector.graphql_request")
    def test_fetch_page_gids(self, mock_gql):
        mock_gql.return_value = {"data": {"pages": {
            "nodes": [{"id": "gid://10", "handle": "a-propos"}],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }}}
        result = _fetch_page_gids("http://base", {})

        self.assertEqual(result, {"a-propos": "gid://10"})

    @patch("features.menus.injector.graphql_request")
    def test_fetch_policy_gids_maps_type_to_gid(self, mock_gql):
        mock_gql.return_value = {"data": {"shop": {"shopPolicies": [
            {"type": "REFUND_POLICY", "id": "gid://30"},
            {"type": "PRIVACY_POLICY", "id": "gid://31"},
        ]}}}
        result = _fetch_policy_gids("http://base", {})

        self.assertEqual(result["REFUND_POLICY"], "gid://30")
        self.assertEqual(result["PRIVACY_POLICY"], "gid://31")

    @patch("features.menus.injector.graphql_request")
    def test_fetch_policy_gids_returns_empty_on_error(self, mock_gql):
        mock_gql.side_effect = Exception("boom")
        result = _fetch_policy_gids("http://base", {})

        self.assertEqual(result, {})


class TestFetchMenuGid(unittest.TestCase):
    @patch("features.menus.injector.graphql_request")
    def test_finds_menu_by_handle(self, mock_gql):
        mock_gql.return_value = {"data": {"menus": {
            "nodes": [{"id": "gid://m1", "handle": "main-menu", "title": "Main"}],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }}}
        result = fetch_menu_gid("main-menu", "http://base", {})

        self.assertEqual(result, "gid://m1")

    @patch("features.menus.injector.graphql_request")
    def test_returns_none_when_absent(self, mock_gql):
        mock_gql.return_value = {"data": {"menus": {
            "nodes": [{"id": "gid://m1", "handle": "footer", "title": "Footer"}],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }}}
        result = fetch_menu_gid("main-menu", "http://base", {})

        self.assertIsNone(result)


class TestBuildItems(unittest.TestCase):
    def test_collection_item_resolves_gid(self):
        cfg   = [{"title": "Griffoirs", "type": "collection", "handle": "griffoirs"}]
        items = _build_items(cfg, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "COLLECTION")
        self.assertEqual(items[0]["resourceId"], COLLECTION_MAP["griffoirs"])

    def test_http_item_uses_url(self):
        cfg   = [{"title": "Blog externe", "type": "http", "url": "https://ext.com"}]
        items = _build_items(cfg, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP)

        self.assertEqual(items[0]["url"], "https://ext.com")
        self.assertNotIn("resourceId", items[0])

    def test_frontpage_has_no_resource(self):
        cfg   = [{"title": "Accueil", "type": "frontpage"}]
        items = _build_items(cfg, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP)

        self.assertEqual(items[0]["type"], "FRONTPAGE")
        self.assertNotIn("resourceId", items[0])

    def test_shop_policy_resolves_gid(self):
        cfg   = [{"title": "Remboursement", "type": "shop_policy", "policy_type": "REFUND_POLICY"}]
        items = _build_items(cfg, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP)

        self.assertEqual(items[0]["resourceId"], POLICY_MAP["REFUND_POLICY"])

    def test_policy_prefix_type_resolves_gid(self):
        # Tolérance : ancien format backoffice "POLICY:<TYPE>" → SHOP_POLICY
        cfg   = [{"title": "Remboursement", "type": "POLICY:REFUND_POLICY"}]
        items = _build_items(cfg, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP)

        self.assertEqual(items[0]["type"], "SHOP_POLICY")
        self.assertEqual(items[0]["resourceId"], POLICY_MAP["REFUND_POLICY"])

    def test_unknown_handle_is_skipped(self):
        cfg   = [{"title": "X", "type": "collection", "handle": "inexistant"}]
        items = _build_items(cfg, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP)

        self.assertEqual(items, [])

    def test_unknown_type_is_skipped(self):
        cfg   = [{"title": "X", "type": "n_importe_quoi"}]
        items = _build_items(cfg, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP)

        self.assertEqual(items, [])

    def test_http_without_url_is_skipped(self):
        cfg   = [{"title": "X", "type": "http"}]
        items = _build_items(cfg, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP)

        self.assertEqual(items, [])

    def test_nested_items_are_built(self):
        cfg = [{
            "title": "Boutique", "type": "catalog",
            "items": [{"title": "Griffoirs", "type": "collection", "handle": "griffoirs"}],
        }]
        items = _build_items(cfg, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP)

        self.assertIn("items", items[0])
        self.assertEqual(items[0]["items"][0]["resourceId"], COLLECTION_MAP["griffoirs"])

    def test_depth_limit_stops_recursion(self):
        # 4 niveaux imbriqués — le 4ème (depth >= 3) doit être coupé
        deep = {"title": "L4", "type": "catalog"}
        cfg  = [{"title": "L1", "type": "catalog", "items": [
                    {"title": "L2", "type": "catalog", "items": [
                        {"title": "L3", "type": "catalog", "items": [deep]}]}]}]
        items = _build_items(cfg, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP)

        l3 = items[0]["items"][0]["items"][0]
        self.assertNotIn("items", l3)


class TestUpsertMenu(unittest.TestCase):
    MENU_CFG = {
        "title": "Menu principal", "handle": "main-menu",
        "items": [{"title": "Griffoirs", "type": "collection", "handle": "griffoirs"}],
    }

    @patch("features.menus.injector.fetch_menu_gid", return_value=None)
    @patch("features.menus.injector._create_menu")
    def test_creates_when_menu_absent(self, mock_create, mock_fetch):
        result = upsert_menu(self.MENU_CFG, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP, "http://base", {})

        mock_create.assert_called_once()
        self.assertEqual(result["statut"], "CRÉÉ")
        self.assertEqual(result["items_count"], 1)

    @patch("features.menus.injector.fetch_menu_gid", return_value="gid://existing")
    @patch("features.menus.injector._update_menu")
    def test_updates_when_menu_exists(self, mock_update, mock_fetch):
        result = upsert_menu(self.MENU_CFG, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP, "http://base", {})

        mock_update.assert_called_once()
        self.assertEqual(result["statut"], "MIS À JOUR")

    @patch("features.menus.injector.fetch_menu_gid", return_value=None)
    @patch("features.menus.injector._create_menu")
    def test_error_when_no_valid_items(self, mock_create, mock_fetch):
        cfg = {"title": "Vide", "handle": "vide",
               "items": [{"title": "X", "type": "collection", "handle": "inexistant"}]}

        result = upsert_menu(cfg, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP, "http://base", {})

        mock_create.assert_not_called()
        self.assertEqual(result["statut"], "ERREUR")

    @patch("features.menus.injector.fetch_menu_gid", return_value=None)
    @patch("features.menus.injector._create_menu", side_effect=Exception("menuCreate boom"))
    def test_returns_error_dict_on_exception(self, mock_create, mock_fetch):
        result = upsert_menu(self.MENU_CFG, COLLECTION_MAP, PAGE_MAP, BLOG_MAP, POLICY_MAP, "http://base", {})

        self.assertEqual(result["statut"], "ERREUR")
        self.assertIn("boom", result["erreur"])


if __name__ == "__main__":
    unittest.main()
