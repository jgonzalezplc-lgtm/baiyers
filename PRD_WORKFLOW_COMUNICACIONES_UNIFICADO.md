# PRD - Ciclo de compras y comunicaciones unificado

**Estado:** Borrador listo para implementación
**Dueño:** Producto Baiyer
**Creado:** 13-08-2026
**Producto:** Baiyer - Cotizador Inteligente B2B
**Alcance:** convertir el Workflow Builder en el único lugar donde se configuran etapas, roles, responsables, comunicaciones internas y externas, recordatorios y eventos que hacen avanzar una compra.
**Instrucción de implementación:** implementar por fases, conservando compatibilidad con los flujos reales existentes. No hacer un reemplazo big-bang.

---

## 1. Resumen

**Hoy:** Baiyer permite dibujar el ciclo de compras, asignar personas a roles y configurar plantillas de correo. Sin embargo, esas capacidades están separadas. El grafo gobierna principalmente la autorización; las comunicaciones se editan en otra pantalla; los responsables se asignan al rol para todo el workflow y no a cada acción; varios recordatorios existen sólo como plantillas, sin un scheduler que los ejecute; y los eventos externos todavía no mueven de forma general una instancia por todas las tarjetas del ciclo.

**Después:** cada tarjeta del ciclo será una unidad ejecutable y autocontenida. En ella se definirá qué trabajo ocurre, qué roles participan, quiénes son responsables, qué correos internos o externos se envían, cuándo se repiten, qué evento detiene cada loop y a qué tarjeta avanza el proceso. El chat y el editor visual modificarán el mismo modelo. La pantalla separada de comunicaciones quedará como biblioteca de plantillas por defecto, accesible desde el propio canvas, no como un segundo configurador del proceso.

---

## 2. La historia

### Antes

Camila administra compras en una empresa industrial. En el canvas dibuja que un cotizador pide precios, un autorizador revisa, un homologador valida al proveedor y un comprador emite la OC. Luego debe salir del grafo para buscar plantillas de correo en otra pantalla. Puede cambiar textos, pero no logra expresar que el cotizador insista cada dos días hasta recibir respuesta, que el autorizador reciba recordatorios diarios hasta decidir o que el homologador solicite documentos hasta que estén completos.

El grafo muestra el proceso que la empresa cree tener, pero no controla el proceso completo que Baiyer ejecuta. Las personas están vinculadas a roles globales, aunque en la práctica distintas áreas pueden cumplir el mismo rol en etapas diferentes. Las plantillas de recordatorio existen, pero algunas no se disparan. Camila no puede mirar una tarjeta y responder cuatro preguntas básicas: quién actúa, a quién escribe, cuánto insiste y qué hace avanzar el proceso.

### Después

Camila abre la tarjeta "Solicitar cotizaciones". Asigna el rol Cotizador a Ana, selecciona el correo externo "Solicitud de cotización", define un seguimiento cada dos días y establece que el loop termina cuando llega una cotización completa o cuando se alcanza el máximo de intentos. Para la ausencia de respuesta decide "descartar proveedor"; para una respuesta completa decide "pasar a seleccionar proveedores".

En "Autorizar selección", asigna a Rodrigo como Autorizador, selecciona un correo interno con magic link y un recordatorio diario hasta que apruebe, rechace o devuelva con observaciones. En "Homologar proveedor", asigna a Paula y configura solicitudes externas de documentos hasta que la información esté completa. En "Emitir OC", el Comprador envía la orden al proveedor, insiste hasta obtener acuse de recibo y luego solicita estado de despacho. Cuando llega la fecha de despacho, Baiyer avisa internamente al equipo.

Camila activa el ciclo. Desde ese momento, cada compra recorre el mismo grafo que ella ve. Cada envío y transición queda auditado. Puede pausar un loop, reasignar una tarea y entender por qué una instancia avanzó sin revisar cron jobs ni código.

---

## 3. Objetivos y no-objetivos

### Objetivos

- **O1 - Un solo configurador:** toda regla específica del proceso vive y se edita desde la tarjeta correspondiente del canvas.
- **O2 - Responsabilidad por acción:** cada tarjeta puede asociar uno o varios roles y uno o varios responsables por rol, con orden secuencial o modalidad paralela cuando corresponda.
- **O3 - Comunicación contextual:** cada tarjeta puede tener cero o varias comunicaciones internas y externas, basadas en el catálogo versionado de plantillas existente.
- **O4 - Loops declarativos:** una comunicación puede repetirse cada X días hasta que ocurra un evento de término, se alcance un límite o un administrador la pause.
- **O5 - Grafo ejecutable de punta a punta:** los eventos del negocio, no sólo la autorización, pueden resolver una tarjeta y mover la instancia a la siguiente conexión.
- **O6 - Seguridad contra duplicados:** reintentos del cron, webhooks o polling no duplican correos ni transiciones.
- **O7 - Trazabilidad:** todo envío, intento, evento, pausa, reasignación y transición se puede explicar desde la instancia.
- **O8 - Compatibilidad incremental:** las autorizaciones con magic link, conversaciones Gmail, RFQ agrupadas, OC y precedencia de plantillas actuales siguen funcionando durante la migración.
- **O9 - Configuración conversacional:** el chat puede proponer y corregir responsables, comunicaciones, cadencias, eventos de término y rutas, con confirmación visual antes de activar.
- **O10 - Operación segura:** ningún workflow se activa si contiene loops sin salida, acciones sin responsables requeridos, eventos sin ruta o plantillas con variables inválidas.

### No-objetivos

- **NO1:** no construir un motor BPMN genérico ni soportar cualquier proceso empresarial.
- **NO2:** no reemplazar Supabase Auth, Gmail OAuth, el agente de conversaciones, `approval_requests` ni sus magic links.
- **NO3:** no crear un diseñador visual nuevo desde cero; se extiende el canvas existente y su estilo Swiss.
- **NO4:** no permitir código, Jinja2, `eval` o condiciones arbitrarias dentro de reglas o plantillas.
- **NO5:** no automatizar decisiones subjetivas de compra, selección u homologación sin un evento o acción explícita y auditable.
- **NO6:** no considerar WhatsApp, SMS o voz en la primera versión. El modelo podrá conservar `canal`, pero el canal ejecutable inicial será email.
- **NO7:** no eliminar la biblioteca de plantillas organizacionales; cambia su papel, desde configurador paralelo a fuente de defaults reutilizables.
- **NO8:** no implementar parsing general de adjuntos PDF/Excel dentro de este alcance. La homologación podrá esperar el evento "documentación completa", aunque su validación inicialmente sea humana o use metadata ya disponible.
- **NO9:** no cambiar retroactivamente instancias activas al editar o versionar un workflow.

---

## 4. Principios del producto

1. **La tarjeta es la unidad de configuración.** Si una regla afecta sólo a una acción, debe ser visible desde esa acción.
2. **Plantilla no es automatización.** La plantilla define qué se dice; la regla de comunicación define cuándo, a quién, cuánto se insiste y qué la detiene.
3. **Evento no es estado.** Un evento es un hecho inmutable; el motor decide de forma determinística qué transición produce.
4. **Los destinatarios internos son personas de la organización; los externos se resuelven desde el contexto de la compra.** Un proveedor no se convierte en miembro ni responsable interno.
5. **Todo loop necesita escape.** Debe tener evento de término y, además, una política al agotar intentos o tiempo.
6. **La definición activa es inmutable para una instancia.** Las nuevas ediciones crean una nueva versión; compras en curso conservan la versión con la que comenzaron.
7. **Human-in-the-loop donde importa.** El sistema puede recordar y rutear; las decisiones de aprobación, selección, homologación y excepción mantienen responsable y evidencia.

---

## 5. Cómo funciona hoy

```text
Configuración del ciclo
chat -> propuesta de etapas -> grafo -> roles -> responsables globales por rol
                                      |
                                      +-> el motor real encuentra autorizadores

Configuración de correo
/settings/comunicaciones -> catálogo de 16 eventos -> override de plantilla

Ejecución real
lista -> solicitar aprobación -> workflow de autorización -> magic link
RFQ / Gmail / OC / cron -> integraciones reales parcialmente conectadas
```

### Capacidades que se deben reutilizar

- `workflow_definitions` versiona borradores, activos y archivados y guarda `nodos`/`conexiones`.
- `workflow_roles`, `responsables` y `responsable_roles` modelan personas y roles, pero la asignación actual es por workflow, no por nodo.
- `workflow_instances` y `workflow_events` entregan instancia y auditoría base.
- `workflow_engine.py` valida grafos, rutas y condiciones estructuradas sin `eval`.
- `workflow_execution.py` conecta el flujo real de autorización y debe evolucionar hacia un orquestador general.
- `approval_requests` sigue siendo la fuente real de decisiones y magic links.
- `mail_events.py` contiene 16 eventos internos/externos y defaults.
- `mail_template_definitions` ya soporta precedencia nodo > workflow > organización > default.
- `mail_template_versions` conserva historial y valida placeholders mediante allowlist.
- `mail_delivery_events` audita envíos, pero hoy no bloquea de forma suficiente un duplicado antes de enviar.
- Gmail polling interpreta respuestas y ya reconoce cotización completa, datos faltantes, acuse de OC y despacho en partes del flujo.
- `/settings/autorizaciones/canvas/[id]` ya edita nodos, rutas, roles y responsables.
- `/settings/comunicaciones` ya edita y previsualiza plantillas.

### Brechas actuales

- El rol-responsable se asigna al workflow completo, no a una tarjeta específica.
- El catálogo de correos está separado de la etapa que los usa.
- Una plantilla no expresa disparador, destinatario, frecuencia, término, timeout ni resultado.
- `approval_reminder`, `rfq_followup`, `purchase_order_ack_reminder` y otros eventos no cuentan con orquestación genérica.
- El motor comienza en un nodo de autorización aplicable, en vez de recorrer todo el ciclo desde Inicio.
- Los resultados adicionales visibles en el canvas no siempre cambian el ruteo real.
- No existe una abstracción persistida de ejecución por tarjeta ni de acción programada.
- Falta un candado previo al envío; registrar auditoría después no elimina el riesgo de duplicación.
- No existe una UX única para validar que una tarjeta tiene todo lo necesario para operar.

---

## 6. Cómo va a funcionar

```text
Chat o edición visual
        |
        v
Tarjeta de acción
  - propósito y resultados posibles
  - roles y responsables por acción
  - comunicaciones internas/externas
  - disparador, cadencia y límite
  - evento de término
  - ruta por resultado
        |
        v
Validación y activación de una versión
        |
        v
Instancia de compra fijada a esa versión
        |
        v
Entrada a tarjeta -> crea ejecución -> dispara/programa acciones
        |
        +-> evento esperado: cancela pendientes -> resuelve resultado -> avanza
        |
        +-> vencimiento: aplica política de excepción -> avanza, escala o pausa
        |
        +-> reintento técnico: misma clave -> no duplica efecto
```

### Ejemplo canónico del ciclo

1. **Preparar solicitud de cotización**
   - Rol: Cotizador.
   - Responsable: una o más personas asignadas a esa acción.
   - Correo externo inicial: `rfq_requested`.
   - Loop: `rfq_followup` cada 2 días.
   - Se detiene por proveedor al recibir `rfq_completa`, al descartar proveedor o al agotar intentos.
   - La tarjeta termina cuando se cumple el criterio agregado configurado: todos resueltos, mínimo N respuestas o cierre manual.

2. **Seleccionar lista de proveedores**
   - Rol: Cotizador.
   - Acción humana dentro de Baiyer.
   - Resultado: `seleccion_enviada` o `requiere_nueva_busqueda`.

3. **Autorizar selección**
   - Rol: Autorizador.
   - Correo interno inicial: `approval_requested` con magic link.
   - Loop: `approval_reminder` cada X días.
   - Termina por `aprobado`, `rechazado` o `devuelto`.
   - Cada resultado tiene una conexión explícita.

4. **Homologar proveedores**
   - Rol: Homologador.
   - Correo interno de asignación opcional.
   - Correo externo de solicitud de antecedentes.
   - Loop externo hasta `documentacion_completa`; si faltan datos, usa una plantilla de seguimiento.
   - Resultado por proveedor: `homologado`, `rechazado` o `vencido`.

5. **Emitir orden de compra**
   - Rol: Comprador.
   - Correo externo: `purchase_order_sent`.
   - Loop: `purchase_order_ack_reminder` hasta `oc_recepcion_confirmada`.
   - Después se consulta despacho con `dispatch_status_request` hasta `despacho_informado`.

6. **Comunicar despacho**
   - Rol: Comprador o Cotizador, según la organización.
   - Correo interno al equipo con fecha y estado del despacho.
   - Termina al registrar el aviso y avanza a Fin o a recepción conforme.

---

## 7. Modelo conceptual de una tarjeta

Toda tarjeta ejecutable responde estas preguntas:

| Dimensión | Pregunta |
|---|---|
| Acción | ¿Qué debe ocurrir? |
| Participación | ¿Qué roles intervienen? |
| Responsabilidad | ¿Qué persona actúa por cada rol en esta tarjeta? |
| Inicio | ¿Qué evento o transición activa la tarjeta? |
| Comunicaciones | ¿Qué correos internos y externos salen? |
| Destinatarios | ¿Se envía al responsable, solicitante, equipo, proveedor u otro contacto permitido? |
| Cadencia | ¿Es inmediato, diferido o recurrente cada X días? |
| Término | ¿Qué evento detiene la comunicación o resuelve la tarea? |
| Excepción | ¿Qué pasa si nadie responde o se alcanza el límite? |
| Ruta | ¿Qué resultado conecta con qué tarjeta? |

Una tarjeta puede no enviar correos. Una tarjeta automática puede no tener responsable operativo, pero debe tener un propietario de excepción o una ruta determinística. Una tarjeta humana debe tener al menos un rol y una asignación válida antes de activarse.

---

## 8. Los datos

### 8.1 Entidades existentes que se conservan

#### `workflow_definitions`

Se conserva como definición versionada. `nodos` y `conexiones` siguen representando el diseño visual y las reglas de ruteo. La versión activa no se edita en sitio: se crea borrador de nueva versión.

#### `workflow_roles`

Se conserva como catálogo de roles del workflow. Agregar `homologador` al conjunto base visible, sin impedir roles personalizados.

#### `responsables`

Se conserva como directorio interno de personas de la organización.

#### `responsable_roles`

Se conserva durante compatibilidad como asignación global/fallback. No debe seguir siendo la fuente primaria para nuevas configuraciones por tarjeta.

#### `workflow_instances`

Se conserva. Debe fijar explícitamente la definición y versión usadas por la compra. Puede ampliarse con contexto operativo, estado de pausa y motivo de cancelación, sin guardar secretos ni cuerpos completos de correo.

#### `workflow_events`

Se conserva como log inmutable y aumenta su vocabulario: entrada/salida de nodo, acción programada, correo reservado/enviado/fallido, respuesta recibida, loop agotado, tarea pausada, tarea reasignada y transición aplicada.

#### Plantillas y entregas de correo

Se conservan `mail_template_definitions`, `mail_template_versions` y `mail_delivery_events`. La precedencia nodo > workflow > organización > default sigue vigente.

### 8.2 Entidades nuevas propuestas

Los nombres son contractuales a nivel conceptual; Claude Code puede ajustar nomenclatura sólo si documenta el motivo y preserva las relaciones.

#### `workflow_node_assignments`

Asocia responsables a roles en una tarjeta específica.

| Campo | Propósito |
|---|---|
| `id` | Identidad estable |
| `workflow_id` | Versión del workflow |
| `nodo_id` | ID estable de la tarjeta dentro del JSON |
| `rol_clave` | Rol cumplido en esta acción |
| `responsable_id` | Persona interna |
| `modo` | `individual`, `paralelo` o `secuencial` |
| `orden` | Orden cuando el modo es secuencial |
| `es_propietario_excepcion` | Quién recibe escalamiento operativo |
| `created_at` | Auditoría |

Restricción única mínima: workflow + nodo + rol + responsable. Al borrar una nueva versión/borrador se borran sus asignaciones; borrar un responsable activo requiere reasignar o invalida la activación.

#### `workflow_node_communication_rules`

Define cuándo y cómo se usa una plantilla desde una tarjeta. No duplica el asunto/cuerpo.

| Campo | Propósito |
|---|---|
| `id` | Identidad de la regla |
| `workflow_id`, `nodo_id` | Tarjeta dueña |
| `rol_clave` | Rol que origina o es dueño de la comunicación |
| `evento_plantilla` | Clave del catálogo (`rfq_requested`, etc.) |
| `audiencia` | `internal` o `external`, coherente con el catálogo |
| `canal` | `email` inicialmente |
| `destinatario_tipo` | responsable del rol, solicitante, autorizador, equipo, proveedor, contacto de proveedor |
| `disparador_tipo` | al entrar, al ocurrir evento, manual, después de demora |
| `disparador_evento` | Evento requerido si corresponde |
| `demora_inicial_dias` | Espera antes del primer envío |
| `repetir_cada_dias` | `null` para envío único; entero positivo para loop |
| `max_intentos` | Límite obligatorio para loops o política explícita sin máximo |
| `evento_termino` | Hecho que cancela futuros envíos |
| `alcance_termino` | por destinatario, por proveedor o por tarjeta completa |
| `resultado_al_terminar` | Resultado de la tarjeta si el evento la resuelve |
| `politica_agotamiento` | pausar, escalar, descartar entidad, avanzar por resultado de timeout |
| `resultado_agotamiento` | Ruta explícita cuando aplique |
| `activa` | Permite apagar una regla sin borrar historial |

No se guardan direcciones externas fijas como configuración primaria. Se resuelven desde la instancia, proveedor y contactos reales. Un destinatario manual sólo se permite si pertenece a una allowlist administrativa y queda visible como excepción.

#### `workflow_node_executions`

Representa una visita concreta de una instancia a una tarjeta. Es necesaria porque un grafo puede volver a una tarjeta y cada visita necesita su propia idempotencia.

| Campo | Propósito |
|---|---|
| `id` | Ejecución de tarjeta |
| `instance_id` | Compra en curso |
| `nodo_id` | Tarjeta |
| `visit_number` | 1, 2, 3... para ciclos legítimos |
| `estado` | pendiente, activa, esperando, completada, omitida, fallida, pausada |
| `resultado` | Resultado que selecciona la conexión |
| `started_at`, `completed_at` | Tiempos |
| `context_snapshot` | Referencias y valores mínimos usados para decidir; nunca credenciales |

#### `workflow_scheduled_actions`

Cola persistida para envíos y vencimientos. El cron existente puede consumirla inicialmente.

| Campo | Propósito |
|---|---|
| `id` | Acción programada |
| `node_execution_id` | Visita a la tarjeta |
| `communication_rule_id` | Regla que la creó |
| `recipient_key` | Identidad lógica estable del destinatario/proveedor |
| `due_at` | Próxima fecha ejecutable |
| `estado` | programada, reservada, ejecutando, enviada, cancelada, fallida, agotada |
| `attempt_number` | Número de intento funcional |
| `technical_attempts` | Reintentos técnicos del mismo intento funcional |
| `lease_until` | Evita que dos workers ejecuten lo mismo |
| `last_error` | Diagnóstico seguro |
| `idempotency_key` | Candado único previo al envío |

La reserva debe ocurrir atómicamente antes de llamar a Gmail. El correo se registra como pendiente/reservado antes del envío y luego como enviado o `delivery_uncertain`. Un timeout de red después de enviar no autoriza automáticamente otro correo.

### 8.3 Catálogo de eventos

Se deben distinguir tres grupos:

- **Eventos de dominio recibidos:** `rfq_respuesta_recibida`, `rfq_completa`, `proveedor_descartado`, `seleccion_enviada`, `aprobado`, `rechazado`, `devuelto`, `documentacion_completa`, `proveedor_homologado`, `proveedor_rechazado`, `oc_emitida`, `oc_recepcion_confirmada`, `despacho_informado`, `compra_recibida`.
- **Acciones de comunicación:** los 16 eventos actuales de `mail_events.py` más los que el gap analysis apruebe.
- **Eventos técnicos/auditoría:** `node_entered`, `mail_reserved`, `mail_sent`, `mail_failed`, `schedule_cancelled`, `loop_exhausted`, `node_completed`, `transition_applied`.

El nombre de una plantilla no debe usarse por sí solo como prueba de que ocurrió el evento de dominio. Por ejemplo, enviar `purchase_order_sent` no equivale a `oc_recepcion_confirmada`.

### 8.4 Nuevos eventos de correo mínimos

El catálogo actual no cubre todo el caso. Agregar, con defaults y allowlist de variables:

- `internal_task_assigned`: se asignó una tarea interna en una tarjeta.
- `internal_task_reminder`: una tarea interna sigue pendiente.
- `homologation_information_requested`: solicitud externa de antecedentes.
- `homologation_missing_information`: faltan antecedentes de homologación.
- `homologation_approved`: aviso interno de proveedor homologado.
- `purchase_order_sent_internal`: aviso interno de OC emitida.
- `purchase_order_acknowledged_internal`: aviso interno de acuse del proveedor.
- `dispatch_announced_internal`: aviso interno con fecha/estado de despacho.

Antes de agregar cada evento, auditar los tres sitios de envío que quedaron fuera de la migración 036 y mapearlos únicamente si la semántica coincide.

---

## 9. Experiencia de configuración

### 9.1 Canvas

El canvas se mantiene como vista principal. Cada tarjeta muestra un resumen compacto:

- icono y nombre de acción;
- chips de roles;
- avatares/iniciales de responsables de esa acción;
- cantidad de comunicaciones internas y externas;
- indicador de loop, por ejemplo `cada 2 días · máx. 3`;
- evento de término principal;
- warning si la tarjeta está incompleta.

No se debe intentar mostrar el contenido de cada correo dentro de la tarjeta cerrada.

### 9.2 Panel de tarjeta

Al seleccionar una tarjeta, el panel lateral tiene cuatro secciones o tabs:

1. **Acción**
   - nombre, descripción, tipo;
   - resultados posibles;
   - condiciones de entrada si existen;
   - conexiones de salida por resultado.

2. **Responsables**
   - roles que participan en esta acción;
   - responsables por rol;
   - modo individual/paralelo/secuencial;
   - propietario de excepción;
   - crear/invitar persona usando el flujo actual.

3. **Comunicaciones**
   - lista ordenada de reglas internas y externas;
   - agregar desde catálogo;
   - destinatario resuelto en lenguaje humano;
   - disparador;
   - envío único o repetición;
   - evento de término y política de agotamiento;
   - editar plantilla sólo para este nodo;
   - previsualizar con datos de ejemplo;
   - restaurar herencia del workflow/organización/default.

4. **Validación**
   - errores y warnings de la tarjeta;
   - ejemplo narrado: "Al entrar, Ana enviará Solicitud de cotización a cada proveedor. Si no responde, repetirá cada 2 días, máximo 3 veces. Se detiene para ese proveedor cuando llega una cotización completa".

### 9.3 Biblioteca de comunicaciones

`/settings/comunicaciones` deja de presentarse como una configuración paralela del proceso.

- Se renombra visualmente como **Biblioteca de correos**.
- Explica que sus cambios son defaults de la organización.
- Desde el canvas se abre el mismo editor en contexto de nodo.
- Muestra en cuántos workflows/nodos se usa cada evento.
- No permite configurar cadencias, loops ni rutas: eso pertenece a la tarjeta.
- Si producto decide retirar la ruta del menú, debe conservar una entrada secundaria desde Configuración y enlaces profundos existentes.

### 9.4 Chat

El chat interpreta frases como:

> "En cotización, Ana escribe a los proveedores y les recuerda cada 2 días hasta que respondan, máximo 3 veces. Si no responden, descártalos. Cuando tengamos al menos 2 cotizaciones, pasa a aprobación con Rodrigo y recuérdale todos los días."

Debe proponer operaciones estructuradas, nunca editar silenciosamente una versión activa. Nuevas operaciones conceptuales:

- asignar rol a nodo;
- asignar responsable a rol en nodo;
- agregar/quitar regla de comunicación;
- configurar disparador;
- configurar repetición y máximo;
- configurar evento de término;
- configurar política de agotamiento;
- agregar resultado y conectar ruta.

Las operaciones sobre personas/invitaciones pueden seguir siendo inmediatas sólo si la UI lo deja explícito. Las reglas de workflow quedan pendientes de Guardar y sólo operan al activar la versión.

### 9.5 Simulación antes de activar

Agregar una previsualización sin efectos externos:

- el usuario elige un escenario de ejemplo;
- el sistema narra la ruta;
- muestra qué correos se programarían y cuándo;
- permite inyectar eventos como "proveedor respondió" o "autorizador rechazó";
- no crea solicitudes reales, no envía correos y no escribe delivery events.

La simulación no bloquea el MVP si retrasa el motor; sí debe existir al menos validación estática y un resumen narrado por tarjeta.

---

## 10. Pseudo-código - el acuerdo

### 10.1 Activación de un workflow

```text
CUANDO un administrador solicita activar un borrador

VALIDAR el grafo base
VALIDAR que cada tarjeta humana tenga rol y responsable por acción
VALIDAR que cada autorización tenga todas sus rutas
VALIDAR que cada regla use un evento y audiencia existentes
VALIDAR que las variables del override pertenezcan al allowlist
VALIDAR que cada destinatario se pueda resolver desde el contexto
VALIDAR que cada loop tenga evento de término
VALIDAR que cada loop tenga límite o política explícita de operación continua
VALIDAR que cada agotamiento tenga una acción determinística
VALIDAR que toda tarjeta alcanzable pueda llegar a Fin

SI hay errores
  no activar
  devolver errores asociados a tarjetas y reglas concretas

SI no hay errores
  archivar la versión activa anterior del mismo ciclo
  activar la nueva versión
  mantener las instancias existentes fijadas a su versión anterior
```

### 10.2 Inicio de una compra

```text
CUANDO una lista entra al ciclo de compras

BUSCAR el workflow activo de la organización
SI no existe
  usar el fallback legado mientras esté vigente

CREAR una instancia fijada a workflow_id y versión
ENTRAR al único nodo Inicio
RECORRER automáticamente conexiones determinísticas
AL llegar a la primera tarjeta ejecutable
  crear una ejecución de nodo con visit_number
  resolver responsables y destinatarios usando el contexto de esa compra
  crear acciones inmediatas o programadas
  registrar node_entered
```

### 10.3 Envío inmediato o programado

```text
CUANDO vence una acción programada

INTENTAR reservarla atómicamente
SI otro worker ya la reservó o terminó
  no hacer nada

VERIFICAR que la ejecución de nodo siga activa
VERIFICAR que no haya ocurrido el evento de término para su alcance
VERIFICAR que el destinatario siga vigente
VERIFICAR horario permitido y políticas de la organización

CONSTRUIR una clave idempotente con:
  instancia + visita de nodo + regla + destinatario + intento funcional

RESERVAR mail_delivery_event antes del envío
RENDERIZAR plantilla con precedencia nodo > workflow > organización > default
ENVIAR por la integración Gmail existente

SI Gmail confirma
  marcar entrega enviada
  registrar mail_sent
  programar el siguiente intento sólo si la regla es recurrente

SI el resultado es incierto
  marcar delivery_uncertain
  no reenviar automáticamente el mismo intento
  avisar al propietario de excepción

SI falla antes de enviar
  aplicar reintentos técnicos acotados al mismo intento funcional
```

### 10.4 Recepción de un evento de dominio

```text
CUANDO Gmail, una acción humana, un magic link o una API reporta un evento

NORMALIZAR el evento al vocabulario canónico
CONSTRUIR una clave idempotente desde la fuente externa
SI el evento ya fue procesado
  devolver el mismo resultado sin repetir efectos

BUSCAR la instancia y ejecución de nodo compatibles
REGISTRAR el evento inmutable
CANCELAR acciones programadas cuyo evento de término coincida y cuyo alcance aplique

SI el evento resuelve la tarjeta
  calcular resultado
  completar la ejecución una sola vez
  seleccionar exactamente una conexión por resultado
  registrar transition_applied
  entrar a la siguiente tarjeta

SI el evento sólo resuelve un proveedor dentro de una tarjeta agregada
  cerrar su loop individual
  evaluar si el criterio agregado de la tarjeta ya se cumplió
```

### 10.5 Loop de cotización por proveedor

```text
AL entrar a Solicitar cotizaciones

POR CADA proveedor incluido en la RFQ
  enviar solicitud inicial una sola vez
  programar seguimiento en X días

CUANDO llega una respuesta
  asociarla a conversación, proveedor, batch e instancia
  SI faltan campos requeridos
    emitir rfq_missing_information según la regla
    mantener abierto el loop de ese proveedor
  SI la cotización está completa
    registrar rfq_completa
    cancelar seguimientos futuros para ese proveedor

CUANDO un proveedor agota intentos
  aplicar política configurada:
    descartar proveedor, escalar o pausar

CUANDO se cumple el criterio agregado de cierre
  resolver la tarjeta con cotizaciones_recibidas
  avanzar a selección
```

### 10.6 Autorización interna

```text
AL entrar a Autorizar selección

CREAR approval_request usando la capacidad existente
ENVIAR approval_requested a los responsables habilitados
PROGRAMAR approval_reminder según modalidad secuencial/paralela

CUANDO un responsable decide
  registrar la decisión en approval_requests y workflow_events
  cancelar sus recordatorios pendientes
  recalcular la resolución usando resolver_autorizadores

SI falta otra decisión secuencial
  notificar al siguiente responsable
SI se aprueba
  avanzar por aprobado
SI se rechaza
  avanzar por rechazado
SI vuelve con observaciones
  avanzar por devuelto
```

### 10.7 Homologación

```text
AL entrar a Homologar proveedor

ASIGNAR tarea al homologador de esa tarjeta
POR CADA proveedor seleccionado que requiera homologación
  enviar solicitud de antecedentes
  programar seguimiento

CUANDO llegan antecedentes
  asociarlos al proveedor y a la ejecución
  permitir que el homologador marque:
    información incompleta, homologado o rechazado

SI incompleta
  mantener o reiniciar el seguimiento sin duplicar el intento ya enviado
SI homologado o rechazado
  cancelar acciones pendientes para ese proveedor

CUANDO todos los proveedores requeridos están resueltos
  avanzar por el resultado agregado configurado
```

### 10.8 OC, acuse y despacho

```text
AL emitir una OC
  usar el emisor existente y la plantilla purchase_order_sent
  registrar oc_emitida
  programar recordatorio de acuse

CUANDO Gmail detecta confirmación de recepción
  registrar oc_recepcion_confirmada
  cancelar recordatorios de acuse
  programar consulta de despacho si corresponde

CUANDO se informa despacho
  registrar despacho_informado con fecha y referencia
  cancelar consultas futuras
  enviar aviso interno al equipo configurado
  avanzar a la siguiente tarjeta
```

### 10.9 Pausa, cancelación y edición

```text
SI una instancia se pausa
  ninguna acción programada nueva puede enviarse
  conservar fechas y estado para reanudación explícita

SI una instancia se cancela
  cancelar todas sus acciones pendientes
  no borrar eventos ni entregas

SI se edita el workflow
  crear o modificar sólo un borrador
  no cambiar instancias ya iniciadas
```

### Promesas del motor

- Un intento funcional produce como máximo un envío efectivo conocido.
- Un evento externo se aplica como máximo una vez.
- Una ejecución de tarjeta se completa como máximo una vez.
- Todo loop tiene una salida visible y auditable.
- Ninguna edición cambia silenciosamente compras en curso.
- Ningún proveedor externo recibe acceso interno por ser destinatario.
- Las rutas reales coinciden con las conexiones visibles del canvas.

---

## 11. Reglas de validación

### Errores bloqueantes

- tarjeta humana sin rol;
- rol de tarjeta sin responsable activo;
- responsable sin email para una comunicación interna por email;
- comunicación externa sin fuente resoluble de destinatario;
- evento de plantilla inexistente o audiencia incompatible;
- loop sin evento de término;
- intervalo menor que 1 día en el MVP o no entero;
- `max_intentos` menor que 1;
- agotamiento sin política;
- resultado de término/agotamiento sin conexión;
- dos conexiones con mismo nodo origen y resultado;
- nodo o loop sin camino posible a Fin;
- placeholder no permitido o variable que el contexto de esa tarjeta no puede producir;
- configuración que intenta editar una versión activa;
- regla que confunde el envío de un correo con la recepción de un evento externo.

### Warnings no bloqueantes

- comunicación sin override: usará default heredado;
- responsable global heredado porque el nodo aún no tiene asignación específica durante la migración;
- loop sin máximo, permitido sólo con política explícita y propietario de excepción;
- demasiados destinatarios externos estimados;
- misma persona asignada a roles incompatibles en una misma acción;
- ruta de rechazo vuelve muchas veces a una tarjeta sin límite operacional, aunque estructuralmente pueda llegar a Fin.

---

## 12. Permisos y seguridad

- Sólo administradores de la organización crean, editan, activan o archivan definiciones, asignaciones y reglas.
- Miembros pueden leer el ciclo y ejecutar tareas para las que están asignados.
- Sólo el responsable asignado, su suplente vigente o un administrador puede completar/reasignar una tarea humana.
- Los magic links conservan sus controles y expiración actuales.
- El backend deriva organización y actor desde `get_auth_context`; no confía en `user_id` del body/query para endpoints nuevos.
- RLS se define por membresía organizacional, no sólo por propietario original.
- Variables de plantilla provienen de allowlists tipadas; no hay ejecución de expresiones.
- Direcciones, cuerpos renderizados y errores no deben filtrar secretos en logs.
- Los adjuntos y respuestas externas se asocian por IDs de conversación, proveedor, OC, RFQ batch e instancia, con fallback humano cuando la confianza no alcance el umbral.

---

## 13. Observabilidad y operación

Cada instancia debe ofrecer una línea de tiempo legible:

```text
09:00 Entró a Solicitar cotizaciones
09:01 Ana envió RFQ a Proveedor A y Proveedor B
2 días después Seguimiento 1 enviado a Proveedor B
1 hora después Proveedor A respondió; cotización completa
2 días después Proveedor B agotó intentos; fue descartado
10:14 La tarjeta terminó; avanzó a Seleccionar proveedores
```

Métricas mínimas:

- instancias activas por nodo;
- edad promedio y máxima por nodo;
- acciones programadas vencidas;
- envíos por evento y estado;
- tasa de respuesta por tipo de comunicación;
- loops agotados por regla;
- entregas `delivery_uncertain` pendientes de revisión;
- transiciones fallidas o eventos sin instancia asociada;
- tiempo de ciclo completo y por etapa.

Alertas operativas:

- cron/worker sin consumir acciones vencidas;
- crecimiento de acciones reservadas con lease expirado;
- aumento de errores Gmail;
- evento de dominio recibido sin ruta válida;
- workflow activo que referencia responsable desactivado.

---

## 14. Compatibilidad y migración

### Regla general

No romper el flujo productivo mientras se construye el motor general. Introducir capacidades detrás de validación y, si hace falta, feature flag por organización.

### Migración de definiciones

1. Crear las nuevas tablas mediante una migración SQL idempotente y manual, siguiendo el proceso actual de Supabase.
2. Para cada workflow existente, convertir `responsable_roles` en fallback, sin fabricar asignaciones por nodo ambiguas.
3. En la primera edición, ofrecer "Aplicar responsables actuales a todas las tarjetas con este rol" para crear asignaciones explícitas.
4. No crear reglas de comunicación recurrentes automáticamente. Sugerir defaults en UI, pero exigir confirmación administrativa.
5. Los overrides organizacionales existentes siguen activos y heredables.
6. Las instancias de autorización ya iniciadas continúan por el código actual.

### Migración de ejecución

- Fase inicial: el motor general observa y registra sin controlar envíos críticos.
- Luego gobierna recordatorios nuevos, donde hoy no existe ejecución real.
- Después gobierna entrada/salida de RFQ y autorización reutilizando emisores existentes.
- Finalmente incorpora homologación, OC, acuse y despacho.
- El fallback legado se elimina sólo cuando métricas y pruebas de producción confirman equivalencia.

### Regla de doble envío

Durante la transición, una misma acción nunca puede ser responsabilidad simultánea del camino legado y del motor nuevo. La selección de dueño debe quedar explícita por instancia/feature flag y registrada.

---

## 15. Plan de entrega

### Fase A - Fundación de datos e idempotencia

- Crear asignaciones por nodo, ejecuciones de nodo, reglas de comunicación y cola programada.
- Corregir deduplicación para reservar antes de enviar.
- Ampliar eventos y auditoría.
- Incorporar tests de concurrencia e idempotencia.

**Salida:** se puede persistir y validar el modelo sin cambiar el comportamiento productivo.

### Fase B - Configurador unificado

- Extender tarjetas y panel lateral.
- Integrar selector/editor de plantillas en contexto de nodo.
- Reposicionar `/settings/comunicaciones` como biblioteca.
- Extender chat con operaciones estructuradas.
- Agregar resumen narrado y validación por tarjeta.

**Salida:** un administrador configura el caso completo desde el canvas.

### Fase C - Scheduler y recordatorios internos

- Consumir `workflow_scheduled_actions` desde el cron actual con lease.
- Implementar asignación de tarea y reminders internos.
- Conectar autorización secuencial/paralela sin cambiar magic links.
- Agregar pausa, reanudación y manejo de `delivery_uncertain`.

**Salida:** aprobación y loops internos operan de forma real e idempotente.

### Fase D - RFQ externa por proveedor

- Conectar RFQ batch, conversación Gmail y eventos normalizados.
- Ejecutar follow-ups por proveedor.
- Implementar criterio agregado de cierre.
- Evitar duplicación entre agente Gmail y motor.

**Salida:** la tarjeta de cotización avanza a selección según respuestas reales.

### Fase E - Homologación

- Agregar eventos/plantillas mínimas.
- Crear tarea humana y seguimiento externo por proveedor.
- Permitir completar/rechazar/solicitar antecedentes.
- Enlazar homologación con emisión de compra.

**Salida:** proveedores seleccionados pueden ser homologados dentro del mismo ciclo.

### Fase F - OC, acuse, despacho y avisos internos

- Conectar emisión OC existente.
- Gobernar loops de acuse y despacho.
- Incorporar los correos internos que quedaron fuera de la migración 036.
- Completar timeline y métricas.

**Salida:** el caso narrado funciona de punta a punta.

### Fase G - Retiro controlado del fallback

- Comparar métricas y eventos con el camino legado.
- Migrar organizaciones habilitadas.
- Documentar rollback.
- Retirar bifurcaciones únicamente después de estabilidad confirmada.

---

## 16. Criterios de aceptación

### Configuración

- [ ] Un administrador puede abrir cualquier tarjeta humana y asignar responsables distintos para el mismo rol en tarjetas diferentes.
- [ ] Puede agregar múltiples comunicaciones internas y externas a una tarjeta.
- [ ] Puede usar una plantilla heredada o crear un override sólo para ese nodo.
- [ ] Puede definir envío inmediato, demorado o recurrente.
- [ ] Todo loop exige evento de término y política al agotarse.
- [ ] Cada resultado seleccionable muestra y exige una conexión.
- [ ] El resumen de la tarjeta explica la automatización en lenguaje humano.
- [ ] El chat puede proponer el flujo del ejemplo sin producir reglas invisibles o inválidas.
- [ ] Una versión activa no se modifica; se crea y activa una nueva versión.

### Ejecución

- [ ] Una nueva compra parte en Inicio y recorre tarjetas reales, no salta directamente a autorización.
- [ ] Al entrar a una tarjeta se crea exactamente una ejecución por visita.
- [ ] Dos ejecuciones concurrentes del cron no envían dos veces el mismo intento.
- [ ] Una respuesta de proveedor cancela sólo los follow-ups que corresponden a ese proveedor.
- [ ] Una respuesta incompleta mantiene el loop abierto con la plantilla correcta.
- [ ] El máximo de intentos aplica la política configurada y deja evidencia.
- [ ] Una aprobación conserva el magic link y ruteo secuencial/paralelo actual.
- [ ] Rechazo y devolución siguen conexiones diferentes si así se configuró.
- [ ] La homologación detiene recordatorios cuando los antecedentes quedan completos.
- [ ] El acuse de OC cancela recordatorios y habilita seguimiento de despacho.
- [ ] El despacho informado produce el aviso interno configurado y avanza.
- [ ] Pausar una instancia impide nuevos envíos; reanudar no duplica los anteriores.
- [ ] Editar el workflow no altera una instancia ya iniciada.

### Auditoría y seguridad

- [ ] La línea de tiempo explica quién hizo qué, cuándo, por qué regla y qué transición ocurrió.
- [ ] Todo envío referencia plantilla y versión efectivamente renderizada.
- [ ] Todo evento externo tiene clave idempotente y referencia de origen.
- [ ] Ningún endpoint nuevo confía en `user_id` enviado por el cliente.
- [ ] Un miembro de otra organización no puede leer ni mutar definiciones, acciones o eventos.
- [ ] Variables inválidas o faltantes frenan el envío antes de contactar al destinatario.

### Compatibilidad

- [ ] Organizaciones sin el nuevo motor siguen usando el flujo actual.
- [ ] RFQ agrupada, conversaciones Gmail, aprobación, OC y plantillas actuales conservan sus contratos.
- [ ] Los tres correos previamente no mapeados sólo se migran a eventos semánticamente correctos.
- [ ] Existe rollback por fase sin borrar historial ni definiciones.

---

## 17. Estrategia de pruebas

### Unitarias

- validación de reglas y destinatarios;
- siguiente nodo para todos los resultados;
- alcance de término por proveedor/destinatario/tarjeta;
- criterio agregado de cierre;
- cálculo de intentos y próxima fecha;
- resolución secuencial/paralela;
- precedencia y variables de plantillas;
- claves de idempotencia estables;
- ciclos válidos con salida y ciclos inválidos sin salida.

### Integración con base de datos

- dos workers intentando reservar la misma acción;
- evento repetido desde Gmail;
- timeout después de envío con estado incierto;
- cancelación de acciones programadas al completar;
- nueva visita a la misma tarjeta con `visit_number` distinto;
- RLS entre dos organizaciones;
- activación/versionado con instancias antiguas activas.

### End-to-end

1. RFQ a dos proveedores: uno responde completo y otro agota intentos.
2. Autorización devuelta con observaciones: vuelve a selección y reingresa a aprobación sin reutilizar recordatorios viejos.
3. Autorización secuencial de dos personas.
4. Homologación con documentos incompletos y posterior aprobación.
5. OC sin acuse, recordatorio, acuse recibido, despacho informado y aviso interno.
6. Pausa antes de un reminder y reanudación posterior.
7. Edición del ciclo mientras una compra usa la versión anterior.
8. Organización sin configuración nueva usando fallback.

### Prueba manual en producción

Usar una organización de prueba, proveedor controlado y direcciones internas reales. No activar para clientes hasta verificar delivery events, conversaciones Gmail, transiciones, cancelaciones y ausencia de duplicados durante al menos un ciclo completo.

---

## 18. Decisiones abiertas que no deben bloquear la fundación

1. **Criterio agregado de RFQ/homologación:** soportar al menos `todos_resueltos`, `minimo_respuestas` y `cierre_manual`; producto debe elegir defaults.
2. **Horario de comunicaciones:** definir zona horaria/ventana por organización. Mientras no exista configuración, usar `America/Santiago` y horario hábil documentado o no activar restricción silenciosa.
3. **Loops sin máximo:** se recomienda exigir máximo en MVP. Si se permiten, deben tener propietario de excepción y apagado manual.
4. **Suplencias:** decidir si el suplente hereda automáticamente asignaciones por nodo o requiere activación temporal.
5. **Reasignación de instancias activas:** debe cambiar ejecución futura y dejar auditoría, sin modificar la definición versionada.
6. **Homologación documental:** inicialmente humana; parsing de contenido de adjuntos queda fuera.
7. **Eventos externos ambiguos:** si una respuesta no se puede asociar con confianza, crear bandeja de excepción y no avanzar automáticamente.

Para implementar la Fase A se puede usar la alternativa conservadora indicada en cada punto. Antes de Fases D-F, las decisiones relevantes deben quedar cerradas.

---

## 19. Definición de terminado

La funcionalidad está terminada cuando una organización puede configurar desde el canvas el ciclo del caso de uso completo - cotización, selección, autorización, homologación, OC, acuse, despacho y avisos internos - y una compra real lo recorre con correos, recordatorios, eventos, responsables, excepciones y rutas auditables; sin duplicados ante reintentos; sin depender de configurar el proceso en una segunda pantalla; y sin romper los flujos productivos existentes.

---

## 20. Instrucciones para Claude Code

1. Leer `CLAUDE.md` completo antes de implementar.
2. Tratar este PRD como contrato de producto, no como permiso para reescribir componentes sanos.
3. Empezar por un inventario corto de contratos existentes y un plan por fases.
4. Implementar una fase por vez con migración, backend, frontend y pruebas proporcionales.
5. Mantener `approval_requests`, magic links, Gmail, RFQ batch, OC y servicio de plantillas como capacidades reutilizadas.
6. No asumir que una migración existe en producción sólo porque hay un archivo SQL; verificar según el proceso documentado.
7. Preparar migraciones idempotentes para ejecución manual en Supabase y esperar confirmación antes de depender de ellas en producción.
8. Usar `get_auth_context` y alcance organizacional en endpoints nuevos.
9. No editar ni descartar cambios preexistentes no relacionados del worktree.
10. Correr al menos import del backend, tests nuevos y `npx tsc --noEmit`; distinguir deuda preexistente de regresiones.
11. Actualizar `CLAUDE.md` al cerrar cada fase con estado real, migraciones aplicadas y pendientes verificables.
12. No marcar una fase completa si sólo existe UI o sólo existen tablas: debe estar conectada al comportamiento real descrito en sus criterios de salida.
