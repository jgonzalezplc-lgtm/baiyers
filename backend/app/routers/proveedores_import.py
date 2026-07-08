import asyncio
import io
import json
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/proveedores", tags=["proveedores_import"])


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
async def importar_proveedores(file: UploadFile = File(...), user_id: str = ""):
    """Lee Excel/CSV, normaliza con Gemini y hace upsert en proveedores."""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id requerido")

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

    # Normalizar con Gemini
    proveedores_norm = []
    if settings.gemini_api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")

            prompt = f"""Analiza estas filas de una base de proveedores y extrae en JSON (SOLO array JSON sin markdown):
[{{"nombre": "string", "email": "string o null", "telefono": "string o null", "categoria": "string o null", "pais": "CL/US/CN/etc o null", "notas": "string o null"}}]

Si un campo no existe en las columnas, usa null. Infiere el país del teléfono o nombre si es posible.

Filas:
{json.dumps(filas[:50], ensure_ascii=False)}"""

            resp = await asyncio.wait_for(model.generate_content_async(prompt), timeout=20.0)
            text = resp.text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:].strip()
            proveedores_norm = json.loads(text)
        except Exception as e:
            print(f"[Import] Gemini error: {e}")

    # Fallback: mapeo directo de columnas
    if not proveedores_norm:
        col_map = {c.lower().strip(): c for c in df.columns}
        for fila in filas:
            fila_lower = {k.lower().strip(): v for k, v in fila.items()}
            proveedores_norm.append({
                "nombre": fila_lower.get("nombre") or fila_lower.get("name") or fila_lower.get("proveedor"),
                "email": fila_lower.get("email") or fila_lower.get("correo"),
                "telefono": fila_lower.get("telefono") or fila_lower.get("teléfono") or fila_lower.get("phone"),
                "categoria": fila_lower.get("categoria") or fila_lower.get("category") or fila_lower.get("rubro"),
                "pais": fila_lower.get("pais") or fila_lower.get("país") or fila_lower.get("country") or "CL",
                "notas": fila_lower.get("notas") or fila_lower.get("notes") or fila_lower.get("observaciones"),
            })

    sb = get_supabase()
    importados = 0
    actualizados = 0
    errores = []

    for p in proveedores_norm:
        nombre = (p.get("nombre") or "").strip()
        if not nombre:
            continue
        try:
            existing = None
            if p.get("email"):
                res = sb.table("proveedores").select("id").eq("user_id", user_id).eq("email", p["email"]).execute()
                if res.data:
                    existing = res.data[0]["id"]

            if not existing:
                res = sb.table("proveedores").select("id").eq("user_id", user_id).eq("nombre", nombre[:200]).execute()
                if res.data:
                    existing = res.data[0]["id"]

            row = {
                "user_id": user_id,
                "nombre": nombre[:200],
                "email": (p.get("email") or "")[:200] or None,
                "score": 50,
                "categoria_score": "confiable",
            }

            if existing:
                sb.table("proveedores").update(row).eq("id", existing).execute()
                actualizados += 1
            else:
                sb.table("proveedores").insert(row).execute()
                importados += 1
        except Exception as e:
            errores.append(f"{nombre}: {e}")

    return {
        "importados": importados,
        "actualizados": actualizados,
        "errores": errores[:10],
        "preview": preview,
        "total_filas": len(filas),
    }
