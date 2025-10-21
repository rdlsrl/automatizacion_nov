# Sistema de Gestión Funeraria — Esquema Visual

Este documento incluye diagramas (Mermaid) del sistema: arquitectura, modelo de datos y flujos clave. Podés verlos directamente en VS Code con extensiones Mermaid o en GitHub (si soporta rendering) o exportar desde el HTML adjunto.

## Arquitectura (alto nivel)

```mermaid
flowchart LR
    subgraph Usuarios
        D[Dueño]
        A[Administración]
        S[Secretarías]
        C[Choferes]
    end

    D & A & S & C --> UI[App Web (Panel + Formularios)]
    UI --> AUTH[Autenticación + Roles (RBAC)]
    UI --> API[Backend API (Servicios de negocio)]
    API --> DB[(MariaDB/MySQL)]
    API --> STORAGE[(Almacenamiento de archivos S3/MinIO)]
    API --> AUD[Auditoría (eventos y cambios)]
    API <-->|Jobs programados| WORK[Scheduler/Worker]
    API --> WA[WhatsApp Cloud API/Proveedor]
    API --> CONTAB[Integración Contable/ERP/Banco]
    API --> INMEM[Inmemory.cl (API/CSV)]
    WORK --> WA
    WORK --> STORAGE
    DB --> BACKUP[Backups automáticos en la nube]
    STORAGE --> BACKUP
```

## Modelo de datos (simplificado)

```mermaid
erDiagram
    CONTRATO ||--o{ SERVICIO : incluye
    CONTRATO }o--|| CLIENTE : contratante
    CONTRATO }o--|| FALLECIDO : caso
    CONTRATO }o--o{ DESCUENTO : aplica
    CONTRATO }o--o{ PAGO : abonos
    CONTRATO }o--o{ DOCUMENTO : adjunta

    SERVICIO }o--o{ PRODUCTO : usa
    PRODUCTO }o--o{ INVENTARIO : stock
    MOVIMIENTO_INVENTARIO }o--|| INVENTARIO : afecta
    MOVIMIENTO_INVENTARIO }o--|| SERVICIO : por_servicio

    EMPLEADO ||--o{ TURNO : tiene
    EMPLEADO ||--o{ META : define
    EMPLEADO ||--o{ ADELANTO : registra
    EMPLEADO ||--o{ LIQUIDACION : genera

    LIQUIDACION }o--o{ ITEM_LIQ : rubros
    ITEM_LIQ }o--|| EMPLEADO : para

    CONVENIO ||--o{ CONTRATO : aplica
    DIRECTORIO }o--o{ SERVICIO : opera_en

    NOTIFICACION }o--|| CONTRATO : sobre
    NOTIFICACION }o--|| EMPLEADO : a_quien

    AUDITORIA }o--|| EMPLEADO : actor
    AUDITORIA }o--|| CONTRATO : sobre
```

## Flujo: Contrato → Liquidación (bonos/comisiones)

```mermaid
sequenceDiagram
    participant Sec as Secretaría
    participant Web as App Web
    participant API as Backend
    participant DB as DB
    participant Work as Worker
    participant Adm as Admin

    Sec->>Web: Crea Cotización/Contrato (fecha/hora, descuentos)
    Web->>API: Guardar CONTRATO + SERVICIOS + PAGOS
    API->>DB: Persistir y AUDITORÍA

    Note over API,Work: Reglas de bonos por fecha/hora, feriados, rol
    Work->>DB: Acumula métricas (ventas/servicios/bonos)
    Adm->>Web: Calcular liquidaciones del mes
    Web->>API: Generar LIQUIDACION + ITEM_LIQ
    API-->>Adm: PDFs y archivo para pago masivo
```

## Flujo: Notificaciones (familia y chofer)

```mermaid
sequenceDiagram
    participant Sec as Secretaría
    participant API as Backend
    participant Work as Worker
    participant WA as WhatsApp API

    Sec->>API: Autoriza difusión / agenda servicio
    API->>Work: Programa mensajes (4h, 5d, 8d, 30d, 1a)
    Work->>WA: Tips (+4h), Tarjeta (+5d), Encuesta (+8d), Oficio (+30d), Aniversario (+1a)
    Work->>WA: Al chofer de turno con indicaciones
```

---

## Exportar a PDF/JPG

- Opción rápida: abrir `funeral_system_overview.html` en un navegador y:
  - PDF: Imprimir → Guardar como PDF.
  - JPG/PNG: Captura con la herramienta del sistema o extensión.
- VS Code: usar extensión “Markdown PDF” para exportar este `.md`.

## Ideas extra para agilizar gestión

- OCR en facturas (extrae datos y sugiere cuenta contable).
- Conciliación bancaria semi-automática (matching por monto/fecha/nº ref).
- Alertas de anomalías (costos fuera de rango, contratos sin adjuntos).
- Firma digital simple en contratos/autorizaciones.
- PWA para choferes (checklist y evidencia de servicio).
- Presupuestos por rubro con alertas de desvío.
