"""Preview/commit de proveedores para MCP."""
import base64
import hashlib
import io

from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext
from app.services.mcp_jobs import commit_draft, create_draft, get_active_draft


def preview_supplier_import(sb, actor: ApplicationActorContext, file_base64: str, file_name: str) -> dict:
    try: content = base64.b64decode(file_base64, validate=True)
    except ValueError as exc: raise HTTPException(status_code=422, detail="Archivo base64 inválido") from exc
    if len(content) > 15 * 1024 * 1024: raise HTTPException(status_code=413, detail="Archivo supera 15 MB")
    try:
        import pandas as pd
        frame = pd.read_csv(io.BytesIO(content), dtype=str) if file_name.lower().endswith(".csv") else pd.read_excel(io.BytesIO(content), dtype=str)
    except Exception as exc: raise HTTPException(status_code=422, detail=f"No se pudo leer el archivo: {exc}") from exc
    from app.routers.proveedores_import import _mapear_fila, _tiene_columnas_reconocidas
    if not _tiene_columnas_reconocidas(frame.columns):
        raise HTTPException(status_code=422, detail="No se reconoce una columna de nombre/proveedor")
    frame = frame.where(frame.notnull(), None)
    rows = [_mapear_fila(row) for row in frame.head(200).to_dict(orient="records")]
    valid, issues = [], []
    for index, row in enumerate(rows):
        if not str(row.get("nombre") or "").strip(): issues.append({"row": index + 2, "issue": "nombre_faltante"})
        else: valid.append(row)
    payload = {"rows": valid, "issues": issues, "total_rows": len(rows), "ready_to_commit": bool(valid)}
    draft = create_draft(sb, actor, "supplier_import", payload, source_name=file_name,
                         source_hash=hashlib.sha256(content).hexdigest())
    return {"draft_id": draft["id"], "expires_at": draft.get("expires_at"), **payload}


async def commit_supplier_import(sb, actor: ApplicationActorContext, draft_id: str, *, confirmed: bool) -> dict:
    if confirmed is not True: raise HTTPException(status_code=409, detail="Se requiere confirmación explícita")
    draft = get_active_draft(sb, actor, draft_id)
    if draft.get("draft_type") != "supplier_import": raise HTTPException(status_code=422, detail="Draft inválido")
    from app.routers.proveedores import CrearProveedorRequest, crear_proveedor
    created = []
    errors = []
    for row in (draft.get("payload") or {}).get("rows", []):
        try:
            result = await crear_proveedor(CrearProveedorRequest(
                nombre=str(row.get("nombre")), rut=row.get("rut"), sitio_web=row.get("sitio_web"),
                pais=row.get("pais") or "CL", email=row.get("email"),
                contacto_nombre=row.get("contacto_nombre"), telefono=row.get("telefono"),
                categorias=[str(row.get("categoria"))] if row.get("categoria") else [],
                notas_privadas=row.get("notas"),
            ), actor.to_auth_context())
            created.append(result.get("id"))
        except Exception as exc: errors.append({"nombre": row.get("nombre"), "error": str(exc)[:300]})
    commit_draft(sb, actor, draft_id, entity_type="supplier_import", entity_id=created[0] if created else draft_id)
    return {"processed": len(created), "supplier_ids": created, "errors": errors[:20]}
