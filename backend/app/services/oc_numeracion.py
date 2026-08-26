"""Numeración de Órdenes de Compra: `OC-2026-BVITAL-0007`.

Antes era `OC-{año}-{len(filas)+1:04d}`, con tres problemas:

1. Contaba filas en vez de leer el máximo, así que borrar una OC hacía que la
   siguiente reutilizara un número ya emitido a un proveedor.
2. No filtraba por organización: el correlativo de una empresa avanzaba cuando
   otra emitía una OC. Se ve en los datos reales — faltan la 0001 y la 0006.
3. No había `UNIQUE` en la tabla, así que dos creaciones simultáneas obtenían el
   mismo número y la base aceptaba las dos.

El código de empresa (`BVITAL`) resuelve algo distinto: Baiyer se integra a
empresas que **ya emiten sus propias OC**. Un `OC-2026-0007` de Baiyer podría
chocar con el `OC-2026-0007` que esa misma empresa emitió por su ERP. La `B`
marca el origen y el token identifica a la organización, así que los dos
universos de numeración no se pisan ni se confunden en una auditoría.

Este módulo es puro: no toca la DB. La asignación y persistencia del código
viven en `organizacion.py`.
"""
import re
import unicodedata

# 8 caracteres en total: "B" + 7. Suficiente para distinguir empresas sin volver
# ilegible el número en un PDF o en el asunto de un correo.
LARGO_TOKEN = 7
_PREFIJO_ORIGEN = "B"

# Formas societarias chilenas: no aportan identidad y comen los 7 caracteres
# útiles ("Vital SpA" y "Vital Ltda" quedarían ambas como "VITALS").
_SUFIJOS_SOCIETARIOS = frozenset({
    "SPA", "LTDA", "LIMITADA", "SA", "EIRL",
    "SOCIEDADANONIMA", "SOCIEDAD", "INC", "LLC", "CORP",
})
# Cuántas palabras finales se prueban juntas. "Vital S.A." se parte en "S" y "A",
# así que compararlas de a una nunca reconocería "SA".
_MAX_PALABRAS_SUFIJO = 4

_NUMERO_FINAL = re.compile(r"-(\d+)$")


def derivar_token(nombre: str | None) -> str:
    """Nombre de organización → token estable de hasta 7 caracteres.

    "Vital SpA" → "VITAL" · "Añón y Cía." → "ANONYCIA" [:7] → "ANONYCI"

    No garantiza unicidad entre organizaciones: dos empresas parecidas pueden
    derivar el mismo token. Quien lo persiste resuelve el choque (ver
    `desambiguar`), porque para eso hace falta consultar la DB.
    """
    limpio = unicodedata.normalize("NFKD", (nombre or "").strip())
    limpio = "".join(c for c in limpio if not unicodedata.combining(c))
    limpio = re.sub(r"[^A-Za-z0-9 ]+", " ", limpio).upper()

    palabras = [p for p in limpio.split() if p]

    # Se prueba de la cola hacia atrás, tomando primero los grupos más largos:
    # "Vital S A" tiene que reconocer "SA" antes que descartar la "A" sola.
    recortando = True
    while recortando and palabras:
        recortando = False
        for n in range(min(_MAX_PALABRAS_SUFIJO, len(palabras)), 0, -1):
            if "".join(palabras[-n:]) in _SUFIJOS_SOCIETARIOS:
                del palabras[-n:]
                recortando = True
                break
    # Si el nombre era SÓLO una forma societaria, se prefiere eso a un token
    # vacío: un número sin código no cumple el propósito de distinguir origen.
    if not palabras:
        palabras = [p for p in limpio.split() if p]

    token = "".join(palabras)[:LARGO_TOKEN]
    return token or "EMPRESA"[:LARGO_TOKEN]


def desambiguar(token: str, tomados: set[str]) -> str:
    """Devuelve un código libre a partir del token, sufijando un número.

    "BVITAL" tomado → "BVITAL2". El sufijo come el último carácter cuando hace
    falta, para no pasarse del largo.
    """
    base = f"{_PREFIJO_ORIGEN}{token}"
    if base not in tomados:
        return base
    for n in range(2, 100):
        sufijo = str(n)
        candidato = f"{base[:1 + LARGO_TOKEN - len(sufijo)]}{sufijo}"
        if candidato not in tomados:
            return candidato
    raise ValueError("No se pudo derivar un código de OC libre para esta organización")


def prefijo(anio: int, codigo: str) -> str:
    """Parte del número que identifica año y empresa: `OC-2026-BVITAL`."""
    return f"OC-{anio}-{codigo}"


def formatear(anio: int, codigo: str, correlativo: int) -> str:
    return f"{prefijo(anio, codigo)}-{correlativo:04d}"


def siguiente_correlativo(numeros_existentes: list[str], anio: int, codigo: str) -> int:
    """Máximo + 1 sobre los números de ESE año y ESA empresa.

    Se lee el máximo y no la cantidad: borrar una OC no puede hacer que la
    siguiente reutilice un número que ya viajó a un proveedor. Los números con
    otro formato (los legado, sin código de empresa) se ignoran.
    """
    esperado = prefijo(anio, codigo) + "-"
    maximo = 0
    for numero in numeros_existentes or []:
        if not (numero or "").startswith(esperado):
            continue
        match = _NUMERO_FINAL.search(numero)
        if match:
            maximo = max(maximo, int(match.group(1)))
    return maximo + 1
