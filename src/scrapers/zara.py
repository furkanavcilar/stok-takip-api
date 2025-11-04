# src/scrapers/zara.py
import os
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ZenRows anahtarı Railway Variables'dan gelecek
ZENROWS_APIKEY = os.getenv("ZENROWS_APIKEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117 Safari/537.36"
}

def _zenrows_get(url: str, js_render: bool = True, wait: int = 2000) -> str:
    """
    ZenRows üzerinden (JS render'lı) HTML çek. Başarısız olursa normal GET'e düş.
    ZenRows dashboard örneğinde param ismi 'js_render' olarak veriliyor.
    """
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
            pass  # fallback

    # fallback: normal request
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def _find_product_url_from_search(sku: str) -> str | None:
    """
    Zara TR aramasından SKU'ya uygun ürün sayfasını bul.
    Çoğu sayfada ürün linkleri /pXXXXXXXX.html ile gider.
    """
    search_url = f"https://www.zara.com/tr/tr/search?searchTerm={requests.utils.quote(sku)}"
    html = _zenrows_get(search_url, js_render=True, wait=2500)
    soup = BeautifulSoup(html, "html.parser")

    # /p########.html kalıplı link ara
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"/p\d+\.html", href):
            if href.startswith("http"):
                return href
            return "https://www.zara.com" + href
    return None


def _parse_in_stock_from_html(html: str) -> dict:
    """
    Heuristik: sayfadaki script/text içinden stok var mı yok mu anlamaya çalış.
    Mümkün olduğunca 'in_stock', 'availability', 'add to bag' gibi ipuçlarını tarar.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True).lower()

    # Script bloklarında stok/availability sinyali ara
    for s in soup.find_all("script"):
        content = s.string or ""
        if not isinstance(content, str):
            continue
        lc = content.lower()

        # Pozitif sinyal
        if '"in_stock":true' in lc or '"in_stock": true' in lc:
            return {"ok": True, "in_stock": True}
        if '"availability":"in stock"' in lc or '"availability":"available"' in lc:
            return {"ok": True, "in_stock": True}

        # Negatif sinyal
        if '"in_stock":false' in lc or '"in_stock": false' in lc:
            return {"ok": True, "in_stock": False}
        if '"availability":"out of stock"' in lc or '"availability":"unavailable"' in lc:
            return {"ok": True, "in_stock": False}

    # Metin üzerindeki ipuçları
    neg_words = ["stokta yok", "tükendi", "out of stock", "ürün bulunamadı"]
    if any(w in text for w in neg_words):
        return {"ok": True, "in_stock": False}

    pos_words = ["sepete ekle", "add to bag", "add to cart", "stoğa eklendi"]
    if any(w in text for w in pos_words):
        return {"ok": True, "in_stock": True}

    # kesin değil
    return {"ok": False, "in_stock": None, "error": "stok durum belirsiz"}


def check_stock_by_sku(sku: str) -> dict:
    sku = (sku or "").strip()
    if not sku:
        return {"ok": False, "error": "SKU boş"}

    product_url = _find_product_url_from_search(sku)
    if not product_url:
        return {"ok": False, "error": "Ürün bulunamadı (search ile p*.html linki bulunamadı)", "searched_sku": sku}

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
    """
    Eğer direkt ürün kodun varsa (p########.html gibi) doğrudan sayfaya gitmeyi dene.
    """
    code = (code or "").strip()
    # code "00526310" gibi ise pXXXX.html kalıbına çevir:
    # emin değilsen önce search'ten dene:
    if not re.fullmatch(r"\d{6,}", code):
        # Kod temiz değilse önce search
        return check_stock_by_sku(code)

    candidates = [
        f"https://www.zara.com/tr/tr/p{code}.html",
        f"https://www.zara.com/p{code}.html",
    ]
    last_err = None
    for url in candidates:
        try:
            html = _zenrows_get(url, js_render=True, wait=2500)
            parsed = _parse_in_stock_from_html(html)
            parsed["url"] = url
            parsed["searched_code"] = code
            return parsed
        except Exception as e:
            last_err = e
            continue
    return {"ok": False, "error": f"Ürün bulunamadı veya erişilemedi: {last_err}", "searched_code": code}
