# Plan de implementación — Rediseño del canvas de ciclo de compras

## Objetivo

Rediseñar el frontend de `/settings/autorizaciones/canvas/[id]` para que el grafo sea el elemento principal de la pantalla y tenga el máximo espacio disponible, sin perder ninguna capacidad existente.

El nuevo layout debe:

1. Mover el chat de correcciones desde la columna lateral a una terminal inferior colapsable.
2. Convertir el panel fijo de propiedades en un drawer flotante que se abre al seleccionar una tarjeta.
3. Mover la paleta de nodos al extremo superior derecho y hacerla desplegable.
4. Incorporar zoom, restablecimiento de vista y navegación por paneo dentro del grafo.
5. Mantener todas las acciones actuales, incluidos botones de agregar (`+`), eliminar/basurero, cerrar, conectar, editar, guardar, validar, ordenar y activar.

Este cambio es exclusivamente de UX y composición del canvas. No debe modificar el modelo de datos, contratos del backend, reglas de validación ni semántica del workflow.

## Archivo principal

- `frontend/app/settings/autorizaciones/canvas/[id]/page.tsx`

Componentes relacionados que pueden extraerse o adaptarse:

- `frontend/components/workflow/NodeCommunicationsPanel.tsx`
- `frontend/components/workflow/MailTemplateEditor.tsx`
- `frontend/components/ui/index.tsx`

Antes de implementar, leer `CLAUDE.md` y respetar las convenciones visuales y arquitectónicas existentes.

## Principio central de UX

El lienzo debe dominar la pantalla. Las herramientas secundarias aparecen bajo demanda y flotan sobre el grafo, sin reducir permanentemente su ancho.

La jerarquía es:

1. Grafo.
2. Tarjeta seleccionada y sus propiedades.
3. Chat de correcciones.
4. Paleta para agregar nodos.

## Layout esperado

### Barra superior

Mantener las acciones actuales:

- Volver a Configuración.
- Nombre del ciclo.
- Estado `Borrador` o `Ciclo activo`.
- `Ordenar automáticamente`.
- `Validar`.
- `Guardar`, cuando corresponda.
- `Activar`, cuando corresponda.
- `Crear borrador con estos cambios`, cuando corresponda.

No eliminar ni esconder acciones según el ancho sin ofrecer una alternativa accesible.

### Lienzo maximizado

El grafo ocupa todo el ancho disponible y el espacio vertical entre la barra superior y la terminal inferior.

Debe conservar:

- Tarjetas existentes.
- Conexiones y flechas.
- Colores de resultados aprobado/rechazado.
- Puntos de entrada y salida.
- Acción de conectar nodos.
- Arrastre de tarjetas.
- Selección de tarjetas.
- Botón basurero de cada tarjeta editable.
- Estados visuales de selección, conexión y solo lectura.
- Conteos de responsables y comunicaciones.
- Chip o indicador de loop.

### Zoom y navegación

Agregar controles flotantes en la esquina inferior izquierda del lienzo:

- Botón `−` para alejar.
- Indicador con porcentaje actual.
- Botón `+` para acercar.
- Acción sobre el porcentaje para restablecer a `100%` y volver al origen.

Interacciones:

- Zoom mínimo sugerido: `50%`.
- Zoom máximo sugerido: `175%`.
- Incrementos de `10%`.
- Paneo arrastrando una zona vacía del lienzo.
- El arrastre de fondo no debe interferir con el drag de tarjetas.
- El zoom debe aplicarse a nodos, conexiones y etiquetas como una sola superficie.
- Las coordenadas persistidas de las tarjetas continúan representando coordenadas del mundo, no coordenadas transformadas por zoom o paneo.
- Opcional si es seguro: zoom con rueda + `Ctrl/Cmd` o trackpad.

Mantener los controles accesibles con `aria-label` y foco de teclado visible.

## Paleta de nodos desplegable

Mover la paleta actual al extremo superior derecho del lienzo.

Estado cerrado:

- Mostrar un botón compacto con `+`.
- Tooltip o `aria-label`: `Agregar nodo`.
- No debe tapar una porción significativa del grafo.

Estado abierto:

- Mostrar un popover flotante con todos los tipos actuales de nodo.
- Conservar la acción para añadir cada tipo.
- Cerrar al seleccionar un tipo, al volver a pulsar `+` o al hacer clic fuera.
- No cerrar al interactuar dentro del popover salvo que se seleccione una opción.

Tipos actuales que deben conservarse:

- Tarea humana.
- Revisión.
- Autorización.
- Decisión / condición.
- Acción automática.
- Homologación.
- Emisión de OC.
- Compra sin OC.
- Espera de documento.

No eliminar el botón `+` ni sustituirlo por una tarjeta permanentemente visible.

## Drawer flotante de la tarjeta

Al seleccionar una tarjeta humana, abrir suavemente un drawer flotante sobre el costado derecho del grafo.

Comportamiento:

- Animación corta de entrada desde la derecha, entre 200 y 300 ms.
- Fondo opaco y sombra suficiente para separarlo del grafo.
- No cambiar el ancho del lienzo al abrirse.
- Scroll vertical interno cuando el contenido exceda la altura.
- Botón `×` visible para cerrar.
- Cerrar también al seleccionar otra tarjeta, reemplazando el contenido.
- Mantener el nodo seleccionado resaltado mientras el drawer esté abierto.
- En móvil o pantallas angostas, usar casi todo el ancho disponible sin desbordar.

### Contenido del drawer

Preservar toda la información y todas las acciones existentes del panel fijo.

#### 1. Encabezado

- Nombre de la tarjeta.
- Tipo de nodo o rol principal.
- Botón `×` para cerrar.
- Botón basurero cuando la tarjeta sea eliminable y el workflow editable.

#### 2. Nombre

- Mantener la edición actual del nombre.
- Respetar el estado de solo lectura.

#### 3. Entrada interpretada

`Entrada (qué recibe esta etapa)` no debe presentarse inicialmente como un campo vacío que el usuario tenga que completar.

Debe mostrar un texto derivado de lo que el sistema interpretó al construir el grafo, considerando:

- La descripción original del proceso.
- La etapa anterior.
- El resultado o rama que llega a esta tarjeta.
- La salida producida por la tarjeta anterior.

UX:

- Etiqueta: `Entrada interpretada`.
- Indicador secundario: `Generado desde el grafo` o `Interpretado`.
- Mostrar el texto como contenido legible, no como input por defecto.
- Acción secundaria `Corregir manualmente`.
- Al pulsarla, convertir el contenido en textarea editable.
- Acciones `Guardar corrección` y `Cancelar`.
- Una corrección manual se guarda en el mismo campo `entrada` ya existente.
- Si existe una corrección manual, no debe sobrescribirse silenciosamente al recargar.

No es necesario crear IA nueva en esta fase si la interpretación actual ya devuelve `entrada`. Si falta en workflows anteriores, generar un fallback determinístico y legible a partir de conexiones y nombres de nodos; no dejar un placeholder vacío como estado principal.

#### 4. Qué debe hacer

Aplicar la misma lógica que en `Entrada interpretada`:

- Mostrar inicialmente la acción interpretada desde el grafo o la descripción del proceso.
- Etiqueta: `Qué debe hacer`.
- Indicador `Interpretado`.
- Acción `Corregir manualmente`.
- Edición mediante textarea solo cuando el usuario la solicite.
- Guardar la corrección en el campo `proceso` actual.
- Nunca sobrescribir silenciosamente una corrección manual.

Si no existe valor interpretado en un workflow antiguo, usar un fallback basado en nombre, tipo, roles, conexiones y resultados de la tarjeta.

#### 5. Roles

Mantener:

- Chips de roles existentes.
- Selección de rol activo.
- Acción para agregar o quitar roles si actualmente está disponible.
- Estados editables y de solo lectura.

#### 6. Responsables

Mantener sin pérdida funcional:

- Responsable por rol.
- Selector de modo individual, paralelo o secuencial.
- Elegir responsable existente.
- Agregar responsable.
- Botón `+` o acción equivalente visible.
- Quitar responsable mediante basurero o acción existente.
- Invitación y mensajes/toasts actuales.
- Orden cuando el modo sea secuencial.

#### 7. Ramas de decisión

Mantener:

- Resultados configurados.
- Texto de ayuda actual.
- Edición cuando corresponde.
- Relación entre resultado y conexión saliente.
- Estados `aprobado` y `rechazado` con sus colores actuales.

#### 8. Configuración específica por tipo

Mantener las secciones condicionales existentes, por ejemplo:

- Cierre agregado de cotizaciones.
- Requisitos de homologación.
- Condiciones de entrada.
- Cualquier configuración que dependa de `nodoSel.tipo`.

No simplificar el drawer dejando fuera campos que hoy aparecen para tipos específicos.

#### 9. Comunicaciones

Mantener todo `NodeCommunicationsPanel` dentro del drawer:

- Lista de comunicaciones configuradas.
- Botón `+ Agregar`.
- Botón basurero para eliminar una regla.
- Tipo interno/externo.
- Plantilla.
- Rol dueño.
- Destinatario.
- Disparador.
- Demora inicial.
- Repetición.
- Máximo de intentos.
- Evento de término.
- Política de agotamiento.
- Resultado al terminar o agotar.
- `Editar correo para esta tarjeta`.
- `Actualizar plantillas`.
- Comportamiento de borrador automático al editar correos desde un ciclo activo.

El rediseño no debe revertir el cambio del commit `ea9a949`.

#### 10. Resumen de la tarjeta

Convertir el resumen actual en un disclosure colapsable:

- Título: `Resumen de la tarjeta`.
- Chevron a la derecha.
- Cerrado por defecto para reducir ruido visual.
- Rotación suave del chevron al abrir.
- Mantener exactamente el contenido narrado que ya se genera hoy.
- Debe ser un control accesible (`button` con `aria-expanded` o `<details>/<summary>`).

## Terminal inferior de chat

Mover el chat `Corregir por chat` a una terminal anclada en la parte inferior del canvas.

Estado compacto:

- Barra de título `Corregir por chat`.
- Último mensaje o indicación breve.
- Textarea/input para escribir.
- Botón `Enviar`.
- Botón con chevron para expandir.

Estado expandido:

- Aumentar suavemente la altura.
- Mostrar historial de conversación con `ChatBubbles` y `TypingBubble` existentes.
- Mantener el input y botón Enviar visibles al fondo.
- Botón para contraer.

Reglas:

- No perder el historial al expandir o contraer.
- Mantener el comportamiento actual de `interpretar-correccion`.
- Mantener mensajes de operaciones descartadas y errores.
- Mantener los botones y acciones que aparezcan dentro de mensajes o propuestas.
- La terminal puede reducir temporalmente el alto visible del grafo, pero no su ancho.
- Al expandir, no debe quedar detrás del drawer; ambas capas deben tener un orden visual definido.

## Botones y acciones que no se pueden perder

Durante el refactor, verificar explícitamente cada uno:

- Flecha para volver.
- `Ordenar automáticamente`.
- `Validar`.
- `Guardar`.
- `Activar`.
- `Crear borrador con estos cambios`.
- `+` para abrir la paleta.
- Opciones para agregar cada tipo de nodo.
- Basurero de tarjeta.
- Puntos/botones de entrada y salida para conexiones.
- Eliminación de conexiones.
- `×` para cerrar el drawer.
- Chips/botones de roles.
- `+ Agregar` responsable.
- Quitar responsable.
- Modos individual/paralelo/secuencial.
- `+ Agregar` comunicación.
- Basurero de comunicación.
- `Editar correo para esta tarjeta`.
- `Actualizar plantillas`.
- Guardar/cerrar/restaurar/vista previa del editor de correo.
- Enviar corrección por chat.
- Expandir/contraer terminal.
- Expandir/contraer resumen.
- Zoom `−`, `100%` y `+`.

Si un botón cambia de ubicación, debe mantener la misma función, permisos, disabled state, confirmaciones y feedback.

## Estados y permisos

### Workflow borrador y usuario administrador

- Edición completa.
- Agregar/eliminar nodos.
- Editar propiedades.
- Asignar responsables.
- Configurar comunicaciones.

### Workflow activo y usuario administrador

- Grafo de solo lectura.
- Edición de correo permitida mediante creación automática de borrador al guardar.
- Mantener la advertencia actual sobre este comportamiento.
- No aparentar que otras propiedades se pueden guardar directamente en la versión activa.

### Usuario no administrador

- Mostrar información en modo lectura.
- Campos realmente deshabilitados, no solo `onChange` ausente.
- Ocultar acciones destructivas o de edición según el comportamiento actual.
- Mantener avisos claros cuando una acción requiere administrador.

## Arquitectura frontend sugerida

Evitar que `page.tsx` crezca todavía más. Extraer componentes presentacionales sin mover lógica de negocio innecesariamente:

- `WorkflowCanvasViewport.tsx`: viewport, transformaciones de zoom/paneo y controles.
- `WorkflowNodePalette.tsx`: botón `+` y popover de tipos.
- `WorkflowNodeDrawer.tsx`: contenedor flotante, cierre y composición de secciones.
- `WorkflowCorrectionTerminal.tsx`: modo compacto/expandido y chat existente.
- `InterpretedField.tsx`: vista interpretada + corrección manual.
- `CollapsibleNodeSummary.tsx`: disclosure del resumen.

La lógica de carga, guardado, validación, activación y llamadas API puede permanecer inicialmente en `page.tsx` y pasarse por props. No reescribir servicios del backend para completar un refactor visual.

## Consideraciones técnicas para zoom/paneo

- Mantener un estado de viewport separado: `{ scale, translateX, translateY }`.
- Aplicar una única transformación CSS al mundo que contiene nodos y SVG.
- Convertir coordenadas del puntero a coordenadas del mundo al arrastrar tarjetas:
  - `worldX = (clientX - rect.left - translateX) / scale`
  - `worldY = (clientY - rect.top - translateY) / scale`
- El paneo comienza solo sobre el fondo del canvas.
- Usar pointer events para mouse y trackpad/touch cuando sea posible.
- Liberar pointer capture al terminar o cancelar el gesto.
- No persistir translate ni scale en el workflow; son preferencias temporales de vista.
- Evitar transiciones CSS durante el drag para que no haya lag.

## Animación

Usar animaciones discretas:

- Drawer: `transform` + `opacity`, 200–300 ms.
- Paleta: aparición breve y cambio de ancho/altura sin desplazar el canvas.
- Terminal: transición de altura, 200–300 ms.
- Chevron: rotación, alrededor de 180 ms.

Respetar `prefers-reduced-motion` desactivando o reduciendo las transiciones.

## Responsive

### Escritorio

- Drawer flotante de aproximadamente 360–420 px.
- Terminal inferior compacta.
- Grafo visible detrás de overlays.

### Tablet

- Drawer de hasta 90% del ancho disponible.
- Paleta alineada a la derecha.
- Acciones superiores pueden envolver en más de una línea sin desaparecer.

### Móvil

- Drawer casi a ancho completo.
- Terminal expandida puede ocupar buena parte de la pantalla, pero debe poder contraerse.
- Zoom y paleta no deben quedar detrás de la terminal.
- No generar scroll horizontal de página.

## Accesibilidad

- Todos los iconos de acción requieren `aria-label`.
- Los botones con solo `+`, `×`, basurero o chevron deben tener nombre accesible.
- Drawer con encabezado asociado y foco manejable.
- Al abrir el drawer desde una tarjeta, no es obligatorio secuestrar el foco, pero el contenido debe quedar en el orden natural de tabulación.
- Escape puede cerrar el drawer o la paleta si se implementa sin interferir con inputs.
- Chevrons con `aria-expanded`.
- Estados disabled reales en inputs y botones.
- Contraste compatible con los tokens actuales.

## Fuera de alcance

- Cambiar el modelo de workflow.
- Cambiar la interpretación conversacional del backend.
- Cambiar el motor de ejecución.
- Crear nuevos eventos de correo.
- Cambiar reglas de permisos.
- Reemplazar el sistema actual de nodos por una librería externa.
- Rediseñar el resto de Configuración.

## Estrategia de implementación

1. Extraer el panel actual a `WorkflowNodeDrawer` sin cambiar comportamiento.
2. Verificar que todas las acciones actuales sigan funcionando dentro del drawer.
3. Expandir el lienzo al ancho completo.
4. Mover la paleta a un popover desplegable.
5. Agregar zoom/paneo y adaptar el drag de nodos a coordenadas transformadas.
6. Mover el chat a `WorkflowCorrectionTerminal` conservando sus componentes y API.
7. Introducir `InterpretedField` para entrada y proceso.
8. Hacer colapsable el resumen.
9. Añadir responsive, animaciones y accesibilidad.
10. Ejecutar pruebas y comparar funcionalidad botón por botón con la versión anterior.

## Criterios de aceptación

- El grafo usa prácticamente todo el ancho de la pantalla.
- No existe una columna lateral fija consumiendo espacio permanentemente.
- La paleta de nodos está cerrada por defecto y se abre con `+`.
- Seleccionar una tarjeta abre un drawer suave sobre el costado derecho.
- Cerrar el drawer no altera el grafo.
- Toda la información y las acciones del panel actual siguen disponibles.
- Entrada y Qué debe hacer aparecen como interpretación legible, no como campos vacíos obligatorios.
- Ambos campos pueden corregirse manualmente y conservar su corrección.
- Resumen de la tarjeta está cerrado por defecto y se despliega con chevron.
- El chat funciona desde la terminal inferior y puede expandirse/contraerse.
- Zoom, reset y paneo funcionan sin romper el arrastre de tarjetas.
- Agregar, eliminar y conectar nodos sigue funcionando.
- Agregar/quitar responsables sigue funcionando.
- Agregar/eliminar/configurar comunicaciones sigue funcionando.
- Editar un correo desde un ciclo activo conserva el borrador automático introducido en `ea9a949`.
- Los usuarios sin permisos no ven controles falsamente editables.
- No hay regresiones en guardar, validar, activar ni crear versiones.

## Verificación mínima

### Pruebas manuales

1. Abrir un workflow borrador con varios tipos de nodo.
2. Abrir/cerrar la paleta y agregar cada tipo de nodo.
3. Seleccionar varias tarjetas y verificar que el drawer actualiza su contenido.
4. Editar nombre, entrada, proceso, roles y configuraciones específicas.
5. Agregar y quitar responsables.
6. Agregar, editar y eliminar comunicaciones.
7. Abrir el editor de correo y probar vista previa, guardar, restaurar y cerrar.
8. Arrastrar nodos con zoom en `50%`, `100%` y `150%`.
9. Panear el fondo y confirmar que no mueve una tarjeta accidentalmente.
10. Crear y eliminar conexiones.
11. Expandir/contraer la terminal y enviar una corrección.
12. Expandir/contraer el resumen.
13. Repetir en workflow activo como admin.
14. Repetir como usuario no admin.
15. Probar anchos desktop, tablet y móvil.

### Comandos

```bash
cd frontend
npx tsc --noEmit
npm run build
```

El repositorio tiene deuda de tipos preexistente documentada en `CLAUDE.md`. Reportar por separado cualquier error previo y confirmar que los archivos modificados no agregan errores nuevos.

## Resultado esperado para el PR

- Código frontend implementado.
- Sin cambios de base de datos.
- Sin cambios incompatibles en endpoints.
- Resumen de componentes extraídos.
- Evidencia de pruebas manuales de todas las acciones enumeradas.
- Capturas desktop y móvil con:
  - Grafo limpio.
  - Paleta abierta.
  - Drawer abierto.
  - Terminal expandida.

