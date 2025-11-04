# src/scrapers/zara.py
import os
import re
import json
from typing import Dict, Any, Optional
import requests


def _fetch(url: str) -> str:
    """
    HTML getir. ZenRows varsa onu kullan, yoksa doğrudan requests.
    """
    zenrows_key = os.getenv("ZENROWS_API_KEY", "").strip()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    if zenrows_key:
        api = "https://api.zenrows.com/v1/"
        params = {"apikey": zenrows_key, "url": url, "js_render": "false"}
        r = requests.get(api, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        return r.text

    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def _extract_viewdata(html: str) -> Optional[Dict[str, Any]]:
    """
    Zara sayfasındaki window.zara.viewData JavaScript nesnesini çıkarır.
    """
    m = re.search(r"window\.zara\.viewData\s*=\s*(\{.*?\})\s*;", html, re.DOTALL)
    if not m:
        return None
    raw = m.group(1)

    try:
        return json.loads(raw)
    except Exception:
        cleaned = re.sub(r",\s*}", "}", raw)
        cleaned = re.sub(r",\s*]", "]", cleaned)
        return json.loads(cleaned)


def _decide_stock(data: Dict[str, Any]) -> Optional[bool]:
    """
    Zara ürününün stok durumunu viewData JSON'undan belirler.
    """
    try:
        product = data["product"]["detail"]
        colors = product.get("colors", [])
        sizes_accum = []
        for c in colors:
            sizes = c.get("sizes") or []
            sizes_accum.extend(sizes)

        if not sizes_accum:
            return None

        for s in sizes_accum:
            availability = (s.get("availability") or "").lower()
            if availability in ("in_stock", "low_stock", "back_soon", "coming_soon"):
                return True

        return False
    except Exception:
        return None


def _normalize(code_or_sku: str) -> str:
    """'0052/6310' → '00526310'"""
    return re.sub(r"[^\d]", "", code_or_sku or "").strip()


# =======================================================
# === DIŞA AÇIK FONKSİYONLAR (main.py bunları çağırıyor) ===
# =======================================================

def check_stock_by_sku(sku: str) -> Dict[str, Any]:
    product_id = _normalize(sku)
    url = f"https://www.zara.com/tr/tr/-p{product_id}.html"
    return _check(url, product_id, sku)


def check_stock_by_code(code: str) -> Dict[str, Any]:
    product_id = _normalize(code)
    url = f"https://www.zara.com/tr/tr/-p{product_id}.html"
    return _check(url, product_id, code)


# =======================================================

def _check(url: str, product_id: str, original: str) -> Dict[str, Any]:
    """HTML’i çek, viewData’yı parse et, stok durumunu belirle."""
    try:
        html = _fetch(url)
    except Exception as e:
        return {
            "ok": False,
            "error": f"istek hatası: {e}",
            "url": url,
            "product_id": product_id,
            "searched": original,
        }

    view = _extract_viewdata(html)
    if not view:
        return {
            "ok": True,
            "in_stock": None,
            "error": "viewData bulunamadı",
            "url": url,
            "product_id": product_id,
            "searched": original,
        }

    in_stock = _decide_stock(view)
    return {
        "ok": True,
        "in_stock": in_stock,
        "url": url,
        "product_id": product_id,
        "searched": original,
    }
