# Resumen de sesión (20-10-2025)

Este documento resume todo lo trabajado en la sesión: implementación/ajustes del monitor de pulling (APIs + UI), documentación, y mejoras robustas de sincronización entre bases MariaDB.

## Objetivos principales
- Monitor de pulling con corte “hasta ayer”, agregaciones diarias y motivos de issues.
- Versionar APIs/UI en el repo y documentar decisiones.
- Mejorar la sincronización de datos entre `rdl_import` (origen) y `autom_nov` (destino) con un patrón robusto en MySQL/MariaDB.

## Cambios clave

### 1) Copia de APIs y frontend al repo
- Se creó `scripts/web/rdl/` con copias de:
  - `api_monitor_pulling.php`
  - `api_detalle_pulling_dia.php`
  - `monitor_pulling_grid.php`
  - `reporte_calidad_pulling.php`
- Ajustes menores para:
  - Salidas JSON limpias (sin header leak).
  - Títulos/ayudas (tooltips) y leyendas aclarando umbrales y definición de horas.

### 2) Documento de contexto
- Archivo: `scripts/docs/CONTEXT_MONITOR_PULLING.md`
  - Describe: diseño, endpoints, métricas, “hasta ayer”, umbrales y decisiones de UI.

### 3) Sincronización de datos (MySQL/MariaDB)
- Problema: versiones previas usaban `SELECT *`, `NOT IN`, y carecían de quoting robusto; además un DELETE daba `No database selected (1046)`.
- Solución implementada (patrón robusto):
  - Identificadores entre backticks para DB/tabla/columna.
  - Listas de columnas explícitas (intersección origen-destino, orden destino).
  - Upsert vía `INSERT … SELECT … ON DUPLICATE KEY UPDATE` con `VALUES(col)`.
  - DELETE de huérfanos con `DELETE d FROM dest d LEFT JOIN src s ON (PK…) WHERE s.PK IS NULL`.
  - `USE <dest_db>` antes del DELETE para evitar error 1046.
  - Fallback sin PK: reemplazo completo (DELETE + INSERT … SELECT).

Scripts afectados:
- `scripts/sync_datos_simple.py` (actualizado previamente en la sesión; probado en ejecución real: PASS)
- `scripts/sync_datos_rdl.py` (ahora alineado al mismo patrón; sintaxis PASS; commit a master)

## Snippets operativos

### Actualización de DB previa a correr Python (opcional en cron)
```sql
-- Mantenimiento liviano (opcional):
ANALYZE TABLE autom_nov.files_import_autom;
ANALYZE TABLE autom_nov.events_autom;
ANALYZE TABLE autom_nov.wells_autom;
-- OPTIMIZE si hubo borrados grandes (usar con criterio):
-- OPTIMIZE TABLE autom_nov.files_import_autom, autom_nov.events_autom, autom_nov.wells_autom;
```

### Llamada de sincronización en el pipeline diario
- En la fase 0 del runner `welldata_diario_completo.sh` se ejecuta la sincronización antes del resto de pasos:
```bash
python3 scripts/sync_datos_simple.py
```
- También podés ejecutar manualmente la sincronización RDL:
```bash
python3 scripts/sync_datos_rdl.py
```

## Verificación y estado
- `sync_datos_simple.py`:
  - Ejecutado en entorno real tras la mejora: INSERT/UPDATE OK; DELETE sin error 1046 gracias a `USE`.
- `sync_datos_rdl.py`:
  - Compilación Python: PASS (`python3 -m py_compile`).
  - Commit en master: PASS (ver abajo).
- Monitor Pulling (APIs/UI):
  - Copias versionadas en `scripts/web/rdl/`.
  - JSON limpio y aclaraciones de UI.

## Commits relevantes
- `sync_datos_rdl.py`: a4bfdf1 — “align with robust sync pattern (explicit cols, ON DUPLICATE KEY UPDATE, DELETE via LEFT JOIN, proper quoting + USE fix)”
- Copia de APIs/UI y doc de contexto: commits previos en la misma rama (master).

## Cómo correr
```bash
# Obtener últimos cambios
git pull --rebase

# Validar sintaxis de los sync (opcional)
python3 -m py_compile scripts/sync_datos_simple.py
python3 -m py_compile scripts/sync_datos_rdl.py

# Ejecutar sincronización RDL (manual)
python3 scripts/sync_datos_rdl.py

# Ejecutar pipeline completo (incluye sync en fase 0)
bash scripts/welldata_diario_completo.sh
```

## Próximos pasos sugeridos
- Factorizar la lógica de sync en un módulo utilitario común a ambos scripts.
- Agregar modo "dry-run" (imprime SQLs) y logging con contadores por tabla.
- Parametrizar índice único alternativo si alguna tabla no usa PK para el upsert.

## Notas
- El patrón asume que las tablas tienen PK o, alternativamente, índice único adecuado para `ON DUPLICATE KEY UPDATE`.
- Si una tabla carece de PK/índice único, se realiza reemplazo total como fallback.
