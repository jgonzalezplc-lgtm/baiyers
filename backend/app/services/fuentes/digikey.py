"""Fuente: DigiKey — OAuth2 + Product Search API."""
import httpx
from typing import Optional

TASA_USD_CLP = 950

_token_cache: dict = {}


async def _get_token(client_id: str, client_secret: str) -> Optional[str]:
    """Obtiene access token via OAuth2 client credentials."""
    cached = _token_cache.get("digikey")
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.digikey.com/v1/oauth2/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "client_credentials",
                },
            )
            if resp.status_code == 200:
                token = resp.json().get("access_token")
                _token_cache["digikey"] = token
                return token
    except Exception as e:
        print(f"[DigiKey] Auth error: {e}")
    return None


async def buscar_digikey(query: str, max_results: int = 8, client_id: str = "", client_secret: str = "") -> list[dict]:
    if not client_id or not client_secret:
        return []
    try:
        token = await _get_token(client_id, client_secret)
        if not token:
            return []

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.digikey.com/products/v4/search/keyword",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-DIGIKEY-Client-Id": client_id,
                    "Content-Type": "application/json",
                },
                json={"Keywords": query, "Limit": max_results, "Offset": 0},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()

        results = []
        for prod in (data.get("Products") or [])[:max_results]:
            # Precio unitario
            precio_usd = None
            unit_price = prod.get("UnitPrice")
            if unit_price:
                try:
                    precio_usd = float(unit_price)
                except Exception:
                    pass

            # Price breaks por volumen
            precio_volumen = []
            for pb in (prod.get("PriceBreaks") or []):
                try:
                    precio_volumen.append({
                        "qty": int(pb.get("BreakQuantity", 1)),
                        "precio_usd": float(pb.get("UnitPrice", 0)),
                        "precio_clp": round(float(pb.get("UnitPrice", 0)) * TASA_USD_CLP),
                    })
                except Exception:
                    pass

            # Stock y disponibilidad
            stock = prod.get("QuantityAvailable")
            lead_weeks = prod.get("LeadWeeks")
            lead_str = f"{lead_weeks} semanas" if lead_weeks else None

            # Especificaciones técnicas
            specs: dict = {}
            for param in (prod.get("Parameters") or []):
                name = param.get("ParameterText") or param.get("Parameter")
                value = param.get("ValueText") or param.get("Value")
                if name and value:
                    specs[name] = value

            # Certificaciones
            rohs_status = (prod.get("RoHsStatus") or "").lower()
            rohs = True if "compliant" in rohs_status else (False if "non" in rohs_status else None)

            results.append({
                "titulo": (prod.get("Description") or {}).get("ProductDescription") or query,
                "precio": round(precio_usd * TASA_USD_CLP) if precio_usd else None,
                "moneda": "CLP" if precio_usd else None,
                "precio_original": precio_usd,
                "moneda_original": "USD",
                "url": prod.get("ProductUrl", ""),
                "fuente": "digikey",
                "fuente_label": "DigiKey",
                "pais": "US",
                "proveedor": "DigiKey",
                "marca": (prod.get("Manufacturer") or {}).get("Name"),
                "numero_parte": prod.get("ManufacturerProductNumber"),
                "thumbnail": prod.get("PrimaryPhoto"),
                # Enriquecidos
                "descripcion": (prod.get("Description") or {}).get("DetailedDescription"),
                "stock": stock,
                "stock_disponible": (stock or 0) > 0 if stock is not None else None,
                "cantidad_minima": prod.get("MinimumOrderQuantity"),
                "plazo_entrega_estimado": lead_str,
                "rohs": rohs,
                "datasheet_url": prod.get("PrimaryDatasheet"),
                "categoria": (prod.get("Category") or {}).get("Name"),
                "especificaciones": specs if specs else None,
                "precio_volumen": precio_volumen if precio_volumen else None,
                "condicion": "nuevo",
                "lifecycle": (prod.get("ProductStatus") or {}).get("Status"),
            })
        return results
    except Exception as e:
        print(f"[DigiKey] Error: {e}")
        return []
