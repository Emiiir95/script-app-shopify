"""
Tests unitaires — shopify/client.py

Couvre : shopify_headers, shopify_base_url, shopify_get, shopify_get_paginated,
         shopify_post, shopify_put, graphql_request
"""
import unittest
from unittest.mock import patch, MagicMock

import requests

from shopify.client import (
    SHOPIFY_API_VERSION,
    graphql_request,
    shopify_base_url,
    shopify_get,
    shopify_get_paginated,
    shopify_headers,
    shopify_post,
    shopify_put,
)


class TestShopifyHeaders(unittest.TestCase):
    def test_returns_token_and_content_type(self):
        h = shopify_headers("mytoken123")
        self.assertEqual(h["X-Shopify-Access-Token"], "mytoken123")
        self.assertEqual(h["Content-Type"], "application/json")


class TestShopifyBaseUrl(unittest.TestCase):
    def test_uses_default_api_version(self):
        url = shopify_base_url("mystore.myshopify.com")
        self.assertEqual(url, f"https://mystore.myshopify.com/admin/api/{SHOPIFY_API_VERSION}")

    def test_custom_version(self):
        url = shopify_base_url("mystore.myshopify.com", "2025-01")
        self.assertEqual(url, "https://mystore.myshopify.com/admin/api/2025-01")


class TestShopifyGet(unittest.TestCase):
    @patch("shopify.client.requests.get")
    def test_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"products": []}
        mock_get.return_value = mock_resp

        result = shopify_get("http://example.com", {})
        self.assertEqual(result, {"products": []})

    @patch("shopify.client.time.sleep")
    @patch("shopify.client.requests.get")
    def test_rate_limit_retries_and_succeeds(self, mock_get, mock_sleep):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "2"}

        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"ok": True}

        mock_get.side_effect = [rate_limited, success]
        result = shopify_get("http://example.com", {})

        self.assertEqual(result, {"ok": True})
        mock_sleep.assert_called_with(2)

    @patch("shopify.client.time.sleep")
    @patch("shopify.client.requests.get")
    def test_rate_limit_parses_float_retry_after(self, mock_get, mock_sleep):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "2.0"}

        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {}

        mock_get.side_effect = [rate_limited, success]
        shopify_get("http://example.com", {})
        mock_sleep.assert_called_with(2)  # int(float("2.0")) == 2

    @patch("shopify.client.time.sleep")
    @patch("shopify.client.requests.get")
    def test_network_error_retries_and_succeeds(self, mock_get, mock_sleep):
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"ok": True}

        mock_get.side_effect = [requests.exceptions.ConnectionError("fail"), success]
        result = shopify_get("http://example.com", {}, max_retries=2)

        self.assertEqual(result, {"ok": True})

    @patch("shopify.client.time.sleep")
    @patch("shopify.client.requests.get")
    def test_max_retries_exceeded_raises(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.exceptions.ConnectionError("always fails")

        with self.assertRaises(requests.exceptions.ConnectionError):
            shopify_get("http://example.com", {}, max_retries=2)


class TestShopifyGetPaginated(unittest.TestCase):
    @patch("shopify.client.requests.get")
    def test_returns_json_and_link_header(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"products": [{"id": 1}]}
        mock_resp.headers.get.return_value = '<https://example.com/next>; rel="next"'
        mock_get.return_value = mock_resp

        data, link = shopify_get_paginated("http://example.com", {})

        self.assertEqual(data["products"][0]["id"], 1)
        self.assertIn('rel="next"', link)

    @patch("shopify.client.requests.get")
    def test_empty_link_header(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"products": []}
        mock_resp.headers.get.return_value = ""
        mock_get.return_value = mock_resp

        data, link = shopify_get_paginated("http://example.com", {})
        self.assertEqual(link, "")

    @patch("shopify.client.time.sleep")
    @patch("shopify.client.requests.get")
    def test_rate_limit_retries_and_parses_float(self, mock_get, mock_sleep):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "1.5"}

        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {}
        success.headers.get.return_value = ""

        mock_get.side_effect = [rate_limited, success]
        shopify_get_paginated("http://example.com", {})
        mock_sleep.assert_called_with(1)  # int(float("1.5")) == 1

    @patch("shopify.client.time.sleep")
    @patch("shopify.client.requests.get")
    def test_network_error_retries(self, mock_get, mock_sleep):
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {}
        success.headers.get.return_value = ""

        mock_get.side_effect = [requests.exceptions.Timeout(), success]
        shopify_get_paginated("http://example.com", {}, max_retries=2)


class TestShopifyPost(unittest.TestCase):
    @patch("shopify.client.requests.post")
    def test_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"created": True}
        mock_post.return_value = mock_resp

        result = shopify_post("http://example.com", {}, {"data": "x"})
        self.assertEqual(result, {"created": True})

    @patch("shopify.client.time.sleep")
    @patch("shopify.client.requests.post")
    def test_rate_limit_retries(self, mock_post, mock_sleep):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "3"}

        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {}

        mock_post.side_effect = [rate_limited, success]
        shopify_post("http://example.com", {}, {})
        mock_sleep.assert_called_with(3)

    @patch("shopify.client.time.sleep")
    @patch("shopify.client.requests.post")
    def test_max_retries_exceeded_raises(self, mock_post, mock_sleep):
        mock_post.side_effect = requests.exceptions.ConnectionError()

        with self.assertRaises(requests.exceptions.ConnectionError):
            shopify_post("http://example.com", {}, {}, max_retries=2)


class TestShopifyPut(unittest.TestCase):
    @patch("shopify.client.requests.put")
    def test_success(self, mock_put):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"updated": True}
        mock_put.return_value = mock_resp

        result = shopify_put("http://example.com", {}, {"data": "x"})
        self.assertEqual(result, {"updated": True})

    @patch("shopify.client.time.sleep")
    @patch("shopify.client.requests.put")
    def test_rate_limit_retries(self, mock_put, mock_sleep):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "1"}

        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {}

        mock_put.side_effect = [rate_limited, success]
        shopify_put("http://example.com", {}, {})
        mock_sleep.assert_called_with(1)


class TestGraphqlRequest(unittest.TestCase):
    BASE_URL = "https://mystore.myshopify.com/admin/api/2026-01"

    @patch("shopify.client.requests.post")
    def test_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"shop": {"name": "Test"}}}
        mock_post.return_value = mock_resp

        result = graphql_request(self.BASE_URL, {}, "{ shop { name } }")
        self.assertEqual(result["data"]["shop"]["name"], "Test")

    @patch("shopify.client.requests.post")
    def test_graphql_errors_raises(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"errors": [{"message": "Syntax error"}]}
        mock_post.return_value = mock_resp

        with self.assertRaises(Exception) as ctx:
            graphql_request(self.BASE_URL, {}, "{ bad query }")
        self.assertIn("GraphQL errors", str(ctx.exception))

    @patch("shopify.client.time.sleep")
    @patch("shopify.client.requests.post")
    def test_rate_limit_retries(self, mock_post, mock_sleep):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "2"}

        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"data": {}}

        mock_post.side_effect = [rate_limited, success]
        graphql_request(self.BASE_URL, {}, "{ shop { name } }")
        mock_sleep.assert_called_with(2)

    @patch("shopify.client.requests.post")
    def test_includes_variables_in_payload(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {}}
        mock_post.return_value = mock_resp

        graphql_request(self.BASE_URL, {}, "mutation { x }", variables={"key": "val"})
        call_payload = mock_post.call_args[1]["json"]
        self.assertIn("variables", call_payload)
        self.assertEqual(call_payload["variables"]["key"], "val")


if __name__ == "__main__":
    unittest.main()
