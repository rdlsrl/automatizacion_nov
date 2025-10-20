# Contexto Monitor Pulling (corte diario)

Este documento resume las decisiones y el estado del monitor de calidad de datos para equipos de Pulling. Usarlo como base de contexto en nuevas charlas o tareas.

## Datos clave
- Corte diario: SIEMPRE hasta ayer (`max_date = ayer`). Ventana: últimos 14 días.
- Fuente: MariaDB `rdl_import`. Tablas: `errors_report_pae`, `rigs`, `wells`.
- Umbrales por defecto: `present_min=90`, `range_min=85`.

## Métricas
- Por equipo y por día (`e.date`):
  - `horas_monitoreadas = SUM(e.horas)` (suma por variable×pozo; puede superar 24).
  - `horas_con_datos = SUM(e.value_present)`.
  - `horas_sin_datos = SUM(e.value_null)`.
  - `calidad% = horas_con_datos / horas_monitoreadas × 100`.
- Alertas por variable requerida (`requerido='SI'`):
  - `NO REGISTRADA`: `horas_presentes=0`.
  - `INCOMPLETA`: `%presente < present_min`.
  - `FUERA DE RANGO`: `%en_rango < range_min`.

## Endpoints y UI
- `http://localhost/rdl/api_monitor_pulling.php`
  - Devuelve `present_min`, `range_min`, `max_date`, `equipos` con `actividad_diaria[fecha]`:
    - `pozos`, `variables`, `horas_monitoreadas`, `horas_con_datos`, `horas_sin_datos`, `calidad`, `issues_count`, `no_reg`, `incomp`, `fuera`.
- `http://localhost/rdl/api_detalle_pulling_dia.php`
  - Params: `rig_id`, `date`, `required_only`, `present_min`, `range_min`. Detalle por variable (incluye motivo de alerta y severidad).
- `http://localhost/rdl/monitor_pulling_grid.php`
  - Grid 14 días con colores por estado, encabezados con día+mes, tooltips con desglose de alertas, modal por día, filtro con autocomplete.

## Decisiones de diseño
- No “tiempo real”: siempre se muestra corte diario (hasta ayer).
- Aclaración de horas: sumarización por variable×pozo, interpretar con % de calidad y alertas.

## Pendientes sugeridos
- Mini-sparkline/badge de alertas por día por equipo.
- Exportación CSV completa desde el grid.
- Toggle opcional para incluir "hoy (parcial)" si se requiere.

---
Para una nueva charla, podés empezar con:

> Usar docs/CONTEXT_MONITOR_PULLING.md como base. Queremos [X cambio/feature].

```
objetivo: [describir brevemente]
alcance: [API/UI]
umbrales: present_min=90, range_min=85
nota: corte hasta ayer (no tiempo real)
```

## Compatibilidad y notas técnicas
- SQL sin CTE (no se usa WITH); se utilizan subconsultas para asegurar compatibilidad con MariaDB antiguas.
- Se usan divisiones con `NULLIF` para evitar divisiones por cero.

## Ubicación en el repositorio
- APIs y UI versionadas en: `scripts/web/rdl/`:
  - `api_monitor_pulling.php`
  - `api_detalle_pulling_dia.php`
  - `monitor_pulling_grid.php`
  - `reporte_calidad_pulling.php`
- Este documento: `scripts/docs/CONTEXT_MONITOR_PULLING.md`.
# Contexto Monitor Pulling (corte diario)

Este documento resume las decisiones y el estado del monitor de calidad de datos para equipos de Pulling. Usarlo como base de contexto en nuevas charlas o tareas.

## Datos clave
- Corte diario: SIEMPRE hasta ayer (`max_date = ayer`). Ventana: últimos 14 días.
- Fuente: MariaDB `rdl_import`. Tablas: `errors_report_pae`, `rigs`, `wells`.
- Umbrales por defecto: `present_min=90`, `range_min=85`.

## Métricas
- Por equipo y por día (`e.date`):
  - `horas_monitoreadas = SUM(e.horas)` (suma por variable×pozo; puede superar 24).
  - `horas_con_datos = SUM(e.value_present)`.
  - `horas_sin_datos = SUM(e.value_null)`.
  - `calidad% = horas_con_datos / horas_monitoreadas × 100`.
- Alertas por variable requerida (`requerido='SI'`):
  - `NO REGISTRADA`: `horas_presentes=0`.
  - `INCOMPLETA`: `%presente < present_min`.
  - `FUERA DE RANGO`: `%en_rango < range_min`.

## Endpoints y UI
- `http://localhost/rdl/api_monitor_pulling.php`
  - Devuelve `present_min`, `range_min`, `max_date`, `equipos` con `actividad_diaria[fecha]`:
    - `pozos`, `variables`, `horas_monitoreadas`, `horas_con_datos`, `horas_sin_datos`, `calidad`, `issues_count`, `no_reg`, `incomp`, `fuera`.
- `http://localhost/rdl/api_detalle_pulling_dia.php`
  - Params: `rig_id`, `date`, `required_only`, `present_min`, `range_min`. Detalle por variable (incluye motivo de alerta y severidad).
- `http://localhost/rdl/monitor_pulling_grid.php`
  - Grid 14 días con colores por estado, encabezados con día+mes, tooltips con desglose de alertas, modal por día, filtro con autocomplete.

## Decisiones de diseño
- No “tiempo real”: siempre se muestra corte diario (hasta ayer).
- Aclaración de horas: sumarización por variable×pozo, interpretar con % de calidad y alertas.

## Pendientes sugeridos
- Mini-sparkline/badge de alertas por día por equipo.
- Exportación CSV completa desde el grid.
- Toggle opcional para incluir "hoy (parcial)" si se requiere.

---
Para una nueva charla, podés empezar con:

> Usar docs/CONTEXT_MONITOR_PULLING.md como base. Queremos [X cambio/feature].
