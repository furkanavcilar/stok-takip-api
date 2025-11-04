import os
import re
import json
import urllib.parse
import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}
ZENROWS_KEY = os.getenv("ZENROWS_API_KEY", "").strip()

def check_stock_by_code(code: str):
    """
    Zara ürün kodu (productId) ile kontrol: ör. 20230010
    """
    pid = re.sub(r"\D+", "", code)
    url = f"https://www.zara.com/tr/tr/p{pid}.html"
    return _check_stock(url, ref=code)

def check_stock_by_sku(sku: str):
    """
    Zara SKU (ör. 0052/6310) ile kontrol. SKU'dan productId türetmeyi dener,
    olmadıysa arama sayfasından /pXXXXXXXX.html linkini yakalar.
    """
    clean = re.sub(r"\D+", "", sku)  # 00526310
    # 1) Doğrudan p{clean}.html dene
    first_try = _check_stock(f"https://www.zara.com/tr/tr/p{clean}.html", ref=sku)
    if first_try.get("ok"):
        return first_try

    # 2) Aramadan pXXXXXXXX.html yakala
    pid = _find_product_id_from_search(sku)
    if not pid:
        return {"ok": False, "error": "Ürün bulunamadı (productId tespit edilemedi)"}

    return _check_stock(f"https://www.zara.com/tr/tr/p{pid}.html", ref=sku)

# ---------- helpers ----------

def _fetch(url: str, use_zenrows_if_needed: bool = True):
    """
    URL'i getirir. 200 dönmez veya challenge/404 olursa ve ZENROWS_API_KEY varsa
    aynı isteği ZenRows üzerinden dener.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200 and r.text:
            return r
        # Uygun değilse ZenRows deneyelim
        if use_zenrows_if_needed and ZENROWS_KEY:
            zr = _fetch_via_zenrows(url)
            if zr is not None:
                return zr
        return r
    except Exception:
        if use_zenrows_if_needed and ZENROWS_KEY:
            zr = _fetch_via_zenrows(url)
            return zr
        raise

def _fetch_via_zenrows(url: str):
    try:
        zurl = (
            "https://api.zenrows.com/v1/?"
            + urllib.parse.urlencode(
                {
                    "apikey": ZENROWS_KEY,
                    "url": url,
                    # rendering genelde viewData’yı garanti ediyor
                    "js_render": "true",
                }
            )
        )
        zr = requests.get(zurl, headers=HEADERS, timeout=25)
        return zr
    except Exception:
        return None

def _find_product_id_from_search(term: str) -> str | None:
    """
    Arama sayfasından ilk /pXXXXXXXX.html linkini yakalar.
    """
    q = urllib.parse.quote(term)
    search_url = f"https://www.zara.com/tr/tr/search?searchTerm={q}"
    r = _fetch(search_url)
    if not r or r.status_code != 200:
        return None

    html = r.text
    # 1) Doğrudan pXXXXXXXX.html desenini ara
    m = re.search(r"/tr/tr/p(\d{6,12})\.html", html)
    if m:
        return m.group(1)

    # 2) Bazı şablonlarda "productId":"12345678" geçer
    m2 = re.search(r'"productId"\s*:\s*"(\d{6,12})"', html)
    if m2:
        return m2.group(1)

    # 3) Sayfayı BeautifulSoup ile tara; linklerden yakala
    try:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            hm = re.search(r"/tr/tr/p(\d{6,12})\.html", a["href"])
            if hm:
                return hm.group(1)
    except Exception:
        pass

    return None

def _extract_view_data(html: str) -> dict | None:
    """
    window.viewData = {...}; bloğunu JSON’a çevirir.
    """
    # En sağlamı: script blokları arasında 'viewData' geçen bloğu bulup JSON’u çekmek
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        txt = script.string or script.text or ""
        if "window.viewData" in txt:
            m = re.search(r"window\.viewData\s*=\s*(\{.*?\});", txt, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    # Bazı durumlarda trailing commas vs. olabilir, ikinci deneme:
                    cleaned = m.group(1)
                    cleaned = re.sub(r",\s*}", "}", cleaned)
                    cleaned = re.sub(r",\s*]", "]", cleaned)
                    return json.loads(cleaned)
    # Regex ile tüm sayfada son çare:
    m2 = re.search(r"window\.viewData\s*=\s*(\{.*?\});", html, re.DOTALL)
    if m2:
        try:
            return json.loads(m2.group(1))
        except Exception:
            pass
    return None

def _check_stock(product_url: str, ref: str):
    """
    Ürün sayfasını çekip viewData’dan varyant/availability çıkarır.
    """
    try:
        resp = _fetch(product_url)
        if not resp or resp.status_code != 200:
            return {
                "ok": False,
                "error": f"Ürün bulunamadı (HTTP {getattr(resp, 'status_code', '??')})",
                "url": product_url,
            }

        data = _extract_view_data(resp.text)
        if not data:
            return {"ok": False, "error": "viewData bulunamadı", "url": product_url}

        variants = []
        product_detail = data.get("product", {}).get("detail", [])
        for prod in product_detail:
            color = prod.get("colorName")
            for size in prod.get("sizes", []):
                variants.append(
                    {
                        "color": color,
                        "size": size.get("name"),
                        "availability": size.get("availability"),
                    }
                )

        in_stock = any(v.get("availability") == "in_stock" for v in variants)
        return {
            "ok": True,
            "in_stock": in_stock,
            "searched": ref,
            "url": product_url,
            "variants": variants,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "url": product_url}
