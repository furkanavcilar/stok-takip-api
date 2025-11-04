import requests
from bs4 import BeautifulSoup
import re
import json

def check_stock_by_code(code: str):
    """
    Zara ürün kodu ile stok bilgisini kontrol eder (örnek: 20230010)
    """
    url = f"https://www.zara.com/tr/tr/p{code}.html"
    return _check_stock(url, code)

def check_stock_by_sku(sku: str):
    """
    Zara ürün SKU (örnek: 0052/6310) ile stok bilgisini kontrol eder
    """
    clean = sku.replace("/", "").replace("-", "")
    url = f"https://www.zara.com/tr/tr/p{clean}.html"
    result = _check_stock(url, sku)

    # Eğer 404 dönerse, SKU için arama endpointini dene
    if not result["ok"]:
        result = _search_and_check_stock(sku)
    return result

def _search_and_check_stock(sku: str):
    """
    SKU ile Zara'da arama yapar ve stok bilgisini çeker.
    """
    try:
        search_url = f"https://www.zara.com/tr/tr/search?searchTerm={sku}"
        r = requests.get(search_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code != 200:
            return {"ok": False, "error": f"Arama başarısız (HTTP {r.status_code})"}

        # ProductId bul
        match = re.search(r'"productId":"(\d+)"', r.text)
        if not match:
            return {"ok": False, "error": "Ürün bulunamadı (productId tespit edilemedi)"}

        product_id = match.group(1)
        url = f"https://www.zara.com/tr/tr/p{product_id}.html"
        return _check_stock(url, sku)
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _check_stock(url: str, ref: str):
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code != 200:
            return {"ok": False, "error": f"Ürün bulunamadı (HTTP {resp.status_code})", "url": url}

        match = re.search(r"window\.viewData\s*=\s*(\{.*?\});", resp.text)
        if not match:
            return {"ok": False, "error": "viewData bulunamadı", "url": url}

        data = json.loads(match.group(1))

        stock_info = []
        for product in data.get("product", {}).get("detail", []):
            color = product.get("colorName")
            for size in product.get("sizes", []):
                stock_info.append({
                    "color": color,
                    "size": size.get("name"),
                    "availability": size.get("availability"),
                })

        in_stock = any(s["availability"] == "in_stock" for s in stock_info)
        return {
            "ok": True,
            "in_stock": in_stock,
            "url": url,
            "searched": ref,
            "variants": stock_info
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}
