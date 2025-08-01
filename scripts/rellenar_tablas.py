import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Text, text, inspect
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.exc import SQLAlchemyError, NoSuchTableError
from datetime import datetime
from typing import Optional # Para las anotaciones de tipo
import pandas as pd # Para leer la tabla de variables_XXX
from collections import Counter # Para el orden de aparición de mnemónicos

# --- 0. Carga de Configuración de Base de Datos ---
# load_dotenv() # Descomenta si usas un archivo .env en el mismo directorio

DB_USER = os.getenv("DB_USER", "root") # <<-- REEMPLAZA
DB_PASSWORD = os.getenv("DB_PASSWORD", "Partediario20") # <<-- REEMPLAZA
DB_HOST = os.getenv("DB_HOST", "192.168.1.144") # <<-- REEMPLAZA si es necesario
DB_NAME = os.getenv("DB_NAME", "rdl_import") # <<-- REEMPLAZA
DB_PORT = os.getenv("DB_PORT", "3306") # <<-- REEMPLAZA si es necesario

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL, echo=False) 
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# --- 1. Modelos SQLAlchemy para las TABLAS ---

# Modelos de tablas fuente/lookup
class Rigs(Base):
    __tablename__ = "rigs" 
    id = Column(Integer, primary_key=True)
    rig_type = Column(String) 

class VariablesPaeAutom(Base):
    __tablename__ = "variables_pae_autom" 
    id = Column(Integer, primary_key=True)
    name_pae = Column(String, unique=True, nullable=False)
    descripcion_pae = Column(Text)

# Modelos de tablas DESTINO (asegúrate que coincidan con tu BD)
class ConfigVariablesPAE(Base):
    __tablename__ = "Config_Variables_PAE" 
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    rig_id = Column(Integer, ForeignKey('rigs.id'), nullable=False, index=True)
    variable_pae_id = Column(Integer, ForeignKey('variables_pae_autom.id'), nullable=False, index=True)
    
    descripcion_pae_objetivo = Column(Text, nullable=True)
    valor_min_pae_esperado = Column(Float, nullable=True) 
    valor_max_pae_esperado = Column(Float, nullable=True) 
    valor_nulo_adicional_las = Column(Float, nullable=True) 
    grupo_pae = Column(String(100), nullable=True) 
    alarma_minima = Column(Float, nullable=True) 
    alarma_maxima = Column(Float, nullable=True) 
    unidad_id = Column(Integer, nullable=True) 
    mostrar_en_dashboard = Column(Boolean, nullable=True) 
    cantidad_decimales = Column(Integer, nullable=True) 
    
    # Tus nuevos campos (usa los nombres exactos que definiste en tu tabla)
    date_start_var = Column(DateTime, nullable=True) 
    date_start_setting_var = Column(DateTime, nullable=True) 
    email_request_ref = Column(String(255), nullable=True) 
    
    fecha_creacion_registro = Column(DateTime, default=datetime.utcnow)
    fecha_modificacion_registro = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ConfigCurvasEquipo(Base): # Modelo "Lean"
    __tablename__ = "config_curvas_equipo" 
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    rig_id = Column(Integer, ForeignKey('rigs.id'), nullable=False, index=True)
    variable_pae_id = Column(Integer, ForeignKey('variables_pae_autom.id'), nullable=False, index=True)
    las_mnemonic_alias = Column(String(255), nullable=False, index=True)
    es_pae_requerida = Column(Boolean, nullable=False, default=False)
    se_importan_datos_de_este_alias = Column(Boolean, nullable=False, default=True)
    
    fecha_creacion_registro = Column(DateTime, default=datetime.utcnow)
    fecha_modificacion_registro = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# --- 2. Funciones Auxiliares ---
def obtener_rigs_pulling(session: Session) -> list[int]:
    print("PASO: Buscando IDs de equipos de Pulling ('PUL')...")
    rig_ids_tuples = session.query(Rigs.id).filter(Rigs.rig_type == 'PUL').all()
    ids = [rig_id for (rig_id,) in rig_ids_tuples]
    print(f"  INFO: Encontrados {len(ids)} equipos de Pulling: {ids if ids else 'Ninguno'}")
    return ids

def obtener_variable_pae_info(session: Session, nombre_pae_str: str) -> Optional[VariablesPaeAutom]:
    if not nombre_pae_str or not nombre_pae_str.strip():
        return None
    pae = session.query(VariablesPaeAutom).filter(VariablesPaeAutom.name_pae == nombre_pae_str.strip()).first()
    return pae

def leer_datos_tabla_variables_rig(engine_actual, nombre_tabla_variables: str) -> Optional[pd.DataFrame]:
    print(f"  PASO: Intentando leer de la tabla antigua: {nombre_tabla_variables}")
    try:
        inspector = inspect(engine_actual) 
        if not inspector.has_table(nombre_tabla_variables):
            print(f"    ERROR: Tabla fuente '{nombre_tabla_variables}' no encontrada.")
            return None
        
        # Leer solo las columnas que esperamos y existen en variables_XXX
        # Adaptar esta lista si tus columnas en variables_XXX se llaman diferente
        columnas_a_leer = ['name_wd', 'name_rdl', 'name_pae', 
                           'value_min_PAE', 'value_max_PAE', 'value_null', 
                           'import', 'required_pae']
        
        # Leer todas las columnas y luego seleccionar, o intentar leer solo las necesarias
        # Para ser más robusto a que falte alguna, leemos todo y luego accedemos con .get()
        df = pd.read_sql_table(nombre_tabla_variables, engine_actual)
        
        # Filtrar filas donde name_pae es NULL o vacío
        if 'name_pae' not in df.columns:
            print(f"    ERROR: La columna 'name_pae' no existe en la tabla '{nombre_tabla_variables}'. No se pueden procesar filas.")
            return pd.DataFrame() # Devolver DataFrame vacío

        df_filtrado = df[df['name_pae'].notna() & (df['name_pae'].astype(str).str.strip() != '')].copy()
        
        # Convertir a string y limpiar espacios para columnas clave que esperamos como string
        for col in ['name_wd', 'name_rdl', 'name_pae', 'import', 'required_pae']:
            if col in df_filtrado.columns:
                 df_filtrado.loc[:, col] = df_filtrado[col].astype(str).str.strip()
            else:
                # Si una columna crítica como 'name_wd' falta, podría ser un problema.
                # Para 'import' o 'required_pae', podríamos asumir un default si faltan.
                print(f"      ADVERTENCIA: Columna '{col}' no encontrada en tabla '{nombre_tabla_variables}'.")
                if col in ['name_wd', 'name_pae']: # Columnas esenciales
                     print(f"      ERROR CRITICO: La columna esencial '{col}' falta en '{nombre_tabla_variables}'. No se puede continuar con esta tabla.")
                     return pd.DataFrame() # Devolver DataFrame vacío
                df_filtrado.loc[:, col] = "" # Crear columna vacía para evitar KeyError

        print(f"    INFO: Leídas {len(df_filtrado)} filas de '{nombre_tabla_variables}' con 'name_pae' informado y no vacío.")
        return df_filtrado
    except Exception as e:
        print(f"    ERROR al leer la tabla '{nombre_tabla_variables}': {e}")
        return None

# --- 3. Función Principal de Migración ---
def migrar_datos_pulling_python():
    db_session = SessionLocal()
    print("INICIANDO MIGRACIÓN PYTHON PARA EQUIPOS DE PULLING...")

    try:
        print(f"PASO: Vaciando tabla '{ConfigVariablesPAE.__tablename__}'...")
        db_session.execute(text(f"TRUNCATE TABLE {ConfigVariablesPAE.__tablename__}"))
        print(f"PASO: Vaciando tabla '{ConfigCurvasEquipo.__tablename__}'...")
        db_session.execute(text(f"TRUNCATE TABLE {ConfigCurvasEquipo.__tablename__}"))
        db_session.commit()
        print("  INFO: Tablas de destino vaciadas exitosamente.")
    except Exception as e:
        db_session.rollback()
        print(f"FATAL: ERROR al vaciar tablas de destino: {e}. Revisa los nombres y permisos.")
        db_session.close()
        return

    ids_rigs_pulling = obtener_rigs_pulling(db_session)
    if not ids_rigs_pulling:
        print("FINALIZADO: No se encontraron equipos de Pulling para migrar.")
        db_session.close()
        return

    for rig_id_actual in ids_rigs_pulling:
        nombre_tabla_fuente = f"variables_{rig_id_actual}" 
        print(f"\n--- PROCESANDO Rig ID: {rig_id_actual} (Tabla Fuente: '{nombre_tabla_fuente}') ---")
        
        processed_config_pae_keys_for_current_rig = set() 

        df_datos_rig_antiguo = leer_datos_tabla_variables_rig(engine, nombre_tabla_fuente)

        if df_datos_rig_antiguo is None or df_datos_rig_antiguo.empty:
            print(f"  INFO: No hay datos válidos para procesar en '{nombre_tabla_fuente}' o la tabla no se pudo leer. Saltando este rig.")
            continue

        for index, fila_antigua in df_datos_rig_antiguo.iterrows():
            nombre_pae_antiguo = fila_antigua.get('name_pae', '') 
            
            print(f"  Procesando fila de '{nombre_tabla_fuente}' con name_pae original: '{nombre_pae_antiguo}' (WD: '{fila_antigua.get('name_wd', '')}')")

            obj_variable_pae = obtener_variable_pae_info(db_session, nombre_pae_antiguo)
            
            if not obj_variable_pae:
                print(f"    ADVERTENCIA: No se encontró PAE ID en 'variables_pae_autom' para name_pae = '{nombre_pae_antiguo}'. Se omite esta entrada.")
                continue
            
            id_variable_pae_actual = obj_variable_pae.id
            descripcion_pae_general = obj_variable_pae.descripcion_pae
            print(f"    INFO: PAE Encontrada en 'variables_pae_autom': ID={id_variable_pae_actual}, Nombre='{obj_variable_pae.name_pae}'")

            # ---- A. Poblar Config_Variables_PAE ----
            config_key = (rig_id_actual, id_variable_pae_actual)

            if config_key not in processed_config_pae_keys_for_current_rig:
                nueva_config_pae = ConfigVariablesPAE(
                    rig_id=rig_id_actual,
                    variable_pae_id=id_variable_pae_actual,
                    descripcion_pae_objetivo=descripcion_pae_general, 
                    valor_min_pae_esperado=fila_antigua.get('value_min_PAE'),
                    valor_max_pae_esperado=fila_antigua.get('value_max_PAE'),
                    valor_nulo_adicional_las=fila_antigua.get('value_null'),
                    grupo_pae=None, 
                    alarma_minima=None,
                    alarma_maxima=None,
                    unidad_id=None, 
                    mostrar_en_dashboard=None,
                    cantidad_decimales=None,
                    date_start_var=None, 
                    date_start_setting_var=None, 
                    email_request_ref=None 
                )
                db_session.add(nueva_config_pae)
                print(f"      INFO: Preparando para INSERTAR en Config_Variables_PAE: rig_id={rig_id_actual}, pae_id={id_variable_pae_actual}")
                processed_config_pae_keys_for_current_rig.add(config_key)
            # else: (No es necesario el print aquí, ya que solo se añade una vez)

            # ---- B. Poblar config_curvas_equipo (Lean) ----
            mnemonicos_a_mapear = []
            name_wd = fila_antigua.get('name_wd', '')
            name_rdl = fila_antigua.get('name_rdl', '')

            if name_wd:
                mnemonicos_a_mapear.append(name_wd)
            if name_rdl and name_rdl != name_wd:
                 mnemonicos_a_mapear.append(name_rdl)
            
            es_requerida_flag = True if fila_antigua.get('required_pae', '').upper() == 'SI' else False
            se_importan_flag = True if fila_antigua.get('import', '').upper() == 'SI' else False

            for mnem in set(mnemonicos_a_mapear): 
                if not mnem: 
                    continue

                # Verificar si ya existe este mapeo exacto antes de añadir a la sesión
                mapeo_existente = db_session.query(ConfigCurvasEquipo).filter_by(
                    rig_id=rig_id_actual,
                    variable_pae_id=id_variable_pae_actual,
                    las_mnemonic_alias=mnem
                ).first()

                if not mapeo_existente:
                    nuevo_mapeo = ConfigCurvasEquipo(
                        rig_id=rig_id_actual,
                        variable_pae_id=id_variable_pae_actual,
                        las_mnemonic_alias=mnem,
                        es_pae_requerida=es_requerida_flag,
                        se_importan_datos_de_este_alias=se_importan_flag
                    )
                    db_session.add(nuevo_mapeo)
                    print(f"      INFO: Preparando para INSERTAR en config_curvas_equipo: alias='{mnem}' -> pae_id={id_variable_pae_actual}")
                # else: (No es necesario el print aquí)
        
        try:
            print(f"  INTENTANDO COMMIT para Rig ID: {rig_id_actual}...")
            db_session.commit()
            print(f"  COMMIT exitoso para Rig ID: {rig_id_actual}")
        except SQLAlchemyError as e:
            db_session.rollback()
            print(f"  ERROR SQLALCHEMY al hacer commit para Rig ID: {rig_id_actual}. Rollback realizado. Error: {e}")
        except Exception as e_gen:
            db_session.rollback()
            print(f"  ERROR GENERAL procesando Rig ID: {rig_id_actual}. Rollback realizado. Error: {e_gen}")

    db_session.close()
    print("\n--- MIGRACIÓN CON PYTHON PARA EQUIPOS DE PULLING FINALIZADA ---")

# --- 4. Bloque de Ejecución ---
if __name__ == "__main__":
    # Antes de ejecutar:
    # 1. Reemplaza "tu_usuario_aqui", "tu_contraseña_aqui", etc., con tus credenciales reales.
    # 2. Asegúrate de que las tablas de destino (`Config_Variables_PAE` y `config_curvas_equipo`)
    #    existan en tu BD con la estructura correcta (Config_Variables_PAE con los nuevos campos de fecha/mail,
    #    y config_curvas_equipo "adelgazada"). Este script NO las crea ni las modifica.
    # 3. Asegúrate de que las tablas fuente (`rigs`, `variables_pae_autom`, `variables_XXX`) existan.
    # 4. ¡PRUEBA ESTO EN UN ENTORNO DE DESARROLLO CON COPIA DE TUS DATOS PRIMERO!
    
    print("Iniciando script de migración Python...")
    migrar_datos_pulling_python()