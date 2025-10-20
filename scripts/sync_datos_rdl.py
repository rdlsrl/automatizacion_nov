#!/usr/bin/env python3
"""
Sincronización de tablas entre rdl_import y autom_nov
Replica el comportamiento de Navicat Data Sync para mantener tablas idénticas
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

# Mapeo de tablas origen -> destino
SYNC_TABLES = {
    "files_import": "files_import_autom",
    "events": "events_autom", 
    "wells": "wells_autom"
}

def log_message(message):
    """Log con timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

def q_ident(name: str) -> str:
    """Escapa identificadores con backticks (incluye caso `NULL`)."""
    return f"`{str(name).replace('`', '``')}`"

def q_table(db: str, table: str) -> str:
    return f"{q_ident(db)}.{q_ident(table)}"

def get_table_structure(cursor, database, table):
    """Obtiene la estructura de una tabla (nombres crudos y escapados)."""
    cursor.execute(f"SHOW COLUMNS FROM {q_table(database, table)}")
    rows = cursor.fetchall()
    cols = [r['Field'] for r in rows]
    cols_q = [q_ident(c) for c in cols]
    return cols, cols_q

def get_primary_key(cursor, database, table):
    """Obtiene las columnas de clave primaria (lista cruda)."""
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND CONSTRAINT_NAME = 'PRIMARY'
        ORDER BY ORDINAL_POSITION
        """,
        (database, table),
    )
    return [row['COLUMN_NAME'] for row in cursor.fetchall()]

def sync_table_navicat_style(cursor, source_db, source_table, dest_db, dest_table):
    """Sincroniza una tabla con ON DUPLICATE KEY UPDATE y DELETE LEFT JOIN.
    Mantiene: INSERT nuevos, UPDATE existentes, DELETE faltantes.
    - Backticks en todos los identificadores
    - Columnas explícitas (sin SELECT *)
    - DELETE con LEFT JOIN por PK
    """
    log_message(f"Sincronizando {source_db}.{source_table} → {dest_db}.{dest_table}")

    q_src = q_table(source_db, source_table)
    q_dst = q_table(dest_db, dest_table)

    # Estructuras
    src_cols, src_cols_q = get_table_structure(cursor, source_db, source_table)
    dst_cols, dst_cols_q = get_table_structure(cursor, dest_db, dest_table)

    # PK
    primary_keys = get_primary_key(cursor, source_db, source_table)
    if not primary_keys:
        # Sin PK: usar REPLACE INTO como fallback seguro
        log_message(f"  ⚠️ {source_table} sin PK; aplico REPLACE INTO")
        cursor.execute(f"DELETE FROM {q_dst}")
        cursor.execute(f"INSERT INTO {q_dst} SELECT * FROM {q_src}")
        log_message(f"  ✅ Reemplazados {cursor.rowcount} registros")
        return

    # Columnas comunes (orden destino)
    common_cols = [c for c in dst_cols if c in src_cols]
    if not common_cols:
        raise RuntimeError(f"No hay columnas comunes entre {q_src} y {q_dst}")

    common_cols_q = [q_ident(c) for c in common_cols]
    select_exprs = [f"s.{q_ident(c)}" for c in common_cols]

    # Columnas a actualizar (todas menos las PK)
    pk_set = set(c.lower() for c in primary_keys)
    update_cols_q = [q_ident(c) for c in common_cols if c.lower() not in pk_set]
    if update_cols_q:
        update_clause = ", ".join([f"{col}=VALUES({col})" for col in update_cols_q])
    else:
        # No-op si no hay columnas actualizables
        update_clause = f"{common_cols_q[0]}={common_cols_q[0]}"

    # INSERT/UPDATE
    insert_sql = f"""
        INSERT INTO {q_dst} ({", ".join(common_cols_q)})
        SELECT {", ".join(select_exprs)}
        FROM {q_src} AS s
        ON DUPLICATE KEY UPDATE
            {update_clause}
    """
    cursor.execute(insert_sql)

    # DELETE con LEFT JOIN por PK (usar esquema destino para evitar 1046)
    cursor.execute(f"USE {q_ident(dest_db)}")
    on_parts = [f"s.{q_ident(pk)} = d.{q_ident(pk)}" for pk in primary_keys]
    on_clause = " AND ".join(on_parts)
    where_parts = [f"s.{q_ident(pk)} IS NULL" for pk in primary_keys]
    # Con LEFT JOIN bastaría con chequear NULL de una PK, pero mantenemos forma general
    where_clause = " AND ".join(where_parts)
    delete_sql = f"""
        DELETE d
        FROM {q_dst} AS d
        LEFT JOIN {q_src} AS s
          ON {on_clause}
        WHERE {where_clause}
    """
    cursor.execute(delete_sql)

    log_message(f"  ✅ Sincronización completa: {cursor.rowcount} DELETE (más INSERT/UPDATE previos)")

def main():
    """Función principal de sincronización"""
    log_message("========================================")
    log_message("INICIANDO SINCRONIZACIÓN DE DATOS")
    log_message("Estilo: Navicat Data Sync (completa)")
    log_message("========================================")
    
    try:
        # Conectar a la base de datos
        conn = pymysql.connect(**db_config, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
        cursor = conn.cursor()
        
        # Verificar conectividad a ambas bases
        cursor.execute("SELECT DATABASE()")
        log_message(f"Conectado a servidor: {db_config['host']}")
        
        # Verificar que existan las bases de datos
        cursor.execute("SHOW DATABASES")
        databases = [row['Database'] for row in cursor.fetchall()]
        
        if 'rdl_import' not in databases:
            raise Exception("Base de datos 'rdl_import' no encontrada")
        if 'autom_nov' not in databases:
            raise Exception("Base de datos 'autom_nov' no encontrada")
        
        log_message("✅ Bases de datos verificadas: rdl_import, autom_nov")
        
        # Sincronizar cada tabla
        for source_table, dest_table in SYNC_TABLES.items():
            try:
                sync_table_navicat_style(cursor, 'rdl_import', source_table, 'autom_nov', dest_table)
            except Exception as e:
                log_message(f"  ❌ ERROR sincronizando {source_table}: {e}")
                # Continuar con las demás tablas
                continue
        
        # Confirmar cambios
        conn.commit()
        log_message("✅ Sincronización completada y confirmada")
        
    except Exception as e:
        log_message(f"❌ ERROR CRÍTICO: {e}")
        if 'conn' in locals():
            conn.rollback()
        return 1
    finally:
        if 'conn' in locals():
            conn.close()
    
    log_message("========================================")
    log_message("SINCRONIZACIÓN FINALIZADA")
    log_message("========================================")
    return 0

if __name__ == "__main__":
    exit(main())