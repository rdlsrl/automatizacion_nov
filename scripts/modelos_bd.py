import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
from typing import Optional # Importado para las anotaciones de tipo

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, Float, DateTime, 
    ForeignKey, Text, Date as SQLAlchemyDate, CHAR, SmallInteger, Numeric,
    Enum as SQLAlchemyEnum, UniqueConstraint, DECIMAL
)
from sqlalchemy.orm import relationship, declarative_base # sessionmaker no es necesaria aquí
from sqlalchemy.sql import func # Para server_default y onupdate con funciones SQL

# --- Carga de Configuración .env ---
try:
    SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = SCRIPT_DIR.parent 
except NameError: 
    SCRIPT_DIR = Path(os.getcwd())
    PROJECT_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name.lower() == "scripts" else SCRIPT_DIR

CONFIG_PATH_MODELOS = PROJECT_ROOT / "config.env"

if CONFIG_PATH_MODELOS.exists() and CONFIG_PATH_MODELOS.is_file():
    print(f"Cargando configuración desde {CONFIG_PATH_MODELOS} para modelos_bd.py")
    load_dotenv(CONFIG_PATH_MODELOS)
else:
    print(f"ADVERTENCIA: Archivo de configuración {CONFIG_PATH_MODELOS} no encontrado para modelos_bd.py")

Base = declarative_base()

# --- Modelos Centralizados ---

class VariablesPaeAutom(Base):
    __tablename__ = "variables_pae_autom"
    
    # --- Columnas que se mantienen ---
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name_pae = Column(String(255), unique=True, nullable=False, index=True, comment="Nombre descriptivo para el cliente")
    descripcion = Column(Text, nullable=True, comment="Notas o descripción general de la variable") # Renombrada
    categoria_pae = Column(String(100), nullable=True, index=True)
    subcategoria_pae = Column(String(100), nullable=True, index=True)
    es_calculada = Column(Boolean, default=False, nullable=False)
    fuente_tipica_dato = Column(String(100), nullable=True)
    alias_comunes_las = Column(Text, nullable=True, comment="Traductor para otros mnemónicos no estándar")
    activa = Column(Boolean, nullable=False, default=True)
    fecha_creacion = Column(DateTime, server_default=func.now(), nullable=False)
    fecha_modificacion = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # --- Columnas NUEVAS que hemos añadido ---
    rdl_nombre_interno = Column(String(255), nullable=True, comment="Nombre interno estándar de RDL (Pason/Descriptivo)")
    wits_code = Column(String(10), nullable=True, comment="Código numérico del estándar WITS")
    witsml_name = Column(String(255), nullable=True, comment="Nombre técnico del estándar WITSML")
    rdl_unidad_estandar_id = Column(Integer, ForeignKey('variables_units_autom.id_unidad'), nullable=True, comment="FK a la unidad estándar preferida por RDL")
    rdl_se_importa = Column(Boolean, nullable=False, default=True, comment="Regla por defecto: TRUE si se importa, FALSE si no.")

    # Las columnas obsoletas como 'valor_min_esperado_global' ya no están aquí.

    def __repr__(self):
        return f"<VariablesPaeAutom(id={self.id}, name_pae='{self.name_pae}', rdl_name='{self.rdl_nombre_interno}')>"


class VariablesUnitsAutom(Base):
    """
    Modelo para el catálogo centralizado de unidades.
    Mapea a la tabla 'variables_units_autom'.
    """
    __tablename__ = 'variables_units_autom'
    
    id_unidad = Column(Integer, primary_key=True, autoincrement=True)
    nombre_unidad = Column(String(50), nullable=False, unique=True, comment="Nombre estandarizado de la unidad (ej. 'm', 'psi')")
    tipo_dimension = Column(String(100), nullable=False, comment="Tipo de dimensión física (ej. 'longitud', 'presion')")
    descripcion_unidad = Column(Text, nullable=True, comment="Descripción detallada de la unidad")

    def __repr__(self):
        return f"<VariablesUnitsAutom(id={self.id_unidad}, nombre='{self.nombre_unidad}', dimension='{self.tipo_dimension}')>"


class VariablesUnitsConversion(Base):
    """
    Modelo para las reglas de conversión entre unidades.
    Mapea a la tabla 'variables_units_conversion'.
    """
    __tablename__ = 'variables_units_conversion'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    orig_unit_id = Column(Integer, ForeignKey('variables_units_autom.id_unidad'), nullable=False, comment="FK a la unidad de origen")
    dest_unit_id = Column(Integer, ForeignKey('variables_units_autom.id_unidad'), nullable=False, comment="FK a la unidad de destino")
    equation = Column(String(255), nullable=False, comment="Fórmula de conversión, usando 'x' para el valor original (ej. 'x*0.3048')")

    def __repr__(self):
        return f"<VariablesUnitsConversion(id={self.id}, de={self.orig_unit_id}, a={self.dest_unit_id}, eq='{self.equation}')>"


# ... (el resto de tus clases como Rigs, EventType, etc. continúan aquí debajo)


class Rigs(Base):
    __tablename__ = "rigs"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False) 
    contractor_id = Column(Integer, nullable=True) 
    id_equipo_sistema_marcado = Column(Integer, nullable=True)
    rig_type = Column(SQLAlchemyEnum('WO','PER','PUL', name='rig_type_enum_rigs_central_v2'), nullable=True) # Asegurar que el nombre del ENUM sea único si ya existe otro

    def __repr__(self):
        return f"<Rig(id={self.id}, name='{self.name}')>"

class EventType(Base):
    __tablename__ = 'events_type'
    id = Column(Integer, primary_key=True, autoincrement=True) 
    event_type = Column(String(50), unique=True, nullable=False)
    # descripcion = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<EventType(id={self.id}, event_type='{self.event_type}')>"

class Events(Base): 
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True, autoincrement=True) # Este es el event_id
    well_id = Column(Integer, nullable=True, default=0) # Considerar FK a una tabla 'wells'
    pw = Column(CHAR(1), nullable=True) 
    rig_id = Column(Integer, ForeignKey('rigs.id'), nullable=True, default=0, index=True)
    type_event = Column(Integer, ForeignKey('events_type.id'), nullable=True, index=True) # Asumiendo que type_event en BD es INT y FK a events_type.id
    event_id_ow = Column(String(20), nullable=True, unique=True, default='0')
    date_start_ow = Column(SQLAlchemyDate, nullable=True) 
    date_start = Column(SQLAlchemyDate, nullable=True) 
    date_end = Column(SQLAlchemyDate, nullable=True)
    obs = Column(String(255), nullable=True)
    activate = Column(SmallInteger, nullable=True, default=0) 
    backup_int_date = Column(DateTime, nullable=True)
    backup_int = Column(Boolean, nullable=True, default=False)
    tiempo_proceso = Column(Numeric(20,2), nullable=True)
    backup_ext_date = Column(DateTime, nullable=True)
    backup_ext = Column(Boolean, nullable=True, default=False)
    
    # rig = relationship("Rigs") 
    # event_type_details = relationship("EventType")

    def __repr__(self):
        return f"<Event(id={self.id}, event_id_ow='{self.event_id_ow}', rig_id={self.rig_id})>"

class FilesImport(Base): 
    __tablename__ = 'files_import'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False) 
    date_time = Column(DateTime, default=func.now()) 
    event_id = Column(Integer, ForeignKey('events.id'), nullable=True, index=True) 
    
    STRT_time = Column("STRT", DateTime, nullable=True, comment="Tiempo de inicio del LAS (si aplica)") 
    STOP_time = Column("STOP", DateTime, nullable=True, comment="Tiempo de fin del LAS (si aplica)") 
    STEP_interval_sec = Column("STEP", Integer, nullable=True, comment="Paso en segundos (si es log por tiempo)") 
    
    STRT_depth_md = Column(Float, nullable=True, comment="Profundidad MD inicial del LAS (WELL.STRT.M)")
    STOP_depth_md = Column(Float, nullable=True, comment="Profundidad MD final del LAS (WELL.STOP.M)")
    STEP_depth_md = Column(Float, nullable=True, comment="Paso de profundidad MD del LAS (WELL.STEP.M)")

    DATE_las_header = Column("DATE_LAS", DateTime, nullable=True, comment="Campo DATE de la cabecera LAS, parseado") 
    NULL_VAL_las = Column("NULL_VAL", String(255), nullable=True, comment="Campo NULL de la cabecera LAS")
    COMP = Column(String(50), nullable=True)
    WELL = Column(String(100), nullable=True, index=True)
    FLD = Column(String(100), nullable=True)
    LOC = Column(String(100), nullable=True)
    SRVC = Column(String(100), nullable=True)
    CTRY = Column(String(255), nullable=True)
    LIC = Column(String(100), nullable=True)
    REGION = Column(String(100), nullable=True)
    UWI = Column(String(100), nullable=True, index=True)
    LATI = Column(String(50), nullable=True)
    LONG = Column(String(50), nullable=True)
    GDAT = Column(String(50), nullable=True)
    
    variables_las_count = Column("variables_las", Integer, nullable=True, comment="Cantidad de variables/curvas en el LAS") 
    registro_seg = Column(Integer, nullable=True, comment="Si STEP se parseó a segundos, obsoleto si usamos STEP_interval_sec") 
    
    size_bytes = Column("size", Integer, nullable=True, default=0)
    process_flag = Column("process", Boolean, nullable=True, default=False) 
    process_date = Column(SQLAlchemyDate, nullable=True) 
    obs = Column(String(100), nullable=True) 
    intervencion = Column(SmallInteger, nullable=True, default=0) 
    start_datos_time = Column("start_datos", DateTime, nullable=True) 
    end_datos_time = Column("end_datos", DateTime, nullable=True) 
    backup_date = Column(SQLAlchemyDate, nullable=True)
    process_time_seg_db = Column("process_time_seg", Numeric(20, 4), nullable=True)
    permite_proceso = Column(Boolean, nullable=True, default=False) 
    
    estado_sistema_marcado = Column(SQLAlchemyEnum('PENDIENTE','VOLCADO WO','VOLCADO PERF', name='estado_sistema_enum_fi_central_v2'), nullable=True, default='PENDIENTE')
    file_delete_status = Column("file_delete", SQLAlchemyEnum('Borrado','En sistema', name='file_delete_enum_fi_central_v2'), nullable=True, default='En sistema')

    estado_procesamiento_curvas = Column(String(50), nullable=True, default='PENDIENTE_MAPEO', comment="Estado del mapeo de curvas de este archivo")

    # event = relationship("Events") 

    def __repr__(self):
        return f"<FilesImport(id={self.id}, name='{self.name}', event_id={self.event_id})>"

class Config_Variables_PAE(Base): 
    __tablename__ = "Config_Variables_PAE"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    rig_id = Column(Integer, ForeignKey('rigs.id'), nullable=False, index=True) 
    variable_pae_id = Column(Integer, ForeignKey('variables_pae_autom.id'), nullable=False, index=True)
    
    descripcion_pae_objetivo = Column(Text, nullable=True)
    pae_valor_min = Column(Float, nullable=True) 
    pae_valor_max = Column(Float, nullable=True) 
    valor_nulo_adicional_las = Column(Float, nullable=True) 
    grupo_pae = Column(String(100), nullable=True) 
    alarma_minima = Column(Float, nullable=True) 
    alarma_maxima = Column(Float, nullable=True) 
    pae_unidad_objetivo_id = Column(Integer, nullable=True) # FK a variables_units_autom.id_unidad
    mostrar_en_dashboard = Column(Boolean, nullable=True) 
    cantidad_decimales = Column(Integer, nullable=True) 
    
    date_start_var = Column(DateTime, nullable=True) 
    date_start_setting_var = Column(DateTime, nullable=True) 
    email_request_ref = Column(String(255), nullable=True) 
    
    fecha_creacion_registro = Column(DateTime, server_default=func.now())
    fecha_modificacion_registro = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    UniqueConstraint(rig_id, variable_pae_id, name='uq_config_rig_pae')

    def __repr__(self):
        return f"<Config_Variables_PAE(rig_id={self.rig_id}, pae_id={self.variable_pae_id})>"

class ConfigCurvasEquipo(Base): # Modelo "Lean"
    __tablename__ = "config_curvas_equipo" 

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    rig_id = Column(Integer, ForeignKey('rigs.id'), nullable=False, index=True)
    variable_pae_id = Column(Integer, ForeignKey('variables_pae_autom.id'), nullable=False, index=True)
    las_mnemonic_alias = Column(String(255), nullable=False, index=True)
    es_pae_requerida = Column(Boolean, nullable=False, default=False)
    se_importan_datos_de_este_alias = Column(Boolean, nullable=False, default=True)
    fecha_creacion_registro = Column(DateTime, server_default=func.now())
    fecha_modificacion_registro = Column(DateTime, server_default=func.now(), onupdate=func.now())

    UniqueConstraint(rig_id, variable_pae_id, las_mnemonic_alias, name='uq_lean_rig_pae_alias')

    def __repr__(self):
        return f"<ConfigCurvasEquipo(rig_id={self.rig_id}, pae_id={self.variable_pae_id}, alias='{self.las_mnemonic_alias}')>"

class ImportVariablesLas(Base): 
    __tablename__ = "import_variables_las"

    id_import_variable = Column(Integer, primary_key=True, autoincrement=True)
    id_files_import = Column(Integer, ForeignKey('files_import.id'), nullable=False, index=True) 
    indice_curva_en_las = Column(Integer, nullable=False, comment='Número de secuencia de la curva en el archivo LAS (1, 2, 3...)')
    mnemonic_original_las = Column(String(255), nullable=False, index=True)
    unidad_original_las = Column(String(50), nullable=True)
    descripcion_curva_las = Column(Text, nullable=True)
    orden_aparicion = Column(Integer, nullable=False, default=1)
    mapeado_a_variable_pae_id = Column(Integer, ForeignKey('variables_pae_autom.id'), nullable=True, index=True)
    mapeado_a_config_curva_id = Column(Integer, ForeignKey('config_curvas_equipo.id'), nullable=True, index=True)
    estado_mapeo_curva = Column(String(50), nullable=False, default='PENDIENTE_MAPEO')
    puntaje_confianza_mapeo = Column(Float, nullable=True)
    datos_curva_cargados = Column(Boolean, nullable=False, default=False)
    comentarios_proceso = Column(Text, nullable=True)
    fecha_registro_curva = Column(DateTime, default=datetime.utcnow)
    
    # Nuevas columnas para validación de unidades
    id_unidad_original_cat = Column(Integer, ForeignKey('variables_units_autom.id_unidad', name='fk_import_vars_unidad_orig_cat_model'), nullable=True)
    id_unidad_objetivo_cat = Column(Integer, ForeignKey('variables_units_autom.id_unidad', name='fk_import_vars_unidad_obj_cat_model'), nullable=True)
    estado_validacion_unidad = Column(String(50), nullable=True)
    factor_conv_aplicable = Column(DECIMAL(20, 10), nullable=True)
    offset_conv_aplicable = Column(DECIMAL(20, 10), nullable=True)
    comentarios_validacion_unidad = Column(Text, nullable=True)

    UniqueConstraint(id_files_import, indice_curva_en_las, name='uq_import_file_indice')
    UniqueConstraint(id_files_import, mnemonic_original_las, orden_aparicion, name='uq_import_file_mnem_orden')

    # Opcional: Definir relationships si quieres acceder a los objetos de unidad directamente desde SQLAlchemy
    # Asegúrate de que el nombre 'VariablesUnitsAutom' coincida con el nombre de tu clase para el catálogo de unidades.
    # unidad_original_catalogo = relationship("VariablesUnitsAutom", foreign_keys=[id_unidad_original_cat])
    # unidad_objetivo_catalogo = relationship("VariablesUnitsAutom", foreign_keys=[id_unidad_objetivo_cat])

    def __repr__(self):
        return f"<ImportVariablesLas(file_id={self.id_files_import}, index_las={self.indice_curva_en_las}, mnem='{self.mnemonic_original_las}')>"

class LogImportLas(Base): 
    __tablename__ = 'log_import_las' 
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre_script = Column(String(100), nullable=True)
    archivo_las = Column(String(255), nullable=True, index=True)
    estado = Column(String(50), nullable=True) 
    mensaje = Column(Text, nullable=True)
    estado_procesamiento_interno = Column(String(50), nullable=True) 
    mensaje_procesamiento_interno = Column(Text, nullable=True)
    fecha_procesamiento_interno = Column(DateTime, nullable=True)
    fecha_descarga = Column(DateTime, nullable=True, default=func.now())

    def __repr__(self):
        return f"<LogImportLas(id={self.id}, archivo_las='{self.archivo_las}', estado='{self.estado}')>"

class InfoProd(Base): 
    __tablename__ = 'info_prod' 
    id = Column(Integer, primary_key=True, autoincrement=True) 
    DATE_REPORT = Column(SQLAlchemyDate, nullable=True)
    UWI = Column(String(20), nullable=True, index=True) 
    WELL = Column(String(255), nullable=True, index=True) 
    EVENT_ID = Column(String(50), nullable=True, unique=True) 
    EVENT_CODE = Column(String(255), nullable=True) 
    START_DATE = Column(SQLAlchemyDate, nullable=True) 
    RIG = Column(String(255), nullable=True)
    obs = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<InfoProd(id={self.id}, WELL='{self.WELL}', EVENT_ID='{self.EVENT_ID}')>"

# --- Bloque para crear tablas ---
if __name__ == "__main__":
    pass  # Aquí puedes agregar código para crear tablas o pruebas si lo deseas