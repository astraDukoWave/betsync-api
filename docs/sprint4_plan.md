# BetSync Sprint 4 — Pivote Fiscal y Contable (MVP Rediseñado)

**Fecha:** 17 de marzo de 2026 | **Status:** En Planificación

---

## 🏗️ Resumen del Pivot
El objetivo del Sprint 4 ha sido redefinido para transformar BetSync de un "Performance Tracker" a un "Fiscal Ledger" (Libro Mayor Fiscal). El foco principal es resolver el dolor de la gestión financiera, la conciliación multi-casa y el cumplimiento tributario para apostadores serios y tipsters en ES/LATAM.

---

## 🎯 Nuevos Requerimientos Funcionales (RF)

### Bloque A: Backend (Capa Contable)
- **RF-Fiscal-01 (Transacciones):** Registro de depósitos, retiros, bonos y comisiones vinculados a un Sportsbook.
- **RF-Fiscal-02 (Multi-Divisa):** Registro de Tipo de Cambio (TC) histórico para conversiones a moneda base (MXN/EUR/ARS) según requerimientos de SAT/AEAT.
- **RF-Fiscal-03 (Bulk Import):** Importación masiva de picks y transacciones vía CSV para eliminar la carga manual de datos antiguos.
- **RF-Fiscal-04 (Motor Fiscal):** Cálculo de base imponible: Ganancias Brutas - Pérdidas Brutas = Utilidad Neta Gravable.

### Bloque B: Frontend (Reporting y Validación)
- **RF-UI-01 (Página /fiscal):** Vista de resumen tributario anual con exportación a formato contable.
- **RF-UI-02 (Página /cashflow):** Seguimiento de flujo de caja real (dinero en banco vs dinero en casas).
- **RF-UI-03 (Dashboard Pro):** KPI cards de Saldo Consolidado y Ganancia Neta Fiscal del año en curso.

---

## 🛠️ Backlog de Tareas

### 1. Modelos y Migraciones (Prioridad Alta)
- [ ] Crear modelo `Transaction` (`deposit`, `withdrawal`, `bonus`, `commission`, `void_refund`).
- [ ] Agregar campos `tax_year` y `exchange_rate` a transacciones.
- [ ] Generar migración Alembic.

### 2. Endpoints de API (Prioridad Alta)
- [ ] `POST /transactions/`: CRUD de movimientos de caja.
- [ ] `GET /fiscal/summary`: Agregaciones por año y jurisdicción.
- [ ] `POST /picks/bulk`: Carga masiva de picks.

### 3. Frontend (Prioridad Media)
- [ ] Nueva ruta `/fiscal` con widget de resumen.
- [ ] Nueva ruta `/cashflow` con tabla de movimientos bancarios.
- [ ] Botón de exportación a Excel (formato auditoría).

### 4. Operacional (Prioridad Urgente)
- [ ] Configurar `.env.local` para producción.
- [ ] Seed de tabla `config` (Model, Min Grade, Edge, Unit Size).
- [ ] Deploy de backend en Railway/Render.

---

## 📦 Entregables Sprint 4
1. **API de Transacciones:** Motor completo de depósitos y retiros.
2. **Reporte Fiscal:** PDF/Excel listo para el contador.
3. **Importador CSV:** Herramienta para migrar desde Excel actual del cliente.

---

*“Cada línea de código debe responder: ¿esto le quita horas a un tipster o lo protege de Hacienda?”*
