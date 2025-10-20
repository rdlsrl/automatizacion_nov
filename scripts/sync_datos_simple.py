#!/usr/bin/env python3
"""
Sincronización simple de tablas entre rdl_import y autom_nov
Version simplificada para debugging
"""
import os
import pymysql
from dotenv import load_dotenv
from datetime import datetime

# Cargar variables de entorno
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '..', 'config.env'))

# Configuración de bases de datos
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"), 
    "password": os.getenv("DB_PASSWORD"),
    "port": int(os.getenv("DB_PORT", 3306))
}

def log_message(message):
    """Log con timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

def sync_table_complete(cursor, source_db, source_table, dest_db, dest_table):
    """Sincronización completa: INSERT nuevos + UPDATE modificados + DELETE eliminados
    - Escapa identificadores con backticks (incluida posible columna `NULL`).
    - Evita SELECT *; usa lista explícita de columnas comunes (orden de destino).
    - Usa LEFT JOIN en DELETE para evitar problemas de NOT IN con NULLs.
    Requiere PK/UNIQUE coherente (por defecto `id`).
    """
    log_message(f"Sincronizando {source_db}.{source_table} → {dest_db}.{dest_table}")

    # Helpers de quoting de identificadores
    def q_ident(name: str) -> str:
        return f"`{str(name).replace('`', '``')}`"

    def q_table(db: str, table: str) -> str:
        return f"{q_ident(db)}.{q_ident(table)}"

    q_src = q_table(source_db, source_table)
    q_dst = q_table(dest_db, dest_table)

    try:
        # Contadores iniciales
        cursor.execute(f"SELECT COUNT(*) AS count FROM {q_dst}")
        dest_count_before = cursor.fetchone()['count']

        # Columnas origen/destino
        cursor.execute(f"SHOW COLUMNS FROM {q_src}")
        src_cols = [r['Field'] for r in cursor.fetchall()]

        cursor.execute(f"SHOW COLUMNS FROM {q_dst}")
        dst_cols = [r['Field'] for r in cursor.fetchall()]

        # Intersección (orden destino)
        common_cols = [c for c in dst_cols if c in src_cols]
        if not common_cols:
            raise RuntimeError(f"No hay columnas comunes entre {q_src} y {q_dst}")

        common_cols_q = [q_ident(c) for c in common_cols]
        # Columnas a actualizar (evitar PK `id` por defecto)
        update_cols = [c for c in common_cols if c.lower() != 'id']
        update_cols_q = [q_ident(c) for c in update_cols]

        # SELECT explícito
        select_exprs = [f"s.{q_ident(c)}" for c in common_cols]

        # ON DUPLICATE KEY UPDATE
        if update_cols_q:
            update_clause = ", ".join([f"{col}=VALUES({col})" for col in update_cols_q])
        else:
            # Fallback: asignación no-op
            only_id = q_ident('id') if 'id' in common_cols else common_cols_q[0]
            update_clause = f"{only_id}={only_id}"

        insert_sql = f"""
            INSERT INTO {q_dst} ({", ".join(common_cols_q)})
            SELECT {", ".join(select_exprs)}
            FROM {q_src} AS s
            ON DUPLICATE KEY UPDATE
                {update_clause}
        """

        cursor.execute(insert_sql)
        log_message(f"  ✅ INSERT/UPDATE afectados: {cursor.rowcount}")

        # Asegurar esquema destino seleccionado para DELETE (evita 1046: No database selected)
        cursor.execute(f"USE {q_ident(dest_db)}")

        # DELETE faltantes usando LEFT JOIN por PK `id`
        if 'id' not in common_cols:
            raise RuntimeError("No se encontró columna clave `id`; ajusta la PK para el DELETE")

        delete_sql = f"""
            DELETE d
            FROM {q_dst} AS d
            LEFT JOIN {q_src} AS s
              ON s.{q_ident('id')} = d.{q_ident('id')}
            WHERE s.{q_ident('id')} IS NULL
        """
        cursor.execute(delete_sql)
        log_message(f"  ✅ DELETE eliminados: {cursor.rowcount}")

        # Contador final
        cursor.execute(f"SELECT COUNT(*) AS count FROM {q_dst}")
        dest_count_after = cursor.fetchone()['count']
        log_message(f"  ✅ Resultado final: {dest_count_after} registros (antes: {dest_count_before})")

    except Exception as e:
        log_message(f"  ❌ ERROR: {e}")
        raise

def main():
    """Función principal de sincronización"""
    log_message("========================================")
    log_message("SINCRONIZACIÓN SIMPLE DE DATOS")
    log_message("========================================")
    
    # Mapeo de tablas
    tables_map = {
        "files_import": "files_import_autom",
        "events": "events_autom",
        "wells": "wells_autom"
    }
    
    try:
        conn = pymysql.connect(**db_config, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
        cursor = conn.cursor()
        
        log_message(f"✅ Conectado a: {db_config['host']}")
        
        # Deshabilitar foreign key checks temporalmente
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        log_message("🔓 Foreign key checks deshabilitados")
        
        # Sincronizar cada tabla
        for source_table, dest_table in tables_map.items():
            try:
                sync_table_complete(cursor, 'rdl_import', source_table, 'autom_nov', dest_table)
            except Exception as e:
                log_message(f"❌ Falló {source_table}: {e}")
                continue
        
        # Rehabilitar foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        log_message("🔒 Foreign key checks rehabilitados")
        
        conn.commit()
        log_message("✅ Todas las sincronizaciones completadas")
        
    except Exception as e:
        log_message(f"❌ ERROR CRÍTICO: {e}")
        return 1
    finally:
        if 'conn' in locals():
            conn.close()
    
    return 0

if __name__ == "__main__":
    exit(main())