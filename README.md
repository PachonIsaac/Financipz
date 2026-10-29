# Financipz

App personal para llevar las finanzas: registro de ingresos y gastos, cuentas, flujo de caja, patrimonio y cripto. Uso de un solo usuario, pensada como PWA.

## Qué hace

- Registra movimientos a mano y recibe los avisos del banco leyendo el correo en solo lectura. Todo lo automático queda **pendiente de revisión** y no cuenta hasta que se confirma; si un aviso es el mismo movimiento que ya registraste, se unen.
- Calcula saldos por cuenta y moneda, el balance (disponible menos la deuda de tarjetas), el resumen del mes y el patrimonio en pesos con la TRM del día. Cada cuenta puede dejarse fuera del balance.
- Lee en solo lectura el portafolio de Binance y guarda una instantánea por día.

## Stack

- **Backend:** FastAPI, SQLAlchemy 2, Alembic y PostgreSQL.
- **Frontend:** React, TypeScript y Tailwind como PWA, solo en modo oscuro.

## Estructura

| Carpeta | Contenido |
|---|---|
| [`backend/`](backend/) | API, parsers y esquema de base de datos |
| [`frontend/`](frontend/) | PWA |

## Estado

En uso. Ver [`backend/README.md`](backend/README.md) y [`frontend/README.md`](frontend/README.md) para correr cada parte y las pruebas.
