import asyncio
import io
import json
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from app.services.auth_context import AuthContext, get_auth_context

router = APIRouter(prefix="/api/proveedores", tags=["proveedores_import"])


def _valor(fila: dict, *claves: str):
    normalizada = {str(k).lower().strip(): v for k, v in fila.items()}
    return next((normalizada.get(k) for k in claves if normalizada.get(k) not in (None, "")), None)


def _mapear_fila(fila: dict) -> dict:
    """Mapeo determinístico para encabezados comunes y formatos Baiyer."""
    return {
        "nombre": _valor(fila, "nombre", "name", "proveedor", "supplier_name", "legal_name", "company_name"),
        "email": _valor(fila, "email", "correo", "primary_email"),
        "telefono": _valor(fila, "telefono", "teléfono", "phone", "primary_phone"),
        "categoria": _valor(fila, "categoria", "category", "rubro"),
        "pais": _valor(fila, "pais", "país", "country") or "CL",
        "notas": _valor(fila, "notas", "notes", "observaciones"),
        "rut": _valor(fila, "rut", "tax_id"),
        "contacto_nombre": _valor(fila, "contact_name", "nombre_contacto"),
        "contacto_email": _valor(fila, "contact_email", "secondary_email", "correo_alternativo"),
        "sitio_web": _valor(fila, "sitio_web", "website", "web", "url"),
    }


def _tiene_columnas_reconocidas(columnas) -> bool:
    nombres = {str(c).lower().strip() for c in columnas}
    return bool(nombres.intersection({
        "nombre", "name", "proveedor", "supplier_name", "legal_name", "company_name",
    }))


# Inverso del mapeo usado por el banco sugerido: una categoría comercial del
# proveedor puede abastecer varias categorías técnicas de ítems.
CATEGORIAS_PROVEEDOR_A_ITEMS: dict[str, set[str]] = {
    "electronico": {"electronica", "neumatico"},
    "electronica": {"electronica", "neumatico"},
    "electrico": {"electrico"},
    "construccion": {"construccion", "tuberias_valvulas"},
    "madera": {"carpinteria"},
    "carpinteria": {"carpinteria"},
    "mecanico": {"mecanico", "industrial", "hidraulico", "neumatico", "tuberias_valvulas"},
    "ferreteria": {"mecanico", "industrial", "consumible"},
    "retail": {"consumible"},
}


def _categorias_items(valor) -> set[str]:
    if not valor:
        return set()
    if isinstance(valor, list):
        partes = valor
    else:
        partes = str(valor).replace(";", ",").replace("|", ",").split(",")
    salida: set[str] = set()
    for parte in partes:
        categoria = str(parte).lower().strip().replace(" ", "_")
        salida.update(CATEGORIAS_PROVEEDOR_A_ITEMS.get(categoria, {categoria} if categoria else set()))
    return salida


@router.get("/plantilla")
async def descargar_plantilla():
    """Retorna plantilla Excel con el formato sugerido."""
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=503, detail="openpyxl no instalado")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Proveedores"
    headers = ["Nombre", "Email", "Telefono", "Categoria", "Pais", "Notas"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = openpyxl.styles.Font(bold=True)

    # Fila de ejemplo
    ws.append(["Ferretería Central", "ventas@ferrecentral.cl", "+56 9 1234 5678", "Ferretería", "CL", "Proveedor confiable"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=plantilla_proveedores.xlsx"},
    )


@router.post("/importar")
async def importar_proveedores(file: UploadFile = File(...), ctx: AuthContext = Depends(get_auth_context)):
    """Lee Excel/CSV, normaliza con Gemini y hace upsert en proveedores."""
    user_id = ctx.actor_user_id

    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(status_code=503, detail="pandas no instalado. Ejecuta: pip install pandas openpyxl")

    from app.config import settings
    from app.services.supabase import get_supabase

    content = await file.read()
    filename = file.filename or ""

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content), dtype=str)
        else:
            df = pd.read_excel(io.BytesIO(content), dtype=str)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error leyendo archivo: {e}")

    df = df.where(pd.notnull(df), None)
    filas = df.head(200).to_dict(orient="records")
    if not filas:
        raise HTTPException(status_code=400, detail="El archivo está vacío")

    # Preview (primeras 5 filas para el frontend)
    preview = df.head(5).to_dict(orient="records")

    # Para formatos conocidos el mapeo determinístico es más confiable, rápido
    # y procesa las 200 filas; Gemini queda para encabezados realmente libres.
    proveedores_norm = []
    if _tiene_columnas_reconocidas(df.columns):
        proveedores_norm = [_mapear_fila(fila) for fila in filas]
    elif settings.gemini_api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")

            prompt = f"""Analiza estas filas de una base de proveedores y extrae en JSON (SOLO array JSON sin markdown):
[{{"nombre": "string", "email": "string o null", "telefono": "string o null", "categoria": "string o null", "pais": "CL/US/CN/etc o null", "notas": "string o null", "rut": "string o null (RUT/tax_id del proveedor)", "contacto_nombre": "string o null", "contacto_email": "string o null (si hay un correo de contacto de persona distinto del email general)"}}]

Si un campo no existe en las columnas, usa null. Infiere el país del teléfono o nombre si es posible.

Filas:
{json.dumps(filas[:50], ensure_ascii=False)}"""

            resp = await asyncio.wait_for(model.generate_content_async(prompt), timeout=20.0)
            text = resp.text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:].strip()
            respuesta_gemini = json.loads(text)
            proveedores_norm = [_mapear_fila(p) for p in respuesta_gemini if isinstance(p, dict)]
        except Exception as e:
            print(f"[Import] Gemini error: {e}")

    # Fallback: mapeo directo de columnas
    if not proveedores_norm:
        proveedores_norm = [_mapear_fila(fila) for fila in filas]

    from app.services.proveedores_matching import resolver_o_crear_proveedor, resolver_o_crear_contacto, normalizar_rut
    from app.services.supplier_capability_intelligence import registrar_evento

    sb = get_supabase()
    importados = 0
    actualizados = 0
    omitidos = 0
    errores = []

    for p in proveedores_norm:
        nombre = (p.get("nombre") or "").strip()
        email = (p.get("email") or "").strip() or None
        if not nombre:
            omitidos += 1
            continue
        try:
            # Busca por RUT → email/dominio → nombre normalizado antes de crear
            # uno nuevo, para no duplicar proveedores ya cargados manualmente
            # o por una importación anterior.
            from app.services.organizacion import ids_organizacion
            existentes_antes = sb.table("proveedores").select("id").in_("user_id", ids_organizacion(user_id)).eq("nombre", nombre[:200]).execute().data
            proveedor_id = resolver_o_crear_proveedor(sb, user_id, nombre, email, p.get("rut"))
            es_nuevo = not existentes_antes or existentes_antes[0]["id"] != proveedor_id

            cambios = {"nombre": nombre[:200]}
            if email:
                cambios["email"] = email[:200]
            rut_norm = normalizar_rut(p.get("rut"))
            if rut_norm:
                cambios["rut"] = rut_norm
            if p.get("telefono"):
                cambios["telefono"] = str(p["telefono"])[:100]
            if p.get("sitio_web"):
                cambios["sitio_web"] = str(p["sitio_web"])[:500]
            sb.table("proveedores").update(cambios).eq("id", proveedor_id).execute()

            if email:
                resolver_o_crear_contacto(sb, user_id, proveedor_id, email, origen="excel")
            contacto_email = (p.get("contacto_email") or "").strip()
            if contacto_email:
                resolver_o_crear_contacto(sb, user_id, proveedor_id, contacto_email, nombre=p.get("contacto_nombre"), origen="excel")

            # La categoría declarada en el Excel es evidencia explícita del
            # usuario. Se registra en el motor canónico y queda idempotente:
            # reimportar actualiza al proveedor sin duplicar capacidades.
            for categoria in _categorias_items(p.get("categoria")):
                registrar_evento(
                    user_id, proveedor_id, "manual_category_assigned",
                    categoria_confirmada=categoria,
                    metadata={"origen": "excel"},
                )

            if es_nuevo:
                importados += 1
            else:
                actualizados += 1
        except Exception as e:
            errores.append(f"{nombre}: {e}")

    return {
        "importados": importados,
        "actualizados": actualizados,
        "omitidos": omitidos,
        "errores": errores[:10],
        "preview": preview,
        "total_filas": len(filas),
    }
