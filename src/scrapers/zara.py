# src/scrapers/zara.py
import os
import re
import json
import time
from typing import Dict, Any, Optional

import requests


def _fetch(url: str) -> str:
    """
    HTML getir. ZENROWS_API_KEY varsa ZenRows üzerinden, yoksa direkt istek at.
    """
    zenrows_key = os.getenv("ZENROWS_API_KEY", "").strip()
    headers = {
        # Basit bir tarayıcı gibi görünelim
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    if zenrows_key:
        api = "https://api.zenrows.com/v1/"
        params = {
            "apikey": zenrows_key,
            "url": url,
            # JS render Zara için çoğu durumda gerekli değil, ama hazır dursun
            "js_render": "false",
        }
        r = requests.get(api, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        return r.text

    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def _extract_viewdata(html: str) -> Optional[Dict[str, Any]]:
    """
    window.zara.viewData = {...}; bloğunu çıkar ve JSON'a çevir.
    Farklı minify biçimlerine karşı esnek regex.
    """
    # ; ile biten tek satırlık atamalar için esnek bir regex
    m = re.search(
        r"window\.zara\.viewData\s*=\s*(\{.*?\})\s*;",
        html,
        re.DOTALL,
    )
    if not m:
        return None
    raw = m.group(1)

    # bazen trailing virgüller vb. olabiliyor; önce doğrudan dene
    try:
        return json.loads(raw)
    except Exception:
        # JSON temizlemeye küçük bir deneme daha
        cleaned = re.sub(r",\s*}", "}", raw)
        cleaned = re.sub(r",\s*]", "]", cleaned)
        return json.loads(cleaned)


def _decide_stock(data: Dict[str, Any]) -> Optional[bool]:
    """
    viewData içinden varyantları bul ve availability durumuna göre stok var/yok kararı ver.
    True/False döner; bulamazsak None.
    """
    try:
        product = data["product"]["detail"]
        colors = product.get("colors", [])
        sizes_accum = []

        for c in colors:
            # renklerin altındaki beden listeleri
            sizes = c.get("sizes") or []
            sizes_accum.extend(sizes)

        if not sizes_accum:
            return None

        # availability alanı genelde: "in_stock", "out_of_stock", "coming_soon"
        for s in sizes_accum:
            availability = (s.get("availability") or "").lower()
            # stok varsa direkt True
            if availability in ("in_stock", "low_stock", "back_soon", "coming_soon"):
                return True

        # hiçbiri stokta değilse:
        return False
    except Exception:
        return None


def normalize_sku_to_pid(sku: str) -> str:
    """
    '0052/6310' -> '00526310'
    """
    return re.sub(r"[^\d]", "", sku).strip()


def check_stock(sku: str) -> Dict[str, Any]:
    """
    Dışarıya açık fonksiyon: SKU alır, URL oluşturur, HTML'i çeker ve stok durumunu döndürür.
    """
    product_id = normalize_sku_to_pid(sku)
    url = f"https://www.zara.com/tr/tr/-p{product_id}.html"

    try:
        html = _fetch(url)
    except Exception as e:
        return {
            "ok": False,
            "error": f"istek hatası: {e}",
            "url": url,
            "product_id": product_id,
            "searched_sku": sku,
        }

    view = _extract_viewdata(html)
    if not view:
        return {
            "ok": True,
            "in_stock": None,
            "error": "viewData bulunamadı",
            "url": url,
            "product_id": product_id,
            "searched_sku": sku,
        }

    in_stock = _decide_stock(view)
    return {
        "ok": True,
        "in_stock": in_stock,  # True / False / None
        "url": url,
        "product_id": product_id,
        "searched_sku": sku,
    }
