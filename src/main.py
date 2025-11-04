from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# ✅ Uygulama nesnesi
app = FastAPI(title="Stok Takip API")

@app.get("/")
def root():
    return {"status": "ok", "message": "Stok Takip API çalışıyor"}

# Zara scraper import (deploy sonrası test için geçici hata önleme)
try:
    from src.scrapers.zara import check_stock_by_code, check_stock_by_sku
except Exception as e:
    print("⚠️ Zara scraper import edilemedi:", e)
    def check_stock_by_code(code): return {"ok": False, "error": "scraper import hatası"}
    def check_stock_by_sku(sku): return {"ok": False, "error": "scraper import hatası"}

@app.get("/check_stock")
def check_stock(
    brand: str,
    code: Optional[str] = Query(None),
    sku: Optional[str] = Query(None)
):
    brand = brand.strip().lower()
    if brand != "zara":
        raise HTTPException(status_code=400, detail=f"Sadece 'zara' destekleniyor (gelen: {brand})")

    if sku:
        return check_stock_by_sku(sku)
    elif code:
        return check_stock_by_code(code)
    else:
        raise HTTPException(status_code=400, detail="sku veya code parametresi gerekli")


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
            results.append({"ok": False, "error": "Marka desteklenmiyor", "brand": it.brand})
            continue
        if it.sku:
            r = check_stock_by_sku(it.sku)
        elif it.code:
            r = check_stock_by_code(it.code)
        else:
            r = {"ok": False, "error": "sku veya code yok"}
        results.append(r)
    return {"count": len(results), "results": results}
