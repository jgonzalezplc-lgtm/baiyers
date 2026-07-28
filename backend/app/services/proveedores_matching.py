"""
Resolución y deduplicación de proveedores/contactos: usado tanto por el import
de Excel como por el agente de Gmail, para que ambos escriban sobre el MISMO
directorio (`proveedores` + `proveedor_contactos`) en vez de crear registros
paralelos.

Orden de coincidencia (el primero que matchea gana, no se fusiona nada
automáticamente si hay ambigüedad — sólo se usa para decidir "ya existe" vs
"hay que crear uno nuevo"):
  1. RUT normalizado.
  2. Email de contacto exacto.
  3. Dominio del email entre los contactos ya registrados.
  4. Nombre normalizado (sin S.A./SpA/Ltda, minúsculas, sin tildes/espacios extra).
"""
import re
import unicodedata


def normalizar_rut(rut: str | None) -> str | None:
    if not rut:
        return None
    r = re.sub(r"[.\s]", "", rut).upper()
    return r or None


def normalizar_nombre(nombre: str | None) -> str:
    if not nombre:
        return ""
    s = nombre.lower().strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"\b(s\.?a\.?|spa|ltda\.?|limitada|e\.?i\.?r\.?l\.?)\b\.?", "", s)
    return re.sub(r"\s+", " ", s).strip()


def dominio_de(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.split("@", 1)[1].strip().lower()


def resolver_o_crear_proveedor(
    sb, user_id: str, nombre: str, email: str | None = None, rut: str | None = None,
) -> str:
    """Busca un proveedor existente del usuario por RUT/email/dominio/nombre;
    si no encuentra ninguno, crea uno nuevo. Devuelve el proveedor_id."""
    rut_norm = normalizar_rut(rut)
    nombre_norm = normalizar_nombre(nombre)

    if rut_norm:
        res = sb.table("proveedores").select("id").eq("user_id", user_id).eq("rut", rut_norm).limit(1).execute()
        if res.data:
            return res.data[0]["id"]

    if email:
        res = sb.table("proveedor_contactos").select("proveedor_id").eq("user_id", user_id).eq("email", email.strip().lower()).limit(1).execute()
        if res.data:
            return res.data[0]["proveedor_id"]

        dom = dominio_de(email)
        if dom:
            contactos = sb.table("proveedor_contactos").select("proveedor_id, email").eq("user_id", user_id).execute().data or []
            for c in contactos:
                if dominio_de(c.get("email")) == dom:
                    return c["proveedor_id"]

    if nombre_norm:
        candidatos = sb.table("proveedores").select("id, nombre").eq("user_id", user_id).execute().data or []
        for c in candidatos:
            if normalizar_nombre(c.get("nombre")) == nombre_norm:
                return c["id"]

    row = {
        "user_id": user_id,
        "nombre": (nombre or email or "Proveedor sin nombre")[:200],
        "email": (email or "")[:200] or None,
        "rut": rut_norm,
        "score": 50,
        "categoria_score": "confiable",
    }
    creado = sb.table("proveedores").insert(row).execute()
    return creado.data[0]["id"]


def resolver_o_crear_contacto(
    sb, user_id: str, proveedor_id: str, email: str, nombre: str | None = None,
    cargo: str | None = None, origen: str = "manual",
) -> str:
    """Busca el contacto de ese proveedor con ese email; si no existe, lo crea."""
    email_norm = email.strip().lower()
    res = sb.table("proveedor_contactos").select("id").eq("proveedor_id", proveedor_id).eq("email", email_norm).limit(1).execute()
    if res.data:
        return res.data[0]["id"]

    ya_tiene_principal = sb.table("proveedor_contactos").select("id").eq("proveedor_id", proveedor_id).eq("es_principal", True).limit(1).execute()
    creado = sb.table("proveedor_contactos").insert({
        "proveedor_id": proveedor_id,
        "user_id": user_id,
        "nombre": nombre,
        "email": email_norm,
        "cargo": cargo,
        "es_principal": not ya_tiene_principal.data,
        "origen": origen,
    }).execute()
    return creado.data[0]["id"]
