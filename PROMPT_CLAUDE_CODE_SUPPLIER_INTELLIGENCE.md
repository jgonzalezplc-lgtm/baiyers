# Prompt para Claude Code — Supplier Capability Intelligence y nuevo flujo Baiyer

Continuemos Baiyer desde el repositorio activo:

`/Users/macbook/Desktop/Cotizador`

## Reglas de trabajo

Antes de modificar nada:

1. Lee completamente `CLAUDE.md` y `PROJECT_STATUS.md`.
2. Inspecciona el estado de Git y los cambios locales.
3. Conserva todos los cambios no relacionados, especialmente `frontend/next-env.d.ts`.
4. No crees ni modifiques `AGENTS.md`.
5. Usa únicamente `CLAUDE.md` como documento de continuidad.
6. No hagas commit, push, deploy ni ejecutes migraciones en producción sin avisarme y recibir autorización explícita.
7. Las migraciones de Supabase son manuales. Puedes crear el archivo SQL, pero no aplicarlo.
8. No hagas cambios destructivos ni limpies datos existentes.
9. No reemplaces piezas existentes sin estudiar cómo reutilizarlas.
10. Antes de asumir nombres de tablas o columnas, verifica el esquema y el código real. Algunos SQL legacy no reflejan necesariamente producción.

## Objetivo general

Quiero evolucionar Baiyer desde un buscador/cotizador hacia una plataforma de `Supplier Capability Intelligence`.

Baiyer debe aprender, de forma auditable y progresiva:

- qué proveedores pueden suministrar qué categorías;
- qué subcategorías o productos específicos manejan;
- en qué territorios operan;
- qué tan confiable es esa relación;
- qué proveedores funcionan mejor para cada usuario;
- qué categorías compra probablemente cada empresa;
- qué proveedores deben recibir cada ítem de un proyecto;
- cómo mejorar con búsquedas, respuestas, cotizaciones, compras y feedback.

El activo principal de Baiyer debe ser una red de evidencia que represente:

`empresa usuaria → contexto de compra → ítem → categoría → proveedor → evidencia → resultado`

## Casos de uso esperados

### Capacidad de proveedores

Una empresa X puede suministrar categorías A, B y C, pero no D, E o F.

Si se busca un ítem clasificado en A, Baiyer debe priorizar proveedores con evidencia en A y evitar consultar proveedores especializados exclusivamente en D, E o F.

No debe ser un filtro completamente rígido: si la búsqueda dirigida falla, Baiyer debe poder ampliar la búsqueda.

### Aprendizaje colectivo

Mientras más usuarios utilicen Baiyer, mejor debería quedar mapeado:

- qué proveedor abastece qué categoría;
- qué productos específicos cotiza;
- qué territorios atiende;
- con qué frecuencia responde;
- qué tan confiable es.

El aprendizaje global nunca debe exponer precios, contactos, condiciones comerciales, correos ni información privada de otros clientes.

### Búsqueda expandida

Si el modelo clasifica un ítem I como categoría A, pero no aparecen resultados satisfactorios:

1. El usuario debe poder pulsar `No encontré lo que buscaba`.
2. Baiyer debe registrar por qué falló la búsqueda.
3. Debe permitir ampliar la búsqueda a categorías relacionadas, fuentes genéricas o todas las fuentes.
4. Si el usuario selecciona proveedores encontrados en la búsqueda expandida, eso genera evidencia.
5. La selección por sí sola no confirma una categoría.
6. Una respuesta válida, precio, disponibilidad, OC o compra completada debe tener más peso.
7. Una corrección explícita del usuario debe considerarse una señal fuerte.

### Cotización inteligente de proyectos

Dada una lista:

- N y M pertenecen a A;
- O y P pertenecen a D;
- Q y R pertenecen a D/E/F.

Si Baiyer conoce que:

- X abastece A;
- Y abastece D;
- Z abastece D/E/F;

debe poder generar:

- correo a X cotizando N y M;
- correo a Y cotizando O y P;
- correo a Z cotizando Q y R.

No debe enviar automáticamente la lista completa a todos.

Un mismo ítem puede enviarse a varios proveedores para mantener competencia. El objetivo futuro es seleccionar entre 2 y 5 proveedores adecuados por ítem y agrupar los correos eficientemente.

## Estado existente que debes reutilizar

Ya existen, entre otras piezas:

- `proveedores`: directorio privado por usuario;
- `proveedor_contactos`: contactos múltiples;
- matching por RUT, dominio, email y nombre;
- `supplier_categories`: asociación básica usuario/proveedor/categoría/keywords;
- `supplier_intelligence.py`: score general;
- `categoria_mapper.py`: categorías hacia fuentes y proveedores custom;
- `resultados`: resultados y respuestas de cotización;
- `procurement_ledger`: historial del ciclo de compra;
- agente Gmail con conversaciones, mensajes, extracción, propuestas y autoaplicación;
- listas multiítem;
- resultados definitivos;
- proyectos/listas de materiales;
- aprobaciones;
- órdenes de compra;
- rating de proveedores;
- onboarding conversacional con investigación de empresa;
- datos de onboarding almacenados actualmente en `user_metadata`.

No reemplaces estas piezas antes de inspeccionarlas. Diseña una evolución incremental y compatible.

# Principios de arquitectura

## 1. Identidad global y relación privada

Separa conceptualmente:

### Identidad global

Una empresa proveedora real debería tener una identidad canónica:

```text
supplier_entities
- id
- nombre_canonico
- rut
- dominio
- sitio_web
- país
- regiones_atendidas
- aliases
- estado_verificacion
- timestamps
```

### Relación privada usuario–proveedor

Cada usuario mantiene su propia relación:

```text
user_suppliers
- id
- user_id
- supplier_entity_id
- nombre_interno
- bloqueado
- preferido
- contactos_preferidos
- condiciones_negociadas
- notas_privadas
- score_privado
- timestamps
```

Evalúa si la tabla actual `proveedores` puede seguir siendo esta relación privada incorporando opcionalmente `supplier_entity_id`.

No hagas ahora una migración destructiva ni reemplaces `proveedores`.

## 2. Capacidades con confianza

La relación proveedor–categoría no debe ser sólo un booleano.

Debe representar:

- proveedor;
- usuario, cuando sea conocimiento privado;
- categoría;
- subcategoría;
- concepto de producto opcional;
- territorio;
- estado: `probable`, `confirmed` o `rejected`;
- confianza;
- evidencia positiva y negativa;
- cotizaciones válidas;
- compras;
- última evidencia;
- timestamps.

Ejemplo:

```text
Proveedor X → Material eléctrico → confianza 0.94
Proveedor X → Cables THHN → confianza 0.98
Proveedor X → Madera estructural → confianza 0.08
```

## 3. Evidencia inmutable

Cada aprendizaje debe provenir de un evento auditable:

- `appeared_in_search`;
- `search_result_relevant`;
- `search_result_rejected`;
- `supplier_selected_for_rfq`;
- `supplier_replied_can_supply`;
- `supplier_replied_cannot_supply`;
- `valid_quote_received`;
- `supplier_selected`;
- `purchase_approved`;
- `purchase_completed`;
- `user_corrected_category`;
- `no_satisfactory_results`.

No sobrescribas conocimiento sin conservar la evidencia que lo originó.

## 4. Peso de las evidencias

No concluyas que un proveedor abastece una categoría sólo porque apareció en Google o fue seleccionado.

Usa pesos configurables y explicables. Como referencia:

```text
appeared_in_search             +0.05
search_result_relevant         +0.15
supplier_selected_for_rfq      +0.30
supplier_replied_can_supply    +0.60
valid_quote_received           +0.75
supplier_selected              +0.85
purchase_approved              +0.90
purchase_completed             +1.00
search_result_rejected         -0.60
supplier_replied_cannot_supply -0.80
```

Estos valores son iniciales. La implementación debe permitir cambiarlos.

## 5. Privado versus global

Debe permanecer privado:

- precios;
- contactos;
- cuerpos de correos;
- condiciones comerciales;
- notas;
- bloqueos;
- preferencias;
- volúmenes;
- historial individual;
- decisiones internas.

Puede convertirse en conocimiento global agregado:

- identidad canónica;
- categorías públicamente abastecidas;
- conceptos cotizados exitosamente;
- territorios;
- capacidad agregada proveedor–categoría;
- estadísticas anonimizadas.

No implementes todavía aprendizaje compartido entre clientes. La primera versión debe aprender sólo por usuario, dejando una ruta futura para agregación anónima.

# Contexto de empresa obtenido en onboarding

Baiyer ya tiene un onboarding conversacional que investiga y guarda datos en `user_metadata`, como:

- empresa;
- industria;
- RUT;
- país;
- dominio;
- categorías por defecto;
- proceso de compra;
- nombre del usuario;
- logo;
- otros datos investigados.

Quiero usar esto para crear un perfil inicial de procurement.

Ejemplo:

Si se registra `juan@enel.cl`, Baiyer puede inferir:

- empresa: Enel;
- industria: energía;
- país: Chile;
- categorías probablemente frecuentes: eléctrico, automatización, instrumentación, seguridad industrial, construcción y servicios técnicos;
- tipos de proveedores probablemente relevantes.

Este perfil debe orientar y priorizar, pero nunca imponerse sobre lo que el usuario busca.

La regla de precedencia debe ser:

```text
intención explícita del ítem
> contexto del proyecto
> historial real del usuario
> perfil de la empresa
> conocimiento global
```

Si una empresa de energía busca sillas ergonómicas, Baiyer debe buscar mobiliario, no forzar proveedores eléctricos.

## Perfil de procurement

Diseña una representación estructurada, por ejemplo:

```text
organization_procurement_profiles
- id
- user_id o organization_id
- empresa
- dominio
- industria
- país
- descripción_actividad
- categorías_probables
- tipos_proveedores_probables
- keywords_compra
- señales_origen
- timestamps
```

No guardes únicamente una lista plana. Cada categoría sugerida debe incluir:

- categoría;
- confianza;
- origen;
- confirmación del usuario;
- evidencia acumulada;
- última evidencia.

Orígenes posibles:

- `onboarding`;
- `industry_prior`;
- `user_confirmed`;
- `search_history`;
- `quote_history`;
- `purchase_history`.

Ejemplo:

```json
[
  {
    "category": "electrico",
    "confidence": 0.92,
    "sources": ["industry_prior", "onboarding"],
    "confirmed_by_user": false
  },
  {
    "category": "automatizacion",
    "confidence": 0.84,
    "sources": ["industry_prior"],
    "confirmed_by_user": false
  }
]
```

Evalúa si esto debe ser una tabla nueva normalizada o una evolución segura del esquema actual. Prefiero una tabla auditable si el perfil evolucionará con el uso.

## Generación inicial

Al completar o actualizar el onboarding:

1. Normalizar empresa, dominio, industria y país.
2. Generar categorías de compra probables.
3. Asignar confianza y explicación.
4. Permitir confirmar, agregar o quitar categorías.
5. Distinguir:
   - lo inferido por IA;
   - lo confirmado por el usuario;
   - lo aprendido mediante uso real.

No uses el dominio como única verdad:

- distingue dominios corporativos y genéricos;
- considera subsidiarias;
- considera consultores y contratistas;
- un usuario podría comprar para más de una organización.

Para dominios genéricos usa principalmente la información declarada en onboarding.

## Uso en identificación y búsqueda

El perfil debe utilizarse como prior:

1. El modelo identifica el ítem por su contenido.
2. El perfil ayuda a resolver ambigüedades.
3. El proyecto tiene más peso que el perfil general.
4. El historial real supera gradualmente la inferencia inicial.
5. El buscador prioriza fuentes y proveedores relevantes.
6. Las fuentes genéricas y la expansión siguen disponibles.
7. La ausencia de una categoría en el perfil no es evidencia negativa.
8. Reserva capacidad de exploración para descubrir necesidades nuevas.

Fórmula conceptual inicial:

```text
supplier_ranking =
  40% correspondencia con el ítem
+ 20% capacidad proveedor–categoría
+ 15% experiencia privada del usuario
+ 10% contexto del proyecto
+ 5% perfil/industria
+ 10% calidad del proveedor
```

El perfil empresarial nunca debe dominar la intención explícita.

## Evolución del perfil

```text
onboarding                  → prior inicial
búsqueda                    → señal débil
selección para cotizar      → señal media
respuesta válida            → señal fuerte
compra completada           → confirmación
corrección del usuario      → señal explícita
```

Evita el ciclo de confirmación donde Baiyer sólo busca en las categorías inicialmente inferidas y nunca descubre necesidades distintas.

No unas automáticamente cuentas por dominio. Deja preparado el futuro modelo:

- `organizations`;
- `organization_members`;
- `organization_procurement_profiles`;
- `organization_suppliers`.

No lo implementes todavía si el modelo actual no lo soporta.

# Estado operativo y consistencia visual

## 1. Estado de los agentes arriba del dashboard

El estado operativo debe quedar visible en la zona superior del dashboard, no escondido al final.

### Agente Gmail

Mostrar:

- verde + `✓`: Gmail conectado y operativo;
- amarillo + `!`: integración existente que requiere atención, reconexión o validación;
- rojo + `×`: Gmail no conectado.

La condición debe provenir del estado persistente real, nunca de parámetros temporales como `?gmail=conectado`.

No basta con que exista una fila en `user_integrations`. Si es seguro y viable, diferencia entre:

- integración existente;
- refresh token presente;
- credenciales utilizables;
- error reciente de sincronización.

No expongas tokens ni información sensible.

### Ciclo de autorizaciones

Mostrar:

- verde + `✓`: ciclo configurado y activo;
- amarillo + `!`: configuración incompleta o sin aprobadores;
- rojo + `×`: no configurado.

Inspecciona y reutiliza el modelo real:

- `approval_workflows`;
- configuración en `user_metadata`;
- flujo de listas y autorizaciones;
- enlace `Editar ciclo de autorizaciones`.

No inventes una segunda fuente de verdad si ya existe una estructura utilizable.

Cada indicador debe incluir etiqueta, icono, color accesible, texto breve y acción para configurar o corregir. El color no puede ser la única señal.

## 2. Corregir cambio inesperado de tema

Actualmente, al pasar desde el dashboard oscuro hacia `Nueva cotización`, el fondo cambia a claro.

Investiga la causa real:

- layouts;
- variables CSS;
- theme provider;
- atributos en `html` o `body`;
- hidratación;
- estilos hardcodeados;
- estilos legacy.

Mantén consistentemente el tema seleccionado entre:

- dashboard;
- nueva cotización;
- identificación;
- lista de materiales;
- cotización a proveedores;
- resultados;
- listas;
- aprobaciones.

No fuerces todo a oscuro ni todo a claro. Respeta la preferencia existente.

Usa tokens actuales como `var(--surface)`, `var(--canvas)`, `var(--brand)`, `var(--n-*)` y `var(--st-*)`.

# Nuevo flujo para proyectos y listas multiítem

El flujo deseado es:

```text
Dashboard
→ Nueva cotización
→ Describir proyecto/necesidad
→ Identificación del proyecto
→ Lista de materiales e ítems con cantidades
→ Cotización a proveedores de confianza
→ Resultados y búsqueda complementaria
→ Respuestas por correo y cuadro comparativo
→ Selección
→ Aprobaciones
→ Orden de compra y/o lista de compra
```

## 1. Identificación y lista de materiales

Cuando el usuario describe un proyecto:

1. Identificar que se trata de un proyecto.
2. Generar materiales o servicios.
3. Incluir cantidades y unidades.
4. Asignar una o más categorías candidatas por ítem.
5. Incluir confianza por categoría.
6. Permitir corregir nombre, descripción, cantidad, unidad y categorías.
7. Guardar correcciones como evidencia explícita.

Cada ítem debe mantener una identidad estable durante todo el flujo. No depender sólo de su posición en un JSON.

Si las listas se guardan en `proyectos.descripcion`, evalúa cómo agregar IDs estables sin romper compatibilidad.

## 2. Paso “Cotización a proveedores de confianza”

Entre la lista de materiales y resultados debe existir:

`Cotización a proveedores de confianza`

Debe utilizar:

- categorías del ítem;
- perfil de procurement;
- historial privado;
- `supplier_capabilities`;
- `supplier_categories`;
- proveedores registrados;
- contactos;
- bloqueos y preferencias;
- score y desempeño;
- territorio.

No debe buscar inicialmente en todo internet. Su objetivo es aprovechar la red de proveedores conocidos del usuario.

## 3. Matriz ítem–proveedor

Construye una matriz de cobertura.

Ejemplo:

```text
Proveedor A → X, Y, Z
Proveedor B → X, Y, M
Proveedor C → O, P, Z
```

Internamente:

```text
Proveedor A:
- X: confianza 0.94
- Y: confianza 0.88
- Z: confianza 0.72
```

La pantalla debe mostrar por proveedor:

- nombre;
- contacto y correo;
- score;
- categorías relevantes;
- ítems probables;
- confianza o explicación;
- estado de contacto/Gmail;
- selección.

Y por ítem:

- cantidad;
- unidad;
- categoría;
- proveedores candidatos;
- proveedores seleccionados;
- cobertura.

Usa `proveedor_id`, `contacto_id`, `item_id`, `cotizacion_id` y relaciones estables, no sólo nombres.

## 4. Selección y cobertura visual

Al seleccionar un proveedor:

- incluir sus ítems compatibles;
- marcar cada ítem cubierto con `✓`;
- destacarlo en verde;
- mostrar cuántos proveedores lo cotizarán.

Estados:

- verde + `✓`: cubierto por al menos un proveedor;
- amarillo + `!`: sólo un proveedor o confianza baja;
- rojo + `×`: sin proveedor;
- neutro: no revisado.

No dependas sólo del color.

Permite editar manualmente qué ítems van en el correo de cada proveedor.

Antes de continuar, mostrar resumen:

```text
12 ítems totales
9 cubiertos
3 sin proveedor
5 proveedores seleccionados
14 solicitudes ítem–proveedor
```

No bloquees necesariamente si faltan ítems, pero muestra warning y pide confirmación.

## 5. Correos agrupados por proveedor

Una vez confirmada la matriz:

- generar un correo por proveedor;
- incluir sólo sus ítems asignados;
- incluir descripción, cantidad, unidad y especificaciones;
- pedir precio, moneda, disponibilidad, plazo y condiciones;
- permitir revisar y editar;
- reutilizar Gmail existente;
- registrar conversación y asociaciones;
- mantener threading, cron y agente existentes.

La solución debe soportar:

```text
una conversación Gmail
→ un proveedor
→ varios ítems
→ varias actualizaciones de resultados
```

No generes una conversación por ítem si se envió un solo correo agrupado.

Evalúa crear:

```text
rfq_batches
- id
- user_id
- lista/proyecto
- supplier_id
- contacto_id
- conversation_id opcional
- estado
- timestamps

rfq_batch_items
- id
- rfq_batch_id
- item_id
- cotizacion_id
- resultado_id opcional
- cantidad
- estado
- timestamps
```

Adapta nombres y relaciones al esquema real y garantiza idempotencia.

## 6. Ítems sin proveedor

Si algunos ítems no quedaron en ningún correo:

1. marcarlos;
2. explicar que faltan proveedores de confianza;
3. llevarlos con prioridad a resultados;
4. iniciar búsqueda general con esos ítems;
5. permitir opcionalmente buscar alternativas para los ya cotizados.

Texto sugerido:

> Primero buscaremos proveedores para los ítems que aún no están cubiertos. También puedes buscar alternativas para los ítems que ya se enviaron a tus proveedores de confianza.

Separar en resultados:

### Requieren proveedores

Ítems sin cobertura que deben buscarse en fuentes por categoría, categorías alternativas, fuentes genéricas y expansión.

### Ya cotizados

Ítems enviados a proveedores de confianza:

- no repetir búsqueda automáticamente;
- permitir `Buscar más alternativas`;
- mostrar proveedores contactados;
- evitar duplicar correos y resultados.

## 7. Continuidad existente

Después del envío:

1. cron Gmail procesa respuestas;
2. agente interpreta respuestas multiítem;
3. actualiza resultados por ítem;
4. envía seguimiento o agradecimiento;
5. cuadro comparativo muestra respuestas;
6. usuario selecciona definitivos;
7. continúa aprobación;
8. al aprobar sin observaciones comienza compra;
9. se emite OC y/o lista de compra.

No construyas un flujo paralelo: integra el nuevo paso al existente.

## 8. Explicación de recomendaciones

Cada relación proveedor–ítem debe explicar por qué aparece:

- categoría manual;
- onboarding;
- cotización anterior;
- compra anterior;
- proveedor preferido;
- keywords;
- capacidad inferida;
- desempeño;
- alta manual.

Ejemplo:

> Recomendado porque ha cotizado material eléctrico anteriormente y está asociado a Cables y Automatización.

Evita precisión falsa. Indica confianza baja cuando corresponda.

# Gestión y alta de proveedores

## 1. Mantener importación Excel/CSV

La importación debe seguir funcionando y reutilizar:

- matching por RUT;
- email/dominio;
- nombre;
- contactos;
- categorías;
- deduplicación.

No crees registros paralelos.

## 2. Alta manual

Agrega `Agregar proveedor manualmente` con:

- nombre;
- RUT opcional;
- sitio web opcional;
- país;
- email;
- contacto opcional;
- teléfono opcional;
- categorías;
- subcategorías o keywords;
- notas privadas opcionales;
- preferido/bloqueado.

Permite seleccionar varias categorías y guardar aunque no exista información pública.

## 3. Investigación automática

Al ingresar nombre, dominio o sitio web, ofrecer:

`Investigar y recomendar categorías`

Similar al onboarding:

1. investigar proveedor;
2. identificar razón social;
3. RUT con evidencia suficiente;
4. dominio;
5. descripción;
6. industria;
7. productos/servicios;
8. categorías;
9. subcategorías;
10. keywords;
11. territorio;
12. confianza;
13. explicación/fuentes.

El usuario debe revisar y confirmar antes de guardar categorías.

Distingue información detectada, confirmada y aprendida posteriormente. No inventes datos.

Reutiliza onboarding cuando sea razonable, sin confundir el perfil del comprador con el del proveedor.

## 4. Ficha del proveedor

Debe poder mostrar:

- identidad;
- contactos;
- categorías manuales;
- categorías inferidas;
- capacidades aprendidas;
- confianza;
- evidencia;
- historial;
- respuestas;
- OCs;
- rating;
- bloqueos/preferencias.

Las correcciones deben generar eventos auditables.

# Alcance de datos de la primera implementación

Diseña la siguiente migración numerada después de inspeccionar `backend/migrations/`.

Como mínimo, evalúa incluir:

## `procurement_profiles`

- perfil por usuario inicialmente;
- empresa, dominio, industria y país;
- categorías probables estructuradas;
- keywords;
- origen, confianza y confirmación;
- timestamps.

## `search_sessions`

- usuario;
- cotización/proyecto/lista opcional;
- ítem original;
- categoría predicha;
- categorías utilizadas;
- términos;
- modo `directed` o `expanded`;
- sesión padre;
- cantidad de resultados;
- estado;
- timestamps.

## `search_feedback`

- sesión;
- usuario;
- tipo;
- categoría predicha;
- categoría corregida;
- comentario;
- timestamps.

Tipos:

- `wrong_products`;
- `missing_suppliers`;
- `wrong_category`;
- `expand_search`;
- `satisfactory`.

## `supplier_capability_events`

- usuario;
- proveedor;
- resultado/cotización/sesión opcional;
- categoría predicha y confirmada;
- concepto normalizado;
- tipo;
- peso;
- clave de idempotencia;
- metadata;
- timestamps.

## `supplier_capabilities`

Prefiere separarla de `supplier_categories` si ésta representa configuración manual:

- usuario;
- proveedor;
- categoría;
- concepto opcional;
- confianza;
- evidencia positiva/negativa;
- cotizaciones válidas;
- compras;
- estado;
- última evidencia;
- timestamps.

## `rfq_batches` y `rfq_batch_items`

Para representar correos agrupados por proveedor y asociaciones multiítem.

Incluye foreign keys compatibles, índices, constraints, claves únicas, RLS, políticas por usuario e idempotencia.

No apliques la migración.

# Servicio de dominio

Crea o propone un servicio central como:

`backend/app/services/supplier_capability_intelligence.py`

Responsabilidades:

- registrar eventos idempotentes;
- definir pesos;
- recalcular capacidades desde eventos;
- consultar capacidades;
- rankear proveedores;
- explicar scores;
- actualizar perfiles con evidencia;
- mantener lógica fuera de routers y UI.

El cálculo inicial debe ser determinístico y explicable. Evita ML opaco y operaciones inseguras de leer contador y luego escribir.

# Integración con flujos existentes

Registra eventos donde sea seguro:

- resultado mostrado;
- relevante/irrelevante;
- proveedor seleccionado para RFQ;
- respuesta con o sin disponibilidad;
- cotización válida;
- resultado definitivo;
- aprobación limpia;
- compra completada;
- búsqueda insatisfactoria;
- corrección de categoría.

Además:

- carga el perfil al identificar y buscar;
- pásalo como contexto estructurado;
- registra componentes del ranking;
- genera/actualiza perfil al completar onboarding;
- permite revisar categorías;
- evita duplicados en reintentos.

# Orden de implementación

No intentes completar todo simultáneamente. Propón y trabaja por fases:

## Fase 1 — Fundaciones

- perfil de procurement;
- sesiones de búsqueda;
- feedback;
- eventos;
- capacidades;
- IDs estables;
- `rfq_batches` si corresponde;
- tests e idempotencia.

## Fase 2 — Estado y tema

- indicadores Gmail y autorizaciones arriba;
- consistencia del tema;
- estados accesibles.

## Fase 3 — Proveedores

- alta manual;
- categorías manuales;
- investigación;
- sugerencias y confirmación;
- deduplicación.

## Fase 4 — Proveedores de confianza

- matriz;
- ranking;
- selección;
- cobertura;
- warnings;
- explicaciones.

## Fase 5 — RFQ agrupada

- un correo por proveedor;
- varios ítems;
- revisión;
- Gmail;
- conversación multiítem;
- idempotencia.

## Fase 6 — Búsqueda complementaria

- priorizar ítems sin cobertura;
- búsqueda opcional de cubiertos;
- expansión;
- feedback;
- deduplicación.

## Fase 7 — Continuidad completa

- respuestas;
- comparador;
- selección;
- aprobaciones;
- compra;
- OC/lista de compra.

Antes de implementar, explícame qué parte cabe de forma segura en esta sesión. No sacrifiques integridad por intentar completar todas las fases de una vez.

# Lo que no debes implementar todavía

- aprendizaje global entre clientes;
- unión automática de cuentas por dominio;
- envío de RFQs sin revisión de matriz y borradores;
- embeddings si no son indispensables;
- reemplazo completo de `proveedores`;
- migraciones destructivas;
- backfill masivo sin idempotencia;
- ML opaco;
- cambios no relacionados;
- reparación general de TypeScript;
- parseo nuevo de adjuntos salvo necesidad directa.

Sí debes dejar preparado el envío agrupado después de confirmación humana.

# Seguridad y privacidad

- No expongas secretos ni tokens.
- No mezcles usuarios.
- Valida pertenencia en endpoints.
- Mantén RLS.
- Usa IDs cuando existan.
- Reutiliza matching existente.
- No compartas precios, contactos, emails, volúmenes o condiciones.
- Mantén auditoría.
- No aceptes `user_id` arbitrario como única autorización para datos privados si puedes seguir o mejorar el patrón de autenticación.
- Reporta endpoints inseguros, sin ampliar alcance sin explicarlo.

# Proceso solicitado

1. Inspecciona código, migraciones y esquema.
2. Antes de implementar explícame:
   - piezas reutilizadas;
   - modelo de datos;
   - archivos;
   - endpoints;
   - onboarding;
   - búsqueda;
   - Gmail multiítem;
   - idempotencia;
   - riesgos;
   - compatibilidad.
3. Presenta un plan incremental.
4. Implementa sólo la fase acordada o el primer corte vertical seguro.
5. Verifica:
   - import del backend;
   - migración;
   - cálculo;
   - idempotencia;
   - aislamiento;
   - feedback;
   - expansión;
   - onboarding;
   - frontend;
   - regresiones del flujo existente.
6. Distingue errores nuevos de deuda TypeScript.
7. Actualiza sólo `CLAUDE.md` para continuidad.
8. Muéstrame archivos, migración, pruebas, resultados, instrucciones, riesgos y siguiente fase.
9. No hagas commit, push, deploy ni apliques migraciones sin autorización.

# Criterios de aceptación

- El onboarding genera perfil inicial con confianza y origen.
- Se distinguen categorías inferidas y confirmadas.
- El perfil orienta sin forzar.
- Búsquedas fuera de la industria funcionan.
- Cada búsqueda tiene sesión.
- Existe `No encontré lo que buscaba`.
- Puede ejecutarse expansión relacionada con la búsqueda original.
- Eventos son idempotentes.
- Existe capacidad privada proveedor–categoría explicable.
- El historial supera gradualmente el prior.
- Gmail y autorizaciones aparecen arriba con estado real.
- Tema se conserva entre pantallas.
- Proyecto genera ítems con cantidad, unidad, categorías e IDs estables.
- Existe `Cotización a proveedores de confianza`.
- Existe matriz proveedor–ítem editable.
- Cada ítem muestra cobertura con color, icono y texto.
- Ítems sin cobertura producen warning.
- Se genera un correo por proveedor sólo con sus ítems.
- Una conversación Gmail puede asociarse a varios ítems.
- Ítems sin proveedor pasan primero a búsqueda general.
- Ítems ya cotizados no se repiten salvo decisión del usuario.
- Flujo continúa a comparador, aprobación y compra.
- Puede agregarse proveedor manualmente.
- Pueden seleccionarse categorías manualmente.
- Puede investigarse y recomendarse categorías.
- Usuario confirma información inferida.
- No se duplican proveedores, correos, conversaciones ni eventos.
- No se mezclan datos privados.
- No se rompen búsqueda, Gmail, listas, aprobaciones ni proyectos.
- `frontend/next-env.d.ts` queda preservado.
- `CLAUDE.md` refleja el estado real.

La idea central es:

```text
El onboarding genera hipótesis iniciales.
Las búsquedas generan señales débiles.
Las selecciones generan intención.
Las respuestas generan evidencia fuerte.
Las compras generan conocimiento confirmado.
Las correcciones explícitas tienen prioridad.
```

Empieza inspeccionando el repositorio y presentándome el diseño y el plan antes de crear una migración incompatible. Si el esquema real difiere de esta propuesta, adáptate al sistema existente y explícame por qué.
