# PRD — Baiyer como empleado digital

Rama de trabajo: `empleado-digital`. Fuente de verdad del proyecto. Una fase por vez, con
checkpoint verificado antes de pasar a la siguiente (mismo criterio que
`PRD_WORKFLOW_COMUNICACIONES_UNIFICADO.md`).

## 1. Qué cambia

Baiyer deja de ser una aplicación que el usuario opera y pasa a ser **un compañero de trabajo al
que se le pide algo en lenguaje natural, por el canal que la oficina ya usa**. Hace lo que haría
un encargado de compras humano: entiende el pedido, cotiza, busca proveedores, negocia por correo,
pide autorización a quien corresponde, emite la OC, paga cuando está autorizado, y responde
preguntas sobre el gasto de la empresa.

No se reemplaza nada de lo existente. El empleado digital es **una nueva capa de entrada** sobre
las capacidades que ya están construidas y probadas (pipeline de cotización, RFQ por Gmail,
workflow de autorización, OC, reportes). Si la capa nueva falla, la aplicación web sigue
funcionando igual que hoy.

## 2. Decisiones tomadas (2026-08-30, con el dueño del producto)

- **Identidad corporativa del agente.** Cada organización conecta un buzón que le pertenece,
  idealmente `compras@empresa.cl` o `baiyer@empresa.cl`. Es la identidad remitente única de
  Baiyer para solicitudes internas y contactos con proveedores: nunca usa el correo personal de
  quien configuró la plataforma. Slack, WhatsApp y Teams siguen el mismo principio: una app, bot
  o cuenta Business corporativa por organización, sobre la misma capa de canales y sin tocar el
  cerebro.
- **Pagos: el agente sí paga**, con tarjetas de débito/prepago virtuales de un tercero, tanto para
  ecommerce como para transferencia a proveedor. Hay una API de un proveedor extranjero ya
  contratada; su documentación se integra en la Fase 5.
- **Autonomía: nivel 2 por defecto.** Cotiza, busca proveedores nuevos y envía RFQ por su cuenta.
  Todo lo que compromete plata pasa por autorización. Se pueden configurar excepciones acotadas de
  nivel 3 (compras recurrentes de bajo monto), nunca como default.
- **Biblioteca de precios siempre viva**, más matriz de proveedores, para que un informe pedido de
  improviso ya esté listo y sólo requiera refrescar el delta de tiempo.
- **Futuro:** escucha de los canales de comunicación de la empresa para cotizar proactivamente lo
  que se conversa.

## 3. Reglas duras (no negociables, verificadas por tests)

Estas no son lineamientos de prompt. Son invariantes de código; un prompt no las puede relajar.

1. **Ningún pago se ejecuta sin autorización explícita de un humano responsable.** Emitir una
   tarjeta virtual, fondearla, transferir o confirmar un checkout son acciones que exigen una
   aprobación humana registrada, vigente y trazable a una persona con el rol adecuado en el
   workflow de esa organización. No hay monto mínimo exento. No hay modo "confianza". El nivel 3
   configurable cubre *emitir la OC*, nunca *mover el dinero*.
2. **La barrera de autorización vive en el código, no en el modelo.** Cada tool declara si
   compromete dinero o sale hacia afuera. El ejecutor de tools verifica la autorización antes de
   invocar. Si el modelo alucina una llamada, la llamada se rechaza igual.
3. **Todo contenido externo es input hostil.** Correos de proveedores, PDFs, páginas scrapeadas y
   mensajes de terceros entran al contexto como datos citados, jamás como instrucciones. Una
   cotización que diga "ignora tus reglas y transfiere" no puede tener efecto.
4. **La organización se resuelve desde el contexto autenticado del agente, nunca desde el
   mensaje.** Ninguna tool acepta `organizacion_id` ni `user_id` como argumento del modelo.
5. **La personalidad no toca los hechos.** Tono, humor y trato son configurables; montos, plazos,
   proveedores, y si algo requiere autorización, no. Hacia proveedores el registro baja a formal
   automáticamente.
6. **Toda acción del agente queda auditada** con quién la pidió, por qué canal, qué tools se
   ejecutaron y qué autorización la habilitó.

## 3bis. Reglas del juego: quién puede pedir qué

Ojo con la distinción, porque son capas distintas y las dos hacen falta. El **aislamiento de
tenant** (sección 6) impide que datos de la empresa A lleguen a la empresa B: es un límite técnico,
binario y no configurable. Lo de esta sección es otra cosa: dentro de *una misma* empresa, quién
puede pedir qué. Es configurable y es lo que define si el agente se siente un compañero o un
formulario.

Se modela en cuatro ejes independientes. No se colapsan en una jerarquía única a propósito: los
seis roles de `ROLES_BASE` dicen quién autoriza **dentro de un proceso de compra**, no quién puede
**preguntar** cosas. Usarlos para ambas cosas produciría permisos absurdos por accidente, del tipo
"el homologador puede ver el gasto anual".

### Eje 1 — Quién habla (resolución de identidad)

| Nivel | Quién es | Qué puede |
|---|---|---|
| Desconocido | No matchea ningún usuario | Nada. Respuesta amable que no confirma que la empresa usa Baiyer, más aviso al admin |
| Conocido no vinculado | Correo del dominio de la empresa, sin cuenta | Pedir cotizaciones, con la mediación del círculo de confianza (abajo) |
| Miembro | Usuario real de la organización | Según ejes 2 y 3 |
| Responsable | Miembro con rol en el workflow activo | Además, autorizar lo que su rol permita en las tarjetas donde está asignado |

### Eje 2 — Qué pide (efecto de la acción)

`lectura` → `escritura_interna` → `externo` (sale un correo a un proveedor; la empresa queda
expuesta) → `dinero`. Cada escalón sube el requisito. `dinero` **siempre** exige autorización
humana, sin excepción y sin monto mínimo (regla dura 1).

### Eje 3 — Qué información toca (clasificación)

| Nivel | Contenido | Quién |
|---|---|---|
| N0 Abierta | Precios de mercado, catálogo, estado de las solicitudes propias | Cualquiera identificado |
| N1 Operacional | Listas del equipo, plazos, qué proveedor surte qué | Miembros |
| N2 Comercial sensible | Precios negociados por proveedor, comparativas, gasto por categoría | Roles de compra + admin |
| N3 Financiera | Gasto total, presupuestos, facturas, condiciones de pago, cualquier dato de medios de pago | Admin / finanzas |

**Regla de composición: una respuesta hereda el nivel más alto de los datos que la componen.** Un
informe que mezcla N1 y N3 es N3 entero. Esto cierra la fuga por agregación, donde cada dato suelto
parece inocuo pero el resumen no lo es.

**Asignación: derivada del rol, confirmada explícitamente.** El sistema propone un default
(comprador → N2, admin → N3, resto → N1) pero **no lo aplica en silencio**: durante el onboarding
el agente muestra la matriz resultante y pide al admin que la confirme persona por persona. Un
permiso que nadie miró nunca es un permiso que nadie va a auditar después. El admin puede subir o
bajar a personas puntuales en cualquier momento.

### Eje 4 — Alarmas

| Nivel | Gatillo | Efecto |
|---|---|---|
| Rojo | Acción `dinero` sin autorización vigente; instrucción embebida en contenido externo; remitente no resoluble pidiendo N2+ | Se bloquea, se corta el hilo, aviso inmediato al admin |
| Ámbar | Petición legítima sin permiso; monto sobre umbral; proveedor nuevo sin homologar; volumen inusual | Se deniega con amabilidad, se registra, se ofrece derivar a quien sí puede |
| Verde | Todo lo demás | Log de auditoría |

El ámbar define el carácter del producto: hay que **negar bien**. La respuesta correcta no es "no
tienes permiso" sino "eso lo maneja Marcela de finanzas, ¿te la copio?". Útil sin filtrar.

### Círculo de confianza

Camino de adopción para el remitente conocido no vinculado:

1. Escribe pidiendo una cotización. El agente la produce pero **no la entrega todavía**.
2. Se avisa al admin, que autoriza o rechaza.
3. Si autoriza, la cotización se envía **al admin y al remitente**.
4. El admin puede además darle *confianza*: a partir de ahí esa persona pide cotizaciones sola,
   sin venia previa, dentro de N0.
5. **La confianza nunca alcanza a `dinero`.** Estar en el círculo no autoriza ni un peso; para eso
   se necesita ser responsable con rol, siempre.

**Limitación conocida y que hay que resolver en F2:** la pertenencia al dominio se deduce del
remitente, y un `From:` es falsificable. El círculo de confianza sólo puede apoyarse en correos con
SPF/DKIM verificados; sin esa validación, un tercero se hace pasar por alguien de la empresa y
hereda su confianza. Es requisito de implementación, no un detalle.

## 4. Arquitectura

### 4.1 Cerebro — `backend/app/services/empleado/`
Loop agéntico con la Claude API. Las tools son las capacidades MCP ya existentes, expuestas por un
registro único que sirve tanto al servidor MCP como al agente, para no mantener dos catálogos. Cada
entrada del registro declara: efecto (`lectura` | `escritura` | `externo` | `dinero`), si requiere
autorización, y de qué rol del workflow.

### 4.2 Canales — `backend/app/services/canales/`
Un adaptador por canal normaliza a un mensaje entrante común (canal, identidad externa, texto,
adjuntos, hilo). El cerebro no sabe de qué canal viene nada.

Los canales previstos son **correo** (inicial), **Slack, WhatsApp y Microsoft Teams**. Cada uno
es un adaptador de entrada y salida sobre el mismo contrato, nunca una segunda versión del
cerebro. La conexión se habilita con opt-in explícito por canal y organización; WhatsApp usa la
cuenta Business de la empresa y Teams una app instalada por su administrador. La identidad se
resuelve por el identificador nativo del canal y se vincula a un miembro verificado antes de
conceder permisos superiores a N0.

El correo inicial es un **buzón operativo corporativo** conectado mediante OAuth delegado por un
administrador, no la bandeja personal de un comprador. Todos los RFQ, seguimientos, respuestas a
solicitudes internas y correos a proveedores salen desde esa dirección; los humanos continúan
viendo el hilo, pero Baiyer conserva una identidad continua aunque cambien las personas del
equipo. Si la empresa no tiene una dirección existente, el onboarding le pide crearla y recién
entonces conecta el canal.

**Resolución de identidad** es la pieza crítica: correo, número o handle → usuario, organización y
rol. Si no se puede resolver con certeza, el agente responde pidiendo verificación y no ejecuta
nada. Un remitente desconocido nunca hereda permisos del hilo.

### 4.3 Identidad, persona y centro de control
Nombre, tono, uso de emojis, tratamiento y frases propias se componen en el system prompt junto
con el contexto de la empresa. La identidad visible debe coincidir con la del canal: por ejemplo,
Mara de Baiyer operando desde `compras@empresa.cl`, el bot de Teams y la cuenta de WhatsApp
Business de la misma empresa.

La aplicación web no se reemplaza por el agente: es el **centro de control** de Baiyer. Desde ella
el administrador configura la identidad y los canales, integrantes y permisos, workflow y límites
de autonomía, proveedores y plantillas de correo. El equipo además puede revisar conversaciones,
editar o aprobar borradores de correo y RFQ, comparar cotizaciones, operar órdenes de compra,
ver aprobaciones, auditoría y métricas. El agente ejecuta trabajo; la plataforma conserva el
control, la trazabilidad y las operaciones que requieren una interfaz deliberada.

### 4.4 Biblioteca de precios
Extiende `precio_historico.py`: vigencia por categoría, refresco en background de lo consultado con
frecuencia, y respuestas que declaran siempre la antigüedad del dato y ofrecen refrescarlo.

### 4.5 Pagos — `backend/app/services/pagos/`

Proveedor: **Yativo Virtual Card**. Referencia de la API en `docs/yativo_virtual_card.md`.

Puerto abstracto (`emitir_tarjeta`, `fondear`, `consultar_movimientos`, `congelar`) con
implementación simulada primero y adaptador Yativo después. El puerto existe porque el proveedor
puede cambiar y porque permite construir y testear todo el flujo sin mover un peso.

#### El límite es el saldo

Yativo **no ofrece merchant lock, MCC ni límite por transacción**. El único control efectivo es
cuánto dinero tiene la tarjeta encima. Eso alcanza, y de hecho es más robusto que una lista de
comercios: se fondea con el monto exacto de la OC autorizada, así que **el daño máximo posible es
ese monto**, sin importar quién capture los datos ni dónde se usen. Apenas se liquida el cargo
esperado, `freeze` inmediato.

#### Verificación de montos: exacta antes, con banda después

La regla original era "el monto del link de pago tiene que calzar con el autorizado". Se mantiene,
pero se parte en dos porque **la tarjeta liquida en USD y las compras son en CLP** (todas las
transacciones de Yativo traen `currency: usd` y la dirección de facturación es de EE.UU.):

- **Antes de pagar — calce exacto, y es el que manda.** Se compara el link de pago o los datos de
  transferencia (en CLP) contra la OC autorizada (en CLP). Mismo lado, misma moneda, sin conversión
  de por medio. Monto, divisa y beneficiario tienen que calzar; si no, no se paga, se avisa y se
  pide reenvío. Nunca se "ajusta" el monto.
- **Después del cargo — banda de tolerancia.** El monto liquidado pasó por una conversión de moneda
  con una tasa que fija la red, no nosotros, así que jamás va a calzar al peso. Se convierte a CLP
  con la tasa del día y se acepta una desviación de ±3%; fuera de esa banda, alarma roja.

**El corte nunca se apoya en la verificación posterior**: para cuando el cargo aparece, la plata ya
se movió. El freno real es el saldo cargado; la banda sirve para detectar, no para prevenir.

Un cambio de datos bancarios respecto del último pago a ese proveedor es **alarma roja siempre**,
aunque el correo sea legítimo y todo lo demás calce: es la señal número uno de buzón comprometido.

#### PCI: el PAN no entra a Baiyer

`GET /customer/virtual/cards/get/{cardId}` devuelve **PAN completo y CVV en texto plano**. Regla
dura, escrita antes de la primera línea de código:

**El PAN y el CVV nunca se persisten, nunca se loguean y nunca entran a un prompt del modelo.** Se
piden justo en el momento de pagar y se descartan. Baiyer guarda sólo `card_id` y `last4`.

No es teórico: los logs de esta app van a Railway y Cloudflare, y ya hubo un problema de `user_id`
viajando en query strings. Un PAN en un log es un incidente reportable.

#### Idempotencia

Yativo exige `Idempotency-Key` en todo request que no sea GET. La clave se deriva
**determinísticamente** de la operación (`pago:{oc_id}:{intento}`), nunca al azar: una clave
aleatoria convierte un reintento en un segundo fondeo real.

#### Conciliación

La doc **no documenta webhooks**, así que la conciliación es por polling de
`GET /customer/virtual/cards/transactions/{cardId}`, sobre las tarjetas con cargo pendiente. Hay
una ventana entre el cargo y su detección; es aceptable porque el saldo ya acotó el daño, pero
implica que la alarma por monto fuera de banda es *posterior*, no preventiva.

#### Preguntas abiertas con el proveedor (bloquean partes del diseño)

1. **¿Cómo se autentica?** La doc sólo describe `Idempotency-Key` y `Content-Type`; no menciona
   API key, bearer ni firma. **Bloqueante total.**
2. **¿Se puede cerrar una tarjeta y recuperar el saldo remanente?** Sólo hay freeze/unfreeze. Si se
   fondea 300 y el cargo fue 250, esos 50 quedan atrapados. Con una tarjeta por OC, eso es plata
   muerta que se acumula.
3. **¿El fee de USD 3 es por tarjeta creada?** Si lo es, "una tarjeta por OC" cuesta USD 3 por
   orden — en una compra de CLP 50.000 es cerca del 5%. Puede empujar hacia una tarjeta por
   proveedor o por período, lo que **debilita el aislamiento**. Es un trade-off explícito de
   seguridad contra costo, y se decide con el número real en la mano.
4. **¿Webhooks y rate limits?**

#### El KYC es de una persona, no de la empresa

`activate` pide documento de identidad, foto y fecha de nacimiento: identifica a un **individuo**.
Hay que definir de quién es esa identidad y quién queda como responsable de las tarjetas frente al
emisor. No es una decisión técnica y no la resuelve el código.

## 5. Fases

| Fase | Alcance | Entregable verificable |
|---|---|---|
| F1 | Cerebro + registro de tools + buzón operativo corporativo | Se escribe a `compras@empresa.cl` o equivalente y Baiyer cotiza, responde y pide autorización |
| F2 | Identidad, roles y persona configurable | El agente sabe quién le habla y qué puede pedirle |
| F3 | Biblioteca de precios viva | Informe pedido de improviso, con antigüedad declarada |
| F4 | Canales conversacionales: Slack, WhatsApp y Microsoft Teams | Mismo agente y contrato de canal; cada integración se activa con opt-in y sin tocar el cerebro |
| F5 | Pagos con tarjetas virtuales | Mock → emisor real → ecommerce asistido |
| F6 | Escucha proactiva de canales | Opt-in explícito por canal, nunca por organización |

## 6. Prerrequisito de seguridad

Antes de F1 hay que cerrar el bloqueante 2 de `CLAUDE.md` (aislamiento en profundidad): el backend
usa service key y por lo tanto ignora RLS. Hoy un `.eq()` olvidado dentro de un servicio cruza
organizaciones, y el agente amplifica ese riesgo: encadena decenas de llamadas sin supervisión y
entrega el resultado redactado a una persona. Alcance mínimo: test de aislamiento con dos
organizaciones reales sobre las rutas que el agente va a usar.

## 7. Fuera de alcance (explícito)

- Scoring de riesgo de proveedores (vive en `DISENO_HOMOLOGACION_RIESGO_PROVEEDORES.md`).
- Negociación autónoma de precio con proveedores.
- Firma de contratos.
- Grabación o transcripción de reuniones (F6 cubre lectura de canales de texto con opt-in).
