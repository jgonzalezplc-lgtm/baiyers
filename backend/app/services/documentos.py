"""Extracción de texto de documentos ofimáticos.

Vivía como `_texto_office` dentro de `routers/identificar.py`, donde lo usaba un
solo endpoint. Se movió acá sin cambiarle la lógica cuando apareció el segundo
llamador: el parseo de adjuntos de correo (`services/adjunto_parser.py`), que
necesita leer la planilla de precios que manda un proveedor.

Por qué Office se convierte a texto y PDF no: Gemini acepta `application/pdf` y
las imágenes como bytes, pero no XLSX ni DOCX. Para esos formatos hay que
extraer el texto antes, y ese es todo el propósito de este módulo.
"""
import io
import xml.etree.ElementTree as ET
import zipfile

from fastapi import HTTPException


def texto_office(data: bytes, nombre: str) -> str:
    """Extrae texto tabular de DOCX/XLSX sin ejecutar macros ni contenido externo."""
    nombre = nombre.lower()
    try:
        if nombre.endswith(".docx"):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                root = ET.fromstring(zf.read("word/document.xml"))
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            parrafos = []
            for p in root.iter(ns + "p"):
                texto = "".join(t.text or "" for t in p.iter(ns + "t")).strip()
                if texto:
                    parrafos.append(texto)
            return "\n".join(parrafos)
        if nombre.endswith((".xlsx", ".xlsm")):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            lineas = []
            for ws in wb.worksheets:
                lineas.append(f"[HOJA: {ws.title}]")
                for row in ws.iter_rows(values_only=True):
                    vals = [str(v).strip() if v is not None else "" for v in row]
                    if any(vals):
                        lineas.append("\t".join(vals))
            return "\n".join(lineas)
        if nombre.endswith(".xls"):
            import pandas as pd
            hojas = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None)
            lineas = []
            for titulo, frame in hojas.items():
                lineas.append(f"[HOJA: {titulo}]")
                for fila in frame.fillna("").astype(str).values.tolist():
                    if any(v.strip() for v in fila):
                        lineas.append("\t".join(v.strip() for v in fila))
            return "\n".join(lineas)
    except (KeyError, zipfile.BadZipFile, ET.ParseError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"No se pudo leer el archivo Office: {exc}")
    raise HTTPException(status_code=415, detail="Formato Office no compatible")
