# Yativo — Virtual Card API (referencia)

Copia versionada de la documentación del proveedor (Notion, 2026-08-30). Se guarda acá porque la
página original se renderiza con JavaScript y no es consultable por herramientas. **Si Yativo
actualiza su doc, actualizar este archivo y anotar la fecha.**

Análisis y consecuencias de diseño: sección 4.5 de `PRD_EMPLEADO_DIGITAL.md`.

## Base URL

- Producción: `https://api.yativo.com/api/v1`
- Test: `https://smtp.yativo.com/api/v1`

## Headers

Todo request que no sea GET exige `Idempotency-Key` (identificador único de request) y
`Content-Type: application/json`.

**La doc no describe el mecanismo de autenticación** (ni API key, ni bearer, ni firma). Es una
brecha real, no una omisión de esta copia — hay que preguntárselo a Yativo.

## Endpoints

### 1. Activar cliente — `POST /customer/virtual/cards/activate`
KYC previo obligatorio antes de poder crear tarjetas.

Campos: `customer_id`, `customer_address` (`city`, `state`, `zipcode`, `street`, `country`,
`number`), `customer_idFront` (URL a la foto del documento), `customer_idNumber`, `date_of_birth`
(DD-MM-YYYY), `user_photo` (URL).

### 2. Crear tarjeta — `POST /customer/virtual/cards/create`
Body: `amount` (entero, **en centavos**, múltiplos de 100), `customer_id`.
Cobra un **fee mínimo de USD 3 por tarjeta creada**.

Respuesta: `card_id`, `customer_email`, `customer_id`, `card_brand` (visa), `card_type` (virtual).

### 3. Recargar — `POST /customer/virtual/cards/topup`
Body: `customer_id`, `cardId`, `amount` (centavos, múltiplos de 100).
Debita del saldo de la billetera del cliente.

### 4. Listar tarjetas — `GET /customer/virtual/cards/list?customer_id=...`

### 5. Detalle de tarjeta — `GET /customer/virtual/cards/get/{cardId}`
Devuelve `balance`, `cardNumber` (**PAN completo**), `last4`, `cardName`, `cvv2`, `expiry`,
`valid`, `billingAddress` (dirección de EE.UU.), `airlinePaymentEnabled`.

### 6. Transacciones — `GET /customer/virtual/cards/transactions/{cardId}`
Cada transacción: `id`, `createdAt`, `updatedAt`, `amount` (dólares), `centAmount`,
`cardBalanceAfter`, `type` (credit/debit), `method` (topup/purchase/…), `narrative`, `status`,
`currency` (**usd**), `reference`, `transactionType`, `authorizationTransactionId`,
`settlementTransactionId`.

### 7. Congelar / descongelar — `PUT /customer/virtual/cards/update/{cardId}`
Body: `action` = `"freeze"` | `"unfreeze"`.

## Notas del proveedor

- Montos siempre en centavos (500 = USD 5,00).
- Fee mínimo de USD 3 al crear tarjeta.
- `Idempotency-Key` obligatorio en todo no-GET.
- KYC obligatorio antes de crear tarjetas.
- Los top-up debitan de la billetera del cliente.

## Lo que la doc NO cubre (verificado por ausencia, hay que preguntar)

1. **Autenticación.** No se documenta ninguna credencial.
2. **Webhooks.** No existen en la doc. La conciliación tendría que ser por polling.
3. **Cerrar tarjeta y recuperar saldo.** Sólo hay freeze/unfreeze; no hay endpoint de cierre ni de
   retiro del saldo remanente hacia la billetera.
4. **Controles de gasto por comercio.** No hay merchant lock, MCC ni límite por transacción. El
   único control efectivo es el saldo cargado.
5. **Monedas distintas de USD.** Todo lo documentado es USD.
6. **Rate limits y política de reintentos.**
