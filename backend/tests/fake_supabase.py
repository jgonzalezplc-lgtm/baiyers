"""Supabase en memoria para pruebas de flujo.

`MagicMock` sirve para verificar una llamada aislada, pero no para encadenar un
flujo: lo que una función escribe tiene que ser lo que la siguiente lee. Esta
implementación soporta el subconjunto de PostgREST que usan los servicios de
compra.

Deliberadamente pequeña: si algún día necesita joins o RPC, es señal de que la
prueba está abarcando demasiado y conviene partirla.
"""
import itertools
import uuid
from typing import Any, Optional


class _Respuesta:
    def __init__(self, data: Any, count: Optional[int] = None):
        self.data = data
        self.count = count


class _Consulta:
    """Acumula filtros y los aplica recién en `execute()`, como PostgREST."""

    def __init__(self, tabla: "_Tabla", operacion: str, payload: Any = None,
                 *, contar: bool = False, on_conflict: str = "",
                 ignore_duplicates: bool = False):
        self._tabla = tabla
        self._operacion = operacion
        self._payload = payload
        self._contar = contar
        self._on_conflict = on_conflict
        self._ignore_duplicates = ignore_duplicates
        self._filtros: list = []
        self._limite: Optional[int] = None
        self._single = False

    # ── Filtros ──────────────────────────────────────────────────────────────
    def eq(self, columna, valor):
        self._filtros.append(lambda f: f.get(columna) == valor)
        return self

    def neq(self, columna, valor):
        self._filtros.append(lambda f: f.get(columna) != valor)
        return self

    def in_(self, columna, valores):
        conjunto = list(valores)
        self._filtros.append(lambda f: f.get(columna) in conjunto)
        return self

    def is_(self, columna, _valor):
        self._filtros.append(lambda f: f.get(columna) is None)
        return self

    def like(self, columna, patron):
        prefijo = patron.replace("%", "")
        self._filtros.append(lambda f: str(f.get(columna) or "").startswith(prefijo))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self._limite = n
        return self

    def maybe_single(self):
        self._single = True
        return self

    def single(self):
        self._single = True
        return self

    # ── Ejecución ────────────────────────────────────────────────────────────
    def _coinciden(self) -> list[dict]:
        filas = [f for f in self._tabla.filas if all(p(f) for p in self._filtros)]
        return filas[: self._limite] if self._limite else filas

    def execute(self) -> Optional[_Respuesta]:
        if self._operacion == "select":
            filas = self._coinciden()
            if self._single:
                # postgrest-py 2.x devuelve None, no un objeto con .data = None
                # (ver el gotcha documentado en CLAUDE.md).
                return _Respuesta(filas[0]) if filas else None
            return _Respuesta(filas, count=len(filas) if self._contar else None)

        if self._operacion == "insert":
            nuevas = [self._tabla._insertar(f) for f in self._payload]
            return _Respuesta(nuevas)

        if self._operacion == "upsert":
            nuevas = []
            claves = [c.strip() for c in self._on_conflict.split(",") if c.strip()]
            for fila in self._payload:
                existente = next(
                    (f for f in self._tabla.filas
                     if claves and all(f.get(c) == fila.get(c) for c in claves)),
                    None,
                )
                if existente:
                    if not self._ignore_duplicates:
                        existente.update(fila)
                    continue
                nuevas.append(self._tabla._insertar(fila))
            return _Respuesta(nuevas)

        if self._operacion == "update":
            filas = self._coinciden()
            for fila in filas:
                fila.update(self._payload)
            return _Respuesta(filas)

        if self._operacion == "delete":
            filas = self._coinciden()
            for fila in filas:
                self._tabla.filas.remove(fila)
            return _Respuesta(filas)

        raise NotImplementedError(self._operacion)


class _Tabla:
    _secuencia = itertools.count(1)

    def __init__(self, nombre: str):
        self.nombre = nombre
        self.filas: list[dict] = []

    def _insertar(self, fila: dict) -> dict:
        nueva = {"id": fila.get("id") or str(uuid.uuid4()), **fila}
        self.filas.append(nueva)
        return nueva

    def select(self, *_cols, count=None):
        return _Consulta(self, "select", contar=count == "exact")

    def insert(self, filas):
        return _Consulta(self, "insert", filas if isinstance(filas, list) else [filas])

    def upsert(self, filas, on_conflict="", ignore_duplicates=False):
        return _Consulta(self, "upsert", filas if isinstance(filas, list) else [filas],
                         on_conflict=on_conflict, ignore_duplicates=ignore_duplicates)

    def update(self, valores):
        return _Consulta(self, "update", valores)

    def delete(self):
        return _Consulta(self, "delete")


class FakeSupabase:
    """Cliente falso. `sembrar()` carga filas iniciales; `filas()` inspecciona."""

    def __init__(self, **tablas: list[dict]):
        self._tablas: dict[str, _Tabla] = {}
        for nombre, filas in tablas.items():
            self.sembrar(nombre, filas)

    def table(self, nombre: str) -> _Tabla:
        return self._tablas.setdefault(nombre, _Tabla(nombre))

    def sembrar(self, nombre: str, filas: list[dict]) -> None:
        tabla = self.table(nombre)
        for fila in filas:
            tabla._insertar(dict(fila))

    def filas(self, nombre: str) -> list[dict]:
        return self.table(nombre).filas
