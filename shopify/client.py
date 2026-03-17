import requests
import time

from utils.logger import log

SHOPIFY_API_VERSION = "2026-01"


def shopify_headers(api_token):
    return {
        "X-Shopify-Access-Token": api_token,
        "Content-Type": "application/json",
    }


def shopify_base_url(store_url, api_version=SHOPIFY_API_VERSION):
    return f"https://{store_url}/admin/api/{api_version}"


def shopify_get(url, headers, params=None, max_retries=5):
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code == 429:
                wait = int(float(resp.headers.get("Retry-After", 2)))
                log(f"Rate limit Shopify GET — attente {wait}s (tentative {attempt+1})", "warning", also_print=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                log(f"Erreur réseau GET ({e}) — retry dans {wait}s", "warning")
                time.sleep(wait)
            else:
                raise
    raise Exception(f"Échec GET après {max_retries} tentatives : {url}")


def shopify_post(url, headers, payload, max_retries=5):
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 429:
                wait = int(float(resp.headers.get("Retry-After", 2)))
                log(f"Rate limit Shopify POST — attente {wait}s (tentative {attempt+1})", "warning", also_print=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                log(f"Erreur réseau POST ({e}) — retry dans {wait}s", "warning")
                time.sleep(wait)
            else:
                raise
    raise Exception(f"Échec POST après {max_retries} tentatives : {url}")


def shopify_put(url, headers, payload, max_retries=5):
    for attempt in range(max_retries):
        try:
            resp = requests.put(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 429:
                wait = int(float(resp.headers.get("Retry-After", 2)))
                log(f"Rate limit Shopify PUT — attente {wait}s (tentative {attempt+1})", "warning", also_print=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                log(f"Erreur réseau PUT ({e}) — retry dans {wait}s", "warning")
                time.sleep(wait)
            else:
                raise
    raise Exception(f"Échec PUT après {max_retries} tentatives : {url}")


def graphql_request(base_url, headers, query, variables=None, max_retries=5):
    store_url   = base_url.split("/admin/api/")[0]
    api_version = base_url.split("/admin/api/")[1]
    url = f"{store_url}/admin/api/{api_version}/graphql.json"
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    for attempt in range(max_retries):
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 429:
            wait = int(float(resp.headers.get("Retry-After", 2)))
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        if data.get("errors"):
            raise Exception(f"GraphQL errors : {data['errors']}")
        return data
    raise Exception("Échec requête GraphQL après plusieurs tentatives.")
