"""Fuente: Mouser Electronics — API gratuita con registro."""
import httpx

MOUSER_SEARCH_URL = "https://api.mouser.com/api/v2/search/keyword"
TASA_USD_CLP = 950


async def buscar_mouser(query: str, max_results: int = 10, api_key: str = "") -> list[dict]:
    if not api_key:
        return []
    try:
        payload = {
            "SearchByKeywordRequest": {
                "keyword": query,
                "records": max_results,
                "startingRecord": 0,
                "searchOptions": "",
                "searchWithYourSignUpLanguage": "false",
            }
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                MOUSER_SEARCH_URL,
                json=payload,
                params={"apiKey": api_key},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()

        results = []
        parts = (data.get("SearchResults") or {}).get("Parts") or []
        for part in parts[:max_results]:
            # Precio unitario y breaks por volumen
            price_breaks_raw = part.get("PriceBreaks") or []
            precio_usd = None
            precio_volumen = []
            for pb in price_breaks_raw:
                try:
                    qty = int(pb.get("Quantity", 1))
                    p = float(pb.get("Price", "0").replace("$", "").replace(",", "").strip())
                    if p > 0:
                        precio_volumen.append({"qty": qty, "precio_usd": p, "precio_clp": round(p * TASA_USD_CLP)})
                        if precio_usd is None:
                            precio_usd = p
                except Exception:
                    pass

            # Stock
            stock_raw = part.get("AvailabilityInStock") or ""
            stock = None
            try:
                stock = int("".join(filter(str.isdigit, str(stock_raw)))) if stock_raw else None
            except Exception:
                pass

            # Lead time
            lead_time = part.get("LeadTime") or part.get("FactoryLeadTime") or None

            # Certificaciones
            rohs = None
            rohs_raw = (part.get("RohsStatus") or "").lower()
            if "compliant" in rohs_raw or "rohs" in rohs_raw:
                rohs = True
            elif "non" in rohs_raw:
                rohs = False

            # Lifecycle
            lifecycle = part.get("LifecycleStatus") or None

            results.append({
                "titulo": part.get("Description") or part.get("ManufacturerPartNumber", query),
                "precio": round(precio_usd * TASA_USD_CLP) if precio_usd else None,
                "moneda": "CLP" if precio_usd else None,
                "precio_original": precio_usd,
                "moneda_original": "USD",
                "url": part.get("ProductDetailUrl", ""),
                "fuente": "mouser",
                "fuente_label": "Mouser",
                "pais": "US",
                "proveedor": f"Mouser",
                "marca": part.get("Manufacturer"),
                "numero_parte": part.get("ManufacturerPartNumber"),
                "thumbnail": part.get("ImagePath") or None,
                # Enriquecidos
                "descripcion": part.get("Description"),
                "stock": stock,
                "stock_disponible": stock > 0 if stock is not None else None,
                "cantidad_minima": int(part.get("Min", 1) or 1),
                "plazo_entrega_estimado": lead_time,
                "rohs": rohs,
                "datasheet_url": part.get("DataSheetUrl") or None,
                "categoria": part.get("Category") or None,
                "lifecycle": lifecycle,
                "precio_volumen": precio_volumen if precio_volumen else None,
                "condicion": "nuevo",
            })
        return results
    except Exception as e:
        print(f"[Mouser] Error: {e}")
        return []
