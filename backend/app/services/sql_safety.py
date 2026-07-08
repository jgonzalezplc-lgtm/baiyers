"""Sanitización de SQL generado por Gemini — solo SELECTs seguros."""
import re

TABLAS_PERMITIDAS = {
    "cotizaciones", "resultados", "ordenes_compra", "proveedores",
    "facturas", "supplier_ratings", "items_proyecto", "cotizaciones_proyecto",
    "proyectos", "recurrencias", "chat_conversaciones", "chat_mensajes",
}

PALABRAS_PROHIBIDAS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|EXEC|EXECUTE|UNION)\b",
    re.IGNORECASE,
)


def sanitizar_sql(sql: str, user_id: str) -> str:
    """
    Valida y ajusta el SQL generado por Gemini.
    Lanza ValueError si la consulta no es segura.
    """
    sql = sql.strip().rstrip(";")

    # Solo SELECT
    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        raise ValueError("Solo se permiten consultas SELECT")

    # Sin palabras peligrosas
    if PALABRAS_PROHIBIDAS.search(sql):
        raise ValueError("Consulta rechazada: contiene operación no permitida")

    # Solo tablas permitidas
    tablas_en_query = re.findall(r"\bFROM\s+(\w+)|\bJOIN\s+(\w+)", sql, re.IGNORECASE)
    for grupo in tablas_en_query:
        for tabla in grupo:
            if tabla and tabla.lower() not in TABLAS_PERMITIDAS:
                raise ValueError(f"Tabla no permitida: {tabla}")

    # Sin subqueries a tablas de sistema
    if re.search(r"information_schema|pg_catalog|auth\.", sql, re.IGNORECASE):
        raise ValueError("Acceso denegado a tablas del sistema")

    # Inyectar filtro user_id si no está presente
    if "user_id" not in sql.lower():
        # Añadir al final como subcondición
        if "WHERE" in sql.upper():
            sql = re.sub(r"\bWHERE\b", f"WHERE user_id = '{user_id}' AND ", sql, count=1, flags=re.IGNORECASE)
        else:
            # Antes de ORDER BY / GROUP BY / LIMIT
            match = re.search(r"\b(ORDER BY|GROUP BY|LIMIT|$)", sql, re.IGNORECASE)
            if match and match.group(0):
                pos = match.start()
                sql = sql[:pos] + f" WHERE user_id = '{user_id}' " + sql[pos:]
            else:
                sql += f" WHERE user_id = '{user_id}'"

    # Asegurar LIMIT máximo 100
    if "LIMIT" not in sql.upper():
        sql += " LIMIT 100"
    else:
        sql = re.sub(r"LIMIT\s+(\d+)", lambda m: f"LIMIT {min(int(m.group(1)), 100)}", sql, flags=re.IGNORECASE)

    return sql
