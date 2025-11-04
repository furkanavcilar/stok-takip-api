from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
from dotenv import load_dotenv

# Ortam değişkenlerini yükle
load_dotenv()

app = FastAPI(title="Stok Takip API")

@app.get("/")
def root():
    return {"status": "ok", "message": "Stok Takip API çalışıyor"}

# --- Zara scraper import ---
from .scrapers.zara import check_stock_by_code, check_stock_by_sku

# Tek ürün kontrolü (GET)
@app.get("/check_stock")
def check_stock(
    brand: str,
    code: Optional[str] = Query(None, description="Ürün kodu (örnek: 20230010)"),
    sku: Optional[str] = Query(None, description="Seri numarası (örnek: 0230/010/999)")
):
    brand = brand.strip().lower()
    if brand != "zara":
        raise HTTPException(status_code=400, detail=f"Şu anda sadece 'zara' destekleniyor. (Gelen: {brand})")

    if sku:
        result = check_stock_by_sku(sku)
        return result
    elif code:
        result = check_stock_by_code(code)
        return result
    else:
        raise HTTPException(status_code=400, detail="Lütfen 'sku' (seri no) veya 'code' parametresi gönderin.")


# ---------- Çoklu ürün kontrolü (POST) ----------
class BatchItem(BaseModel):
    brand: str
    sku: Optional[str] = None
    code: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

class BatchRequest(BaseModel):
    items: List[BatchItem]

@app.post("/check_batch")
def check_batch(req: BatchRequest):
    results = []
    for it in req.items:
        brand = (it.brand or "").strip().lower()

        if brand != "zara":
            results.append({
                "ok": False,
                "error": f"Marka desteklenmiyor: {it.brand}",
                "brand": it.brand,
                "sku": it.sku,
                "code": it.code,
                "meta": it.meta
            })
            continue

        if it.sku:
            r = check_stock_by_sku(it.sku)
        elif it.code:
            r = check_stock_by_code(it.code)
        else:
            r = {"ok": False, "error": "sku veya code verilmedi"}

        r["brand"] = it.brand
        r["sku"] = it.sku
        r["code"] = it.code
        r["meta"] = it.meta
        results.append(r)

    return {"count": len(results), "results": results}
