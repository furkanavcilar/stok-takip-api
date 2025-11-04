import os
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

ZENROWS_APIKEY = os.getenv("ZENROWS_APIKEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

def _zenrows_get(url: str, js_render: bool = True, wait: int = 2000) -> str:
    """ZenRows ile JS render edilmiş HTML getir (gerekirse)."""
    if ZENROWS_APIKEY:
        api = "https://api.zenrows.com/v1/"
        params = {
            "apikey": ZENROWS_APIKEY,
            "url": url,
            "js_render": "true" if js_render else "false",
            "wait": str(wait),
        }
        try:
            r = requests.get(api, params=params, headers=HEADERS, timeout=40)
            r.raise_for_status()
            return r.text
        except Exception:
            pass

    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def _search_product_api(sku: str) -> str | None:
    """
    Zara'nın dahili arama API'sine direkt istek at.
    Arama sonuçlarından productId alır.
    """
    search_api = f"https://www.zara.com/tr/tr/search?searchTerm={requests.utils.quote(sku)}"
    try:
        html = _zenrows_get(search_api, js_render=True, wait=3000)
    except Exception:
        return None

    # Zara artık sonuçları <script id="__NEXT_DATA__"> içinde JSON olarak saklıyor.
    soup = BeautifulSoup(html, "html.parser")
    data_script = soup.find("script", id="__NEXT_DATA__")
    if not data_script or not data_script.string:
        return None

    text = data_script.string
    match = re.search(r'"productId":"(\d+)"', text)
    if not match:
        return None

    product_id = match.group(1)
    return f"https://www.zara.com/tr/tr/p{product_id}.html"


def _parse_in_stock_from_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True).lower()

    # JSON script içinde stok bilgisi ara
    for s in soup.find_all("script"):
        content = s.string or ""
        if not isinstance(content, str):
            continue
        lc = content.lower()
        if '"in_stock":true' in lc or '"in_stock": true' in lc:
            return {"ok": True, "in_stock": True}
        if '"availability":"in stock"' in lc or '"availability":"available"' in lc:
            return {"ok": True, "in_stock": True}
        if '"in_stock":false' in lc or '"in_stock": false' in lc:
            return {"ok": True, "in_stock": False}
        if '"availability":"out of stock"' in lc or '"availability":"unavailable"' in lc:
            return {"ok": True, "in_stock": False}

    # Fallback metin kontrolü
    if any(w in text for w in ["stokta yok", "tükendi", "out of stock", "ürün bulunamadı"]):
        return {"ok": True, "in_stock": False}
    if any(w in text for w in ["sepete ekle", "add to bag", "add to cart", "stoğa eklendi"]):
        return {"ok": True, "in_stock": True}

    return {"ok": False, "in_stock": None, "error": "stok durum belirsiz"}


def check_stock_by_sku(sku: str) -> dict:
    sku = (sku or "").strip()
    if not sku:
        return {"ok": False, "error": "SKU boş"}

    product_url = _search_product_api(sku)
    if not product_url:
        return {"ok": False, "error": "Ürün bulunamadı (productId alınamadı)", "searched_sku": sku}

    try:
        html = _zenrows_get(product_url, js_render=True, wait=2500)
    except requests.HTTPError as e:
        return {"ok": False, "error": f"HTTP hata: {e}", "url": product_url, "searched_sku": sku}
    except Exception as e:
        return {"ok": False, "error": f"İndirme hatası: {e}", "url": product_url, "searched_sku": sku}

    parsed = _parse_in_stock_from_html(html)
    parsed["url"] = product_url
    parsed["searched_sku"] = sku
    return parsed


def check_stock_by_code(code: str) -> dict:
    code = (code or "").strip()
    if not re.fullmatch(r"\d{6,}", code):
        return check_stock_by_sku(code)

    url = f"https://www.zara.com/tr/tr/p{code}.html"
    try:
        html = _zenrows_get(url, js_render=True, wait=2500)
        parsed = _parse_in_stock_from_html(html)
        parsed["url"] = url
        parsed["searched_code"] = code
        return parsed
    except Exception as e:
        return {"ok": False, "error": f"Ürün bulunamadı veya erişilemedi: {e}", "searched_code": code}
