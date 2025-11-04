import json
import re
from typing import Any, Dict
import requests
from bs4 import BeautifulSoup
import os

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/119.0.0.0 Safari/537.36"
)

ZENROWS_API_KEY = os.getenv("ZENROWS_API_KEY")

def _fetch_html(url: str, use_zenrows: bool = True) -> str:
    headers = {"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"}

    if use_zenrows and ZENROWS_API_KEY:
        zen_url = f"https://api.zenrows.com/v1/?apikey={ZENROWS_API_KEY}&url={url}&js_render=true"
        resp = requests.get(zen_url, headers=headers, timeout=30, allow_redirects=True)
        # Zara 404 dönerse ZenRows bazen bozuk sayfa verir, fallback'e geçelim
        if resp.status_code == 404 or len(resp.text) < 5000:
            return _fetch_html(url, use_zenrows=False)
        resp.raise_for_status()
        return resp.text
    else:
        resp = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        resp.raise_for_status()
        return resp.text


def check_stock_by_code(product_code: str) -> Dict[str, Any]:
    """Zara ürün kodundan stok durumunu kontrol eder."""
    base_urls = [
        f"https://www.zara.com/tr/tr/p{product_code}.html",
        f"https://www.zara.com/tr/tr/product/{product_code}.html",
        f"https://www.zara.com/tr/tr/-p{product_code}.html"
    ]

    last_error = None
    for url in base_urls:
        try:
            html = _fetch_html(url)
            low_html = html.lower()
            if any(k in low_html for k in ["bana bildir", "coming soon", "out of stock", "tükendi"]):
                return {"ok": True, "in_stock": False, "url": url}
            if any(k in low_html for k in ["sepete ekle", "add to bag", "add to cart"]):
                return {"ok": True, "in_stock": True, "url": url}
            # stok bilgisini bulamadıysa ama sayfa açıldıysa
            return {"ok": True, "in_stock": None, "url": url, "error": "stok bilgisi tespit edilemedi"}
        except Exception as e:
            last_error = str(e)
            continue

    return {"ok": False, "error": f"Ürün sayfası bulunamadı: {last_error}", "url": base_urls[-1]}


def check_stock_by_sku(sku: str) -> Dict[str, Any]:
    """Zara SKU → ürün kodu eşleşmesini yap ve stok durumunu kontrol et."""
    sku_map = {
        "0230/010/999": "20230010",  # Leather Fever parfüm
        "0052/6310": "00526310",     # Kontrast yakalı polo sweatshirt
    }

    product_code = sku_map.get(sku)
    if not product_code:
        return {"ok": False, "error": f"{sku} için eşleşen ürün kodu yok", "url": None}

    result = check_stock_by_code(product_code)
    result["product_id"] = product_code
    result["searched_sku"] = sku
    return result
