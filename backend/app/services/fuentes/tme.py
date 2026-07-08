"""Fuente: TME (Transfer Multisort Elektronik) — distribuidor europeo."""
import hashlib
import hmac
import urllib.parse
import httpx

TASA_EUR_CLP = 1040
TME_BASE = "https://api.tme.eu"


def _tme_signature(api_secret: str, url: str, params: dict) -> str:
    sorted_params = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in sorted(params.items()))
    base = f"POST&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(sorted_params, safe='')}"
    sig = hmac.new(api_secret.encode(), base.encode(), hashlib.sha1)
    return sig.hexdigest()


async def buscar_tme(query: str, max_results: int = 10, api_key: str = "", api_secret: str = "") -> list[dict]:
    if not api_key or not api_secret:
        return []
    try:
        url = f"{TME_BASE}/Products/Search.json"
        params = {
            "Token": api_key,
            "Language": "ES",
            "SearchPlain": query,
            "SearchWithStock": 0,
            "Country": "CL",
            "Currency": "EUR",
        }
        params["ApiSignature"] = _tme_signature(api_secret, url, params)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, data=params)
            if resp.status_code != 200:
                return []
            data = resp.json()

        results = []
        products = (data.get("Data") or {}).get("ProductList") or []
        for prod in products[:max_results]:
            prices = prod.get("Prices") or []
            precio_eur = None
            if prices:
                try:
                    precio_eur = float(prices[0].get("PriceValue", 0))
                except Exception:
                    pass

            # Price breaks por volumen
            precio_volumen = []
            for pb in prices:
                try:
                    precio_volumen.append({
                        "qty": int(pb.get("Amount", 1)),
                        "precio_eur": float(pb.get("PriceValue", 0)),
                        "precio_clp": round(float(pb.get("PriceValue", 0)) * TASA_EUR_CLP),
                    })
                except Exception:
                    pass

            # Stock
            stock = None
            try:
                stock = int(prod.get("Amount", 0)) or None
            except Exception:
                pass

            results.append({
                "titulo": prod.get("Description") or prod.get("Symbol") or query,
                "precio": round(precio_eur * TASA_EUR_CLP) if precio_eur else None,
                "moneda": "CLP" if precio_eur else None,
                "precio_original": precio_eur,
                "moneda_original": "EUR",
                "url": prod.get("ProductInformationPage", ""),
                "fuente": "tme",
                "fuente_label": "TME",
                "pais": "EU",
                "proveedor": "TME",
                "marca": prod.get("Producer"),
                "numero_parte": prod.get("Symbol"),
                "thumbnail": prod.get("Photo"),
                # Enriquecidos
                "descripcion": prod.get("Description"),
                "stock": stock,
                "stock_disponible": (stock or 0) > 0 if stock is not None else None,
                "cantidad_minima": prod.get("MinAmount"),
                "plazo_entrega_estimado": f"{prod.get('SupplierDeliveryTime')} días" if prod.get("SupplierDeliveryTime") else None,
                "categoria": prod.get("Category"),
                "precio_volumen": precio_volumen if len(precio_volumen) > 1 else None,
                "condicion": "nuevo",
            })
        return results
    except Exception as e:
        print(f"[TME] Error: {e}")
        return []
