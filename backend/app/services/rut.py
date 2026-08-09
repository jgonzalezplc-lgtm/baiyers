"""Validación y normalización de RUT chileno. Puro, sin acceso a DB."""

import re

_RUT_LIMPIO_RE = re.compile(r"[^0-9kK]")


def normalizar_rut(rut: str) -> str:
    """Quita puntos/guión/espacios y deja el dígito verificador en mayúscula."""
    limpio = _RUT_LIMPIO_RE.sub("", rut or "")
    return limpio.upper()


def _digito_verificador(cuerpo: str) -> str:
    suma = 0
    multiplicador = 2
    for c in reversed(cuerpo):
        suma += int(c) * multiplicador
        multiplicador = multiplicador + 1 if multiplicador < 7 else 2
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def validar_rut(rut: str) -> bool:
    """Valida un RUT chileno (dígito verificador módulo 11)."""
    limpio = normalizar_rut(rut)
    if len(limpio) < 2:
        return False
    cuerpo, dv = limpio[:-1], limpio[-1]
    if not cuerpo.isdigit():
        return False
    if not (7 <= len(cuerpo) <= 8):
        return False
    return _digito_verificador(cuerpo) == dv


def formatear_rut(rut: str) -> str:
    """Formatea a XX.XXX.XXX-D. Asume que `rut` ya es válido."""
    limpio = normalizar_rut(rut)
    cuerpo, dv = limpio[:-1], limpio[-1]
    partes = []
    while len(cuerpo) > 3:
        partes.insert(0, cuerpo[-3:])
        cuerpo = cuerpo[:-3]
    partes.insert(0, cuerpo)
    return ".".join(partes) + "-" + dv
