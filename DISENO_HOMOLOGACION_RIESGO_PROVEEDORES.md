# Homologación y risk check de proveedores — propuesta para Baiyer

Fecha de investigación: 5 de agosto de 2026. Alcance inicial: proveedores B2B en Chile.

## Recomendación ejecutiva

Incorporar un **gate previo a la emisión de la OC** con dos capacidades separadas:

1. **Agente de homologación documental:** abre un expediente por proveedor y organización,
   solicita antecedentes por el mismo hilo Gmail, descarga y archiva adjuntos, extrae datos,
   valida integridad/vigencia/coherencia y pide sólo lo faltante o vencido.
2. **Motor/agente de riesgo:** consume únicamente evidencias estructuradas y trazables del
   expediente, fuentes externas y desempeño histórico de Baiyer. Calcula dimensiones de riesgo,
   aplica reglas duras y entrega una recomendación explicable. El LLM redacta y resume; no decide
   por sí solo el puntaje ni inventa datos faltantes.

El resultado no debe ser un simple “aprobado/rechazado”. Debe decir, por ejemplo:

> Riesgo alto (78/100). Recomendación: no emitir OC. La sociedad está vigente, pero existe un
> procedimiento concursal activo y la cuenta bancaria no pudo ser verificada. Fuentes consultadas,
> fechas y documentos disponibles en el expediente.

## 1. Expediente mínimo de homologación

No todos los proveedores requieren el mismo paquete. La política debe ser configurable por
organización, categoría, monto y criticidad.

### Nivel básico — toda compra

- Razón social, nombre de fantasía, RUT, tipo de persona, giro/actividad, domicilio y país.
- Contacto comercial y contacto de facturación.
- Inicio de actividades y situación tributaria consultada en SII.
- Datos bancarios: banco, tipo y número de cuenta, titular y RUT del titular.
- Certificado bancario o documento emitido por el banco. Nunca aceptar como única evidencia los
  datos escritos en el cuerpo del correo.
- Aceptación de condiciones de compra, tratamiento de datos y declaración de exactitud.

### Nivel estándar — proveedor recurrente o compra material

- Todo lo anterior.
- Certificado de vigencia de sociedad (sugerencia de política: emitido hace no más de 30 días).
- Estatuto actualizado y certificado de anotaciones, o equivalentes del régimen tradicional.
- Personería/poder vigente de quien suscribe contratos o comunica cambios bancarios.
- Declaración de beneficiarios finales y estructura de propiedad. Para una política AML reforzada,
  usar el umbral de 10% indicado por la UAF para sujetos obligados; para Baiyer esto es una buena
  práctica configurable, no una afirmación de que todo comprador privado esté sujeto a esa circular.
- Declaración de conflictos de interés, PEP, sanciones, cohecho y programa de integridad.
- Certificado de antecedentes laborales y previsionales de la Dirección del Trabajo, si es empleador.
- Referencias comerciales y cobertura/ubicaciones de despacho.
- Certificaciones técnicas, sanitarias, ambientales, de seguridad o seguros exigibles por categoría.

### Nivel reforzado — alto monto, anticipo, servicio en faena o proveedor crítico

- Estados financieros de los últimos 2 años y estado intermedio reciente; idealmente auditados según
  umbral definido por el comprador.
- Formulario 22 y/o carpeta tributaria aportada voluntariamente por el proveedor, con consentimiento
  y acceso restringido.
- Certificado de procedimientos concursales/quiebras de Superir.
- Informe comercial de una fuente autorizada/contratada, bajo base jurídica y finalidad definida.
- F30-1 por período/obra cuando exista subcontratación o trabajo en instalaciones del comprador.
- Pólizas y certificados: responsabilidad civil, accidentes, calidad, ciberseguridad u otros según rubro.
- Plan de continuidad, concentración de clientes/proveedores y capacidad operacional.
- Validación independiente de cambio de cuenta bancaria (callback a un contacto previamente
  verificado y doble aprobación interna).

### Documentos que no conviene pedir por defecto

- Copia de cédula de identidad de representantes, antecedentes penales u otros datos personales
  excesivos, salvo necesidad y base jurídica concreta.
- Claves del SII, ClaveÚnica, credenciales bancarias o accesos a portales.
- Cartolas bancarias completas si basta un certificado de titularidad.

## 2. Validaciones documentales

Cada documento debe tener `tipo`, `emisor`, `RUT detectado`, `fecha_emision`, `fecha_vencimiento`,
`folio/CVE`, `hash_sha256`, `origen`, `mime`, `tamaño`, `versión`, `texto_extraido`, resultado y evidencia.

El agente debe ejecutar controles determinísticos antes del análisis semántico:

- tipo real del archivo versus extensión/MIME; límite de tamaño; antivirus; bloqueo de ejecutables,
  macros y archivos cifrados; descompresión con límites anti zip-bomb;
- hash y deduplicación; conservación del original inmutable;
- RUT válido y coincidencia entre proveedor, titular bancario y documentos;
- razón social, representante y domicilio coherentes entre documentos;
- fechas, vigencia y política de antigüedad por tipo documental;
- folio/CVE/QR verificado contra la fuente oficial cuando exista;
- firma electrónica verificable cuando corresponda;
- detección de páginas faltantes, baja legibilidad y posibles alteraciones;
- extracción con confianza por campo y enlace a página/celda de origen.

La IA puede clasificar, extraer y detectar contradicciones. No debe declarar auténtico un documento
por su apariencia. “Válido” requiere verificación externa o revisión humana; sin ella usar “consistente
pero no verificado”.

### Documentos sin folio/CVE/QR verificable

Para tipos documentales que no tienen código de verificación oficial (certificado bancario, cotización,
referencia comercial), la defensa principal contra fabricación **no es** intentar detectar si el archivo
fue “generado por IA” — los detectores de watermark/estilo de IA son poco confiables para este uso: dan
falsos positivos con escaneos legítimos y falsos negativos con falsificaciones hechas a mano o con
plantilla editada. Es preferible un forense de metadata y layout, siempre alimentando `hallazgos` para
revisión humana y nunca declarando autenticidad por sí solo:

- metadata del PDF (`Producer`/`Creator`) contra el software conocido del emisor real cuando aplica;
- consistencia entre capa de texto e imagen de fondo (texto “pegado” sobre un escaneo es señal de edición);
- comparación de layout/tipografía contra una librería de plantillas de referencia por emisor/tipo;
- para el caso más sensible — cambio de cuenta bancaria — la mitigación real ya descrita en la sección 5
  (validación independiente por callback a un contacto previamente verificado) pesa más que cualquier
  análisis del archivo.

## 3. Fuentes para el risk check

### Fuentes públicas/oficiales recomendadas

| Fuente | Señal | Integración recomendada | Limitación |
|---|---|---|---|
| SII, Situación Tributaria de Terceros | Inicio/actividad y alertas tributarias | Consulta por RUT; guardar resultado, fecha y URL | El propio SII dice que es parcial y no certifica el comportamiento tributario |
| Registro de Empresas y Sociedades | Vigencia, estatuto, anotaciones, personería | Verificar CVE del documento aportado | Cubre régimen simplificado; sociedades tradicionales usan Conservador/Diario Oficial |
| Mercado Público / ChileProveedores | Estado hábil y ficha; historial de OC/licitaciones | API con ticket para proveedores, licitaciones y OC; certificado cuando proceda | Estado “hábil” es para contratación pública, no garantía financiera privada; API es beta |
| Superir | Liquidación, reorganización, renegociación/quiebras | Certificado aportado o consulta autorizada; registrar fecha | Portal puede requerir ClaveÚnica y no debe automatizarse sorteando controles |
| Dirección del Trabajo | Multas y deudas previsionales; cumplimiento F30-1 | Documento aportado y validación de folio si está disponible | Lo solicita el empleador; F30-1 depende de período/obra y no es universal |
| CMF | Fiscalización, sanciones y EEFF de entidades/emisores cubiertos | API/portal oficial cuando el RUT esté en universo CMF | No cubre a la mayoría de pymes proveedoras; API bancaria no es un buró comercial general |
| API Mercado Público | Órdenes adjudicadas, categorías, organismos, montos | Agregaciones por proveedor/RUT con ticket | Historial público no prueba cumplimiento privado ni solvencia actual |
| Historial Baiyer | respuesta RFQ, precio, entrega, calidad, incidentes, devoluciones | Eventos internos idempotentes y por organización | Debe distinguir “sin historia” de “mal desempeño” |

### Fuentes privadas a evaluar comercial y legalmente

- Buró comercial/informe empresarial (por ejemplo, proveedor autorizado de información comercial).
- Screening de sanciones, PEP, beneficiario final y adverse media con cobertura Chile/global.
- Validación de titularidad bancaria o confirmación bancaria, si un banco/fintech ofrece un contrato y
  API adecuados. Evitar screen scraping de portales bancarios.
- Monitoreo de ciberseguridad para proveedores con acceso a sistemas o datos.

Antes de integrar una fuente privada se debe confirmar contrato, cobertura, SLA, derecho a usar el dato
para evaluación de proveedores, retención, explicación/corrección y posibilidad de decisiones automatizadas.

### Fuentes que no deben presentarse como API disponible sin validación

SII, Registro de Empresas, Superir, DT y Poder Judicial tienen consultas o portales, pero eso no implica
que ofrezcan una API pública estable para este uso. No automatizar CAPTCHA, sesiones con ClaveÚnica ni
scraping contrario a términos. Implementar cada conector como `api`, `consulta_manual_verificada`,
`documento_aportado` o `no_disponible`, y mostrar esa calidad en el informe.

## 4. Lectura y archivo desde el agente de correo

### Lo que Baiyer ya puede hacer

- OAuth actual: `gmail.readonly`, `gmail.modify` y `gmail.send`.
- Detecta nombre, MIME y `attachmentId`; Gmail permite descargar el binario con esos scopes.
- La función `descargar_adjunto()` ya existe.
- La tabla `gmail_attachments` ya contempla `hash`, `texto_extraido`, `entity_type` y `entity_id`,
  pero hoy sólo se escriben nombre, MIME e id del adjunto.

### Lo que falta

1. Descargar el binario en un worker asíncrono, no dentro del polling principal.
2. Escanear y guardar el original en un bucket privado de Supabase Storage por organización/proveedor;
   DB sólo guarda metadatos y ruta. Cifrado, URLs firmadas cortas y auditoría de accesos.
3. Parsear PDF nativo y escaneado (OCR), DOCX, XLSX/CSV, imágenes y texto; preservar páginas y celdas.
4. Clasificar el documento contra un catálogo versionado y extraer a un esquema JSON estricto.
5. Validar reglas, cruzar campos y generar `hallazgos`, nunca sobrescribir silenciosamente datos maestros.
6. Mostrar revisión humana para baja confianza, contradicciones, datos bancarios y bloqueos.
7. Pedir por correo sólo documentos faltantes, ilegibles, inconsistentes o vencidos, con fecha concreta.

Los enlaces a Docs/Sheets/Drive incluidos en el correo no son adjuntos. Para leer contenido privado se
necesita permiso de Drive. La opción más segura es pedir exportación PDF/XLSX como adjunto. Como fase
posterior, usar Google Picker + `drive.file` por archivo; evitar `drive.readonly` global, que es scope
restringido y eleva verificación/seguridad. Enlaces públicos pueden descargarse sólo con controles SSRF,
allowlist de hosts, límites y registro de consentimiento.

### Formatos iniciales

- MVP: PDF, PNG/JPEG, DOCX, XLSX, CSV y TXT.
- No procesar activamente: XLSM/DOCM, ZIP/RAR, ejecutables o archivos protegidos por contraseña.
- Para XLSX usar lectura sin macros/fórmulas ejecutadas; extraer valores y fórmulas como texto.
- Para PDF firmado conservar original y validar firma con herramienta especializada; OCR no reemplaza
  la verificación de firma.

## 5. Flujo de estados propuesto

`no_iniciado → solicitado → recepcion_parcial → en_revision → requiere_aclaracion → completo →
evaluando_riesgo → homologado | homologado_condicional | rechazado | vencido | suspendido`

Reglas clave:

- Un expediente pertenece a `(organizacion_id, proveedor_id)`; no compartir evaluación privada entre
  clientes. Las evidencias públicas sí se vuelven a consultar, con cache acotado y procedencia.
- Homologación y risk check tienen versiones. Una reevaluación nunca borra la decisión anterior.
- El botón “Emitir OC” consulta el snapshot vigente, monto/categoría y política de la organización.
- Una excepción requiere rol autorizado, motivo, fecha de expiración y registro inmutable.
- El agente puede enviar recordatorios de rutina; contradicciones, sospecha de fraude o rechazo pasan a
  revisión humana antes de comunicar al proveedor.

Ejemplo de seguimiento seguro:

> Gracias, recibimos 5 de 7 antecedentes. Para completar la homologación faltan el certificado de
> vigencia emitido dentro de los últimos 30 días y un certificado bancario que identifique al titular.
> El documento F30-1 recibido corresponde a marzo de 2026 y la política requiere uno del período
> junio de 2026 o posterior. Puede responder a este mismo correo con los archivos adjuntos.

## 6. Modelo de riesgo explicable

Usar un score 0–100 donde 100 es mayor riesgo, separado en dimensiones. Los pesos son una política
versionada por organización, no constantes escondidas en un prompt.

| Dimensión | Peso inicial | Ejemplos de señales |
|---|---:|---|
| Identidad/legal | 20% | RUT/razón social, vigencia, personería, beneficiario final, inconsistencias |
| Tributario/laboral/compliance | 20% | alerta SII, DT/F30-1, sanciones, conflictos, integridad |
| Financiero/continuidad | 25% | insolvencia, liquidez, endeudamiento, antigüedad, dependencia, anticipo |
| Operacional/categoría | 15% | capacidad, certificaciones, cobertura, criticidad, continuidad |
| Desempeño histórico | 15% | entregas, calidad, disputas, respuesta, compras terminadas |
| Fraude/ciber/bancario | 5% | cambio de cuenta, dominio/email, titularidad, documentos alterados |

Bandas sugeridas: 0–24 bajo, 25–49 medio, 50–74 alto, 75–100 crítico. Además del score aplicar reglas
duras; un promedio no debe ocultar un evento decisivo.

### Reglas duras iniciales

- procedimiento concursal de liquidación activo: **bloquear / no comprar**, salvo excepción formal;
- RUT inválido, sociedad no vigente o identidad contradictoria: **bloquear**;
- cuenta bancaria con titular distinto no justificado o cambio no validado: **bloquear pago/OC**;
- documento presuntamente adulterado: **suspender y revisión humana**;
- documento obligatorio vencido: **no homologado** hasta actualizar;
- riesgo alto con compra crítica/anticipo: **segunda aprobación, garantía o proveedor alternativo**.

“Dato no disponible” no equivale a cero riesgo. Debe aumentar la incertidumbre y, según monto/criticidad,
obligar a pedir evidencia o revisión. La salida incluye score, banda, confianza/cobertura, reglas activadas,
evidencias a favor/en contra, fechas y acciones mitigantes.

### Historial Baiyer

Reutilizar el patrón de `supplier_capability_events`, pero no mezclar capacidad comercial con riesgo.
Crear eventos separados: entrega a tiempo, atraso, rechazo de calidad, devolución, disputa, cambio
bancario, factura inconsistente, OC completada y evaluación humana. Normalizar por cantidad de compras,
recencia y severidad. Un proveedor nuevo se marca “sin historia”, no “excelente”.

## 7. Esquema técnico sugerido

- `supplier_onboarding_cases`: organización, proveedor, nivel/política, estado, fechas, responsable.
- `supplier_requirements`: requisito versionado, obligatoriedad, condición, vigencia y estado.
- `supplier_documents`: Storage path, hash, MIME, fechas, folio/CVE, versión, origen y clasificación.
- `supplier_document_fields`: campo, valor normalizado, confianza y localización de evidencia.
- `supplier_findings`: severidad, regla, evidencia, resolución y revisor.
- `supplier_external_checks`: fuente, request seguro, respuesta normalizada, fecha, expiración y estado.
- `supplier_risk_assessments`: snapshot inmutable, política, scores, cobertura, banda y recomendación.
- `supplier_risk_events`: historial operacional idempotente.
- `supplier_bank_accounts`: cifrado y acceso muy restringido; estado de verificación, no secretos.
- `supplier_consents` y `supplier_audit_events`: finalidad, versión de aviso, actor y timestamps.

RLS por `organizacion_id`, service role sólo en workers, secretos en vault/env, logs sin contenido
documental ni cuentas completas. Definir retención y borrado; el hash puede conservarse sólo si la
política y base jurídica lo permiten.

## 8. Integración con el flujo actual

El punto correcto es después de seleccionar proveedores definitivos y antes de crear/enviar la OC:

1. Usuario selecciona proveedor.
2. Baiyer calcula nivel de homologación por monto, categoría, anticipo y criticidad.
3. Si no hay expediente vigente, ofrece “Iniciar homologación” y abre conversación de tipo
   `homologacion` (no reutilizar estados de RFQ/compra como si fueran lo mismo).
4. Agente documental completa el expediente y solicita faltantes.
5. Motor de riesgo ejecuta checks y genera snapshot.
6. UI muestra semáforo, recomendación, evidencias, incertidumbre y mitigaciones.
7. Política permite OC, exige aprobación/condiciones o bloquea. La decisión humana queda registrada.

No iniciar la homologación recién en el texto actual de `iniciar_proceso_compra()`: ese método se llama
cuando la lista ya fue autorizada y hoy anuncia al proveedor que fue seleccionado. Conviene adelantar el
gate y evitar prometer la compra antes del resultado de riesgo.

## 9. Implementación por fases

### Fase 0 — política y UX

- Definir paquete básico/estándar/reforzado, umbrales, vigencias y reglas por categoría.
- Aprobar aviso de privacidad, consentimiento cuando corresponda, retención y proceso de corrección.
- Diseñar pantalla de expediente y modal previo a OC.

### Fase 1 — expediente + adjuntos Gmail

- Migración de tablas, bucket privado, worker, antivirus y parsers de PDF/DOCX/XLSX/imágenes.
- Catálogo documental, extracción con evidencia y revisión humana.
- Correos determinísticos de solicitud/faltantes; sin auto-rechazo.

### Fase 2 — verificaciones oficiales

- RUT/SII, verificación CVE RES, Mercado Público y certificado Superir/DT aportado.
- Registro de procedencia, freshness, errores y modo manual donde no exista API legítima.

### Fase 3 — score y gate de OC

- Motor determinístico versionado, reglas duras, informe y override auditado.
- Conectar historial interno y monitoreo de vencimientos.

### Fase 4 — proveedores comerciales y monitoreo

- Buró/PEP/sanciones/beneficiario final después de due diligence contractual y legal.
- Reevaluación por vencimiento, evento adverso o nueva compra de mayor riesgo.

## 10. Criterios de aceptación del MVP

- Un proveedor responde con PDF, DOCX y XLSX; los originales quedan archivados, escaneados y hasheados.
- La ficha muestra cada campo con documento, página/celda, confianza y estado de verificación.
- El agente detecta documento faltante, vencido, ilegible y RUT inconsistente; redacta seguimiento exacto.
- Ningún dato bancario cambia automáticamente ni aparece completo en logs/UI sin permiso.
- El risk check es reproducible con las mismas evidencias y versión de política.
- El informe diferencia `encontrado`, `no encontrado`, `fuente no disponible` y `no aplica`.
- El gate bloquea reglas críticas, permite override autorizado y conserva auditoría.
- Toda recomendación tiene fuentes, fechas, cobertura y acciones concretas.

## Fuentes consultadas

- SII, [Situación Tributaria de Terceros](https://www2.sii.cl/stc/noauthz) y
  [descripción del trámite](https://www.sii.cl/como_se_hace_para/situacion_trib_terceros.html).
- Registro de Empresas y Sociedades, [verificación de certificados/CVE](https://www.registrodeempresasysociedades.cl/VerificarCertificados.aspx)
  y [equivalencias y personería](https://www.registrodeempresasysociedades.cl/FAQ.aspx?seccion=10).
- ChileCompra, [API pública y solicitud de ticket](https://ayuda.mercadopublico.cl/preguntasfrecuentes/article/KA-01967/es-es)
  y [Registro de Proveedores](https://proveedor.mercadopublico.cl/pago/buscarProveedor).
- Dirección del Trabajo, [certificado de antecedentes laborales y previsionales](https://www.dt.gob.cl/portal/1626/w3-article-100351.html)
  y [certificado de cumplimiento/F30-1](https://www.dt.gob.cl/portal/1626/w3-article-100359.html).
- Superintendencia de Insolvencia, [certificado de procedimientos concursales/quiebras](https://www.superir.gob.cl/tramites/solicitud-certificados/).
- CMF, [documentación de API](https://api.cmfchile.cl/api/documentacion/Estado-de-Resultados-de-Bancos.html).
- UAF, [beneficiario final](https://www.uaf.cl/es-cl/normativa/beneficiario-final).
- Google, [descarga de adjuntos Gmail](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages.attachments/get),
  [scopes de Drive](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) y
  [descarga/exportación](https://developers.google.com/workspace/drive/api/guides/manage-downloads).
- Biblioteca del Congreso Nacional, [Ley 21.719](https://www.bcn.cl/leychile/Navegar/imprimir?idNorma=1209272&idParte=10527471&idVersion=2026-12-01),
  vigente desde el 1 de diciembre de 2026, y [Ley 19.628 vigente hasta entonces](https://www.bcn.cl/leychile/Navegar?dt=open&idLey=19628).

## Decisiones que Baiyer debe cerrar antes de construir

1. Umbrales de monto y categorías que activan cada nivel.
2. Si Baiyer sólo recomienda o también bloquea técnicamente la OC.
3. Quién puede revisar, aprobar excepciones y ver datos bancarios/beneficiarios finales.
4. Qué fuente comercial se contratará y qué cobertura/costo ofrece por RUT chileno.
5. Períodos de vigencia y retención de cada documento.
6. Si se aceptarán enlaces Drive en una segunda fase o sólo adjuntos.

