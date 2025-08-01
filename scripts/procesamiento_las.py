#!/usr/bin/env python3
# procesamiento_las.py
import argparse
import os
import sys
import subprocess
import json
from typing import Any, Optional, Tuple, Dict, List 
import lasio
from datetime import datetime as dt, date, timedelta 
import re
import logging
import locale 

from sqlalchemy import inspect, text, func as sqlfunc

# Tipos de SQLAlchemy necesarios para los modelos
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime as SQLAlchemyDateTime,
    TEXT, Enum as SQLAlchemyEnum, Date as SQLAlchemyDate, CHAR, SmallInteger,
    Boolean, Numeric 
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from dotenv import load_dotenv
from pathlib import Path

# Configuración del logger
logger = logging.getLogger(__name__)

# Carga de .env para pruebas individuales (cuando __name__ == '__main__')
if __name__ == "__main__":
    try:
        SCRIPT_DIR_PROC_TEST = Path(__file__).resolve().parent
        PROJECT_ROOT_PROC_TEST = SCRIPT_DIR_PROC_TEST.parent
    except NameError:
        SCRIPT_DIR_PROC_TEST = Path(os.getcwd())
        PROJECT_ROOT_PROC_TEST = SCRIPT_DIR_PROC_TEST.parent if SCRIPT_DIR_PROC_TEST.name.lower() == "scripts" else SCRIPT_DIR_PROC_TEST

    config_path_proc_test = PROJECT_ROOT_PROC_TEST / "config.env"
    if config_path_proc_test.exists():
        if not logging.getLogger().hasHandlers():
            logging.basicConfig(level=logging.INFO, 
                                format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
                                handlers=[logging.StreamHandler(sys.stdout)])
        logger.info(f"Cargando .env desde {config_path_proc_test} para prueba de procesamiento_las.py")
        load_dotenv(config_path_proc_test)
    else:
        if not logging.getLogger().hasHandlers():
            logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
        logger.warning(f"Archivo {config_path_proc_test} no encontrado para prueba de procesamiento_las.py.")

try:
    # Definir clases de utilidad sin importar directamente
    class UtilWell: 
        def __init__(self, id: int, name: str, uwi: Optional[str] = None):
            self.id = id
            self.name = name
            self.uwi = uwi
    
    class UtilOilfield: 
        def __init__(self, id: int, yacimiento: str, codigo: str):
            self.id = id
            self.yacimiento = yacimiento
            self.codigo = codigo
    
    def identificar_pozo_db(db_session, nombre_pozo: str, uwi_pozo: str = "") -> Optional[UtilWell]:
        """
        Función que ejecuta el script import_las_autom_unificado.py via subprocess
        para identificar un pozo en la base de datos.
        """
        try:
            script_path = os.path.join(os.path.dirname(__file__), 'import_las_autom_unificado.py')
            
            if not os.path.exists(script_path):
                logger.error(f"Script import_las_autom_unificado.py no encontrado en: {script_path}")
                return None
            
            # Preparar datos de entrada para el script
            input_data = f"{nombre_pozo}\n{uwi_pozo}\n"
            
            # Obtener el entorno Python actual (con variables de DB)
            env = os.environ.copy()
            
            # Ejecutar el script con subprocess
            result = subprocess.run(
                [sys.executable, script_path],
                input=input_data,
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )
            
            if result.returncode == 0 and result.stdout.strip():
                # Parsear la salida del script
                output_lines = result.stdout.strip().split('\n')
                for line in output_lines:
                    if line.startswith('RESULTADO:'):
                        try:
                            # Extraer el JSON de la línea de resultado
                            json_part = line.replace('RESULTADO:', '').strip()
                            resultado = json.loads(json_part)
                            
                            if resultado.get('exito') and resultado.get('well_id'):
                                logger.info(f"Script unificado encontró pozo: ID={resultado['well_id']}, Nombre='{resultado.get('well_name', '')}'")
                                return UtilWell(
                                    id=resultado['well_id'],
                                    name=resultado.get('well_name', ''),
                                    uwi=resultado.get('well_uwi', '')
                                )
                        except (json.JSONDecodeError, KeyError) as e:
                            logger.error(f"Error parseando resultado del script unificado: {e}")
                            continue
                
                logger.warning(f"Script unificado ejecutado pero no encontró pozo válido para '{nombre_pozo}' / '{uwi_pozo}'")
                return None
            else:
                if result.stderr:
                    logger.error(f"Error en script unificado: {result.stderr}")
                logger.warning(f"Script unificado no retornó resultado exitoso para '{nombre_pozo}' / '{uwi_pozo}'")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout ejecutando script import_las_autom_unificado.py para '{nombre_pozo}'")
            return None
        except Exception as e:
            logger.error(f"Error ejecutando script import_las_autom_unificado.py para '{nombre_pozo}': {e}")
            return None

except ImportError as e:
    logger.critical(f"CRÍTICO: Error configurando funciones de identificación: {e}. "
                    "Asegúrate que el script 'import_las_autom_unificado.py' "
                    "exista en la misma carpeta 'scripts' y sea ejecutable.", exc_info=True)
    
    # Clases fallback si hay error
    class UtilWell: 
        def __init__(self, id: int, name: str, uwi: Optional[str] = None):
            self.id = id
            self.name = name
            self.uwi = uwi
    
    class UtilOilfield: 
        def __init__(self, id: int, yacimiento: str, codigo: str):
            self.id = id
            self.yacimiento = yacimiento
            self.codigo = codigo
    
    def identificar_pozo_db(*args, **kwargs) -> Optional[UtilWell]: 
        logger.error("Función identificar_pozo_db no disponible debido a error de configuración.")
        return None

Base = declarative_base()

class FilesImport(Base):
    __tablename__ = 'files_import_autom'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    date_time = Column(SQLAlchemyDateTime, default=sqlfunc.now(), onupdate=sqlfunc.now())
    event_id = Column(Integer, nullable=True)
    STRT = Column(SQLAlchemyDateTime, nullable=True)
    STOP = Column(SQLAlchemyDateTime, nullable=True)
    DATE_LAS = Column("DATE", SQLAlchemyDateTime, nullable=True) 
    start_datos = Column(SQLAlchemyDateTime, nullable=True)
    end_datos = Column(SQLAlchemyDateTime, nullable=True)
    NULL_VAL = Column("NULL", String(255), nullable=True)
    COMP = Column(String(50), nullable=True)
    WELL = Column(String(100), nullable=True)
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
    variables_las = Column(String(50), nullable=True)
    registro_seg = Column(Integer, nullable=True) 
    backup_date = Column(SQLAlchemyDate, nullable=True)
    process_time_seg_db = Column("process_time_seg", Numeric(20, 4), nullable=True)
    permite_proceso = Column(Integer, nullable=True, default=0)
    estado_sistema_marcado = Column(SQLAlchemyEnum('PENDIENTE','VOLCADO WO','VOLCADO PERF', name='estado_sistema_enum_fi_v6'), nullable=True, default='PENDIENTE')
    file_delete = Column(SQLAlchemyEnum('Borrado','En sistema', name='file_delete_enum_fi_v6'), nullable=True, default='En sistema')
    size_bytes = Column("size", Integer, nullable=True, default=0)

class Rig(Base):
    __tablename__ = 'rigs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    contractor_id = Column(Integer, nullable=False) 
    id_equipo_sistema_marcado = Column(Integer, nullable=True)
    rig_type = Column(SQLAlchemyEnum('WO','PER','PUL', name='rig_type_enum_rigs'), nullable=True)

class Event(Base):
    __tablename__ = 'events_autom'
    id = Column(Integer, primary_key=True, autoincrement=True)
    well_id = Column(Integer, nullable=True, default=0)
    pw = Column(CHAR(1), nullable=True) 
    rig_id = Column(Integer, nullable=True, default=0)
    type_event = Column(String(10), nullable=True, default='0') 
    event_id_ow = Column(String(20), nullable=True, unique=True, default='0') # Longitud ajustada a 20
    date_start_ow = Column(SQLAlchemyDate, nullable=True) 
    date_start = Column(SQLAlchemyDate, nullable=True) 
    date_end = Column(SQLAlchemyDate, nullable=True)
    obs = Column(String(255), nullable=True)
    activate = Column(SmallInteger, nullable=True, default=0) 
    backup_int_date = Column(SQLAlchemyDateTime, nullable=True)
    backup_int = Column(Boolean, nullable=True, default=False)
    tiempo_proceso = Column(Numeric(20,2), nullable=True)
    backup_ext_date = Column(SQLAlchemyDateTime, nullable=True)
    backup_ext = Column(Boolean, nullable=True, default=False)

class InfoProd(Base):
    __tablename__ = 'info_prod'
    id = Column(Integer, primary_key=True, autoincrement=True) 
    DATE_REPORT = Column(SQLAlchemyDate, nullable=True)
    UWI = Column(String(20), nullable=True, index=True)
    WELL = Column(String(255), nullable=True, index=True) 
    EVENT_ID = Column(String(50), nullable=True, unique=True) # Se mantiene en 50 aquí, la lógica del script truncará si es necesario
    EVENT_CODE = Column(String(255), nullable=True) 
    START_DATE = Column(SQLAlchemyDate, nullable=True) 
    RIG = Column(String(255), nullable=True)
    obs = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<InfoProd(id={self.id}, WELL='{self.WELL}', EVENT_ID='{self.EVENT_ID}', EVENT_CODE='{self.EVENT_CODE}')>"

class EventType(Base): # Descomentar esta línea
    __tablename__ = 'events_type'  # Descomentar esta línea
    id = Column(Integer, primary_key=True)  # Descomentar esta línea
    event_type = Column("event_type", String(50), unique=True, nullable=False)  # Descomentar esta línea
    # descripcion = Column(String(255), nullable=True) # Puedes mantener esta comentada si no la usas

    def __repr__(self): # Descomentar esta línea
        return f"<EventType(id={self.id}, event_type='{self.event_type}')>" # Descomentar esta línea

class LogImportLas(Base):
    __tablename__ = 'log_import_las'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre_script = Column(String(100), nullable=True)
    archivo_las = Column(String(255), nullable=True)
    estado = Column(String(50), nullable=True)
    mensaje = Column(TEXT, nullable=True)
    estado_procesamiento_interno = Column(String(50), nullable=True)
    mensaje_procesamiento_interno = Column(TEXT, nullable=True)
    fecha_procesamiento_interno = Column(SQLAlchemyDateTime, nullable=True)
    fecha_descarga = Column(SQLAlchemyDateTime, nullable=True, default=sqlfunc.now())

    def __repr__(self):
        return f"<LogImportLas(id={self.id}, archivo_las='{self.archivo_las}', estado='{self.estado}')>"

def extraer_valor_header(header_item: Optional[lasio.HeaderItem]) -> Optional[str]:
    if header_item is None: return None
    value = header_item.value
    if value is None: return None
    # Manejar explícitamente datetime y date para evitar problemas de formato directo a str
    if isinstance(value, (dt, date)): 
        return str(value) # O un formato específico si es necesario, ej. value.isoformat()
    if isinstance(value, (int, float)): return str(value).strip()
    return str(value).strip() if isinstance(value, str) else str(value).strip()

def parsear_fecha_las_simple(date_str: Optional[str]) -> Optional[dt]:
    if not date_str or not isinstance(date_str, str):
        if date_str is not None:
             logger.debug(f"El valor de fecha proporcionado no es una cadena: {date_str} (tipo: {type(date_str)})")
        return None
    cleaned_date_str = date_str.split(" : ")[0].strip()
    possible_formats = [
        "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%b/%Y %H:%M:%S",
        "%d-%b-%Y %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y", "%Y-%m-%d", "%d/%b/%Y", "%d-%b-%Y", "%Y/%m/%d", "%m/%d/%Y",
        "%d/%m/%y %H:%M:%S", "%d-%b-%y %H:%M:%S", "%m/%d/%y %H:%M:%S",
        "%d/%m/%y", "%d-%b-%y", "%m/%d/%y",
    ]
    for fmt in possible_formats:
        try: return dt.strptime(cleaned_date_str, fmt)
        except ValueError: continue
    locales_to_try_for_b = ['en_US.UTF-8', 'en_US', 'english_us', 'english', 'en_GB.UTF-8']
    original_locale_tuple = None 
    changed_locale_success = False
    if any("%b" in f or "%B" in f for f in possible_formats):
        try: original_locale_tuple = locale.getlocale(locale.LC_TIME)
        except ValueError: logger.debug("No se pudo obtener el locale actual LC_TIME.")
        for loc_setting in locales_to_try_for_b:
            try:
                locale.setlocale(locale.LC_TIME, loc_setting)
                changed_locale_success = True 
                logger.debug(f"Intentando parsear fecha con locale temporal para LC_TIME: {loc_setting}")
                for fmt in possible_formats:
                    if "%b" in fmt or "%B" in fmt: 
                        try: return dt.strptime(cleaned_date_str, fmt)
                        except ValueError: continue
            except locale.Error:
                logger.debug(f"Locale '{loc_setting}' no disponible o falló al establecer para LC_TIME.")
                changed_locale_success = False 
            except Exception as e_locale_set:
                logger.error(f"Error inesperado al intentar establecer locale '{loc_setting}' para LC_TIME: {e_locale_set}")
                changed_locale_success = False
        if original_locale_tuple is not None and changed_locale_success :
            try:
                locale.setlocale(locale.LC_TIME, original_locale_tuple)
                logger.debug(f"Locale LC_TIME restaurado a: {original_locale_tuple}")
            except locale.Error: logger.warning(f"No se pudo restaurar el locale original LC_TIME a {original_locale_tuple}.")
            except Exception as e_locale_restore: logger.error(f"Error inesperado al restaurar locale LC_TIME a '{original_locale_tuple}': {e_locale_restore}")
        elif original_locale_tuple is None and changed_locale_success:
            try:
                locale.setlocale(locale.LC_TIME, '') 
                logger.debug("Locale LC_TIME reseteado al por defecto del sistema.")
            except locale.Error: logger.warning("No se pudo resetear LC_TIME al locale por defecto del sistema después de un cambio temporal.")
    logger.warning(f"No se pudo parsear la fecha '{cleaned_date_str}' (original: '{date_str}') con los formatos y locales probados.")
    return None

def parsear_step_las(step_item: Optional[lasio.HeaderItem]) -> Tuple[Optional[float], Optional[int]]:
    step_float_original: Optional[float] = None
    step_en_segundos: Optional[int] = None
    if not step_item or step_item.value is None: return None, None
    try:
        value_str = str(step_item.value).strip()
        try: step_float_original = float(value_str)
        except ValueError:
            numeric_match_float = re.match(r"([\d\.\-]+)", value_str)
            if numeric_match_float: step_float_original = float(numeric_match_float.group(1))
            else:
                logger.warning(f"STEP LAS '{value_str}' no se pudo convertir a float.")
                return None, None
        unit_str = str(step_item.unit).strip().upper() if step_item.unit and step_item.unit.strip() else "S"
        if unit_str == "S": step_en_segundos = int(round(step_float_original))
        elif unit_str == "MS": step_en_segundos = int(round(step_float_original / 1000)) if step_float_original != 0 else 0
        elif unit_str == "MIN": step_en_segundos = int(round(step_float_original * 60))
        elif unit_str == "H": step_en_segundos = int(round(step_float_original * 3600))
        else:
            logger.debug(f"Unidad de STEP '{unit_str}' no reconocida como S, MS, MIN, H. Asumiendo que el valor '{step_float_original}' ya está en segundos.")
            step_en_segundos = int(round(step_float_original))
    except (ValueError, TypeError) as e:
        logger.warning(f"Error parseando STEP '{step_item.value}' (unidad: '{step_item.unit}'): {e}")
        return step_float_original, None
    return step_float_original, step_en_segundos

def _leer_cabecera_well(las_obj: lasio.LASFile) -> Dict[str, Any]:
    well_info_dict: Dict[str, Any] = {}
    if las_obj and las_obj.well:
        for header_item in las_obj.well:
            mnemonic = header_item.mnemonic.strip().upper()
            well_info_dict[mnemonic] = extraer_valor_header(header_item)
            if mnemonic == "STEP": well_info_dict["STEP_ITEM"] = header_item 
    else: logger.warning("No se encontró el bloque ~Well en el archivo LAS.")
    return well_info_dict

def _procesar_curvas_va_str(las_obj: lasio.LASFile) -> str:
    if not las_obj or not hasattr(las_obj, 'curves'): return "0"
    count = 0
    for curve in las_obj.curves:
        if curve.mnemonic and curve.mnemonic.strip(): count += 1
    return str(count)

def _crear_o_actualizar_registro_files_import(
    db_session: Session, nombre_archivo_las: str, filepath_las_completo: str, 
    well_header_info: Dict[str, Any], variables_las_str: str, id_evento_asociado: int 
) -> Tuple[bool, str, Optional[int]]:
    registro_fi = db_session.query(FilesImport).filter(FilesImport.name == nombre_archivo_las).first()
    accion = "actualizado"
    files_import_id: Optional[int] = None
    if not registro_fi:
        logger.info(f"Creando nuevo registro en files_import para '{nombre_archivo_las}'.")
        registro_fi = FilesImport(name=nombre_archivo_las) 
        db_session.add(registro_fi)
        accion = "creado"
    else:
        files_import_id = registro_fi.id
        logger.info(f"Actualizando registro existente en files_import para '{nombre_archivo_las}' (ID: {files_import_id}).")

    registro_fi.event_id = id_evento_asociado
    valor_strt_cabecera = well_header_info.get('STRT')
    registro_fi.STRT = parsear_fecha_las_simple(valor_strt_cabecera)
    if valor_strt_cabecera and registro_fi.STRT is None: logger.warning(f"Archivo '{nombre_archivo_las}': STRT de cabecera '{valor_strt_cabecera}' no pudo ser parseado para columna STRT.")
    valor_stop_cabecera = well_header_info.get('STOP')
    registro_fi.STOP = parsear_fecha_las_simple(valor_stop_cabecera)
    if valor_stop_cabecera and registro_fi.STOP is None: logger.warning(f"Archivo '{nombre_archivo_las}': STOP de cabecera '{valor_stop_cabecera}' no pudo ser parseado para columna STOP.")
    valor_date_cabecera = well_header_info.get('DATE')
    registro_fi.DATE_LAS = parsear_fecha_las_simple(valor_date_cabecera)
    if valor_date_cabecera and registro_fi.DATE_LAS is None: logger.warning(f"Archivo '{nombre_archivo_las}': DATE de cabecera '{valor_date_cabecera}' no pudo ser parseado para columna DATE_LAS.")
    if accion == "creado":
        registro_fi.start_datos = None
        registro_fi.end_datos = None
    _step_float, step_en_segundos = parsear_step_las(well_header_info.get('STEP_ITEM'))
    registro_fi.registro_seg = step_en_segundos
    registro_fi.NULL_VAL = well_header_info.get('NULL')
    registro_fi.COMP = well_header_info.get('COMP')
    registro_fi.WELL = well_header_info.get('WELL')
    registro_fi.FLD = well_header_info.get('FLD')
    registro_fi.LOC = well_header_info.get('LOC')
    registro_fi.SRVC = well_header_info.get('SRVC')
    registro_fi.CTRY = well_header_info.get('CTRY')
    registro_fi.LIC = well_header_info.get('LIC')
    registro_fi.REGION = well_header_info.get('REGION') 
    registro_fi.UWI = well_header_info.get('UWI', well_header_info.get('API'))
    registro_fi.LATI = well_header_info.get('LATI')
    registro_fi.LONG = well_header_info.get('LONG')
    registro_fi.GDAT = well_header_info.get('GDAT')
    registro_fi.variables_las = variables_las_str
    try:
        registro_fi.size_bytes = os.path.getsize(filepath_las_completo)
    except OSError as e_size:
        logger.warning(f"No se pudo obtener el tamaño del archivo '{filepath_las_completo}': {e_size}")
        if registro_fi.size_bytes is None and accion == "creado": registro_fi.size_bytes = 0
    try:
        db_session.flush() 
        if accion == "creado": files_import_id = registro_fi.id
        current_id_for_msg = files_import_id if files_import_id is not None else (registro_fi.id if hasattr(registro_fi, 'id') and registro_fi.id is not None else "desconocido")
        msg = f"Registro en files_import '{nombre_archivo_las}' (ID: {current_id_for_msg}) {accion} y preparado en sesión."
        logger.info(msg)
        return True, msg, current_id_for_msg
    except Exception as e:
        current_id_for_msg = files_import_id if files_import_id is not None else (registro_fi.id if hasattr(registro_fi, 'id') and registro_fi.id is not None else "desconocido")
        msg = f"Error al hacer flush del registro en files_import para '{nombre_archivo_las}' (ID: {current_id_for_msg}): {e}"
        logger.error(msg, exc_info=True)
        return False, msg, current_id_for_msg

def _extraer_fecha_del_nombre_archivo(nombre_archivo: str) -> Optional[date]:
    match_dmY = re.search(r'(\d{2})[-_](\d{2})[-_](\d{4})', nombre_archivo)
    if match_dmY:
        try:
            day, month, year = int(match_dmY.group(1)), int(match_dmY.group(2)), int(match_dmY.group(3))
            return date(year, month, day)
        except ValueError:
            logger.debug(f"Fecha inválida encontrada en nombre de archivo '{nombre_archivo}': {match_dmY.group(0)}")
            return None
    match_Ymd = re.search(r'(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)', nombre_archivo)
    if match_Ymd:
        try:
            year, month, day = int(match_Ymd.group(1)), int(match_Ymd.group(2)), int(match_Ymd.group(3))
            if 1900 <= year <= dt.now().year + 5 and 1 <= month <= 12 and 1 <= day <= 31:
                 return date(year, month, day)
            else:
                logger.debug(f"Componentes de fecha fuera de rango en '{nombre_archivo}' (YYYYMMDD): Y={year}, M={month}, D={day}")
        except ValueError:
            logger.debug(f"Fecha inválida (YYYYMMDD) encontrada en nombre de archivo '{nombre_archivo}': {match_Ymd.group(0)}")
            return None
    logger.debug(f"No se pudo extraer una fecha conocida del nombre de archivo: {nombre_archivo}")
    return None

def _obtener_o_crear_evento_desde_info_prod(
    db_session: Session,
    registro_info_prod: InfoProd,
    well_id_encontrado: int,
    rig_id_del_las: Optional[int], 
    rig_name_del_las: Optional[str], 
    nombre_archivo_para_obs: str
) -> Optional[int]:
    if not registro_info_prod:
        return None

    event_id_ow_candidato = registro_info_prod.EVENT_ID

    if event_id_ow_candidato and event_id_ow_candidato.strip():
        evento_existente = db_session.query(Event).filter(Event.event_id_ow == event_id_ow_candidato).first()
        if evento_existente:
            logger.info(f"Descartando candidato de info_prod (ID: {registro_info_prod.id}, EVENT_ID: {event_id_ow_candidato}) porque su EVENT_ID ya existe en events.event_id_ow (Evento ID: {evento_existente.id}).")
            return None 
    
    logger.info(f"Procediendo a crear nuevo evento desde info_prod (ID: {registro_info_prod.id}, EVENT_ID: '{event_id_ow_candidato}')")

    rig_id_para_nuevo_evento = rig_id_del_las 
    rig_name_final_para_obs = rig_name_del_las if rig_name_del_las else "Desconocido (LAS)"

    if registro_info_prod.RIG and registro_info_prod.RIG.strip():
        logger.info(f"InfoProd (ID: {registro_info_prod.id}) tiene RIG: '{registro_info_prod.RIG}'. Buscando en tabla 'rigs'.")
        rig_de_info_prod_en_bd = db_session.query(Rig).filter(sqlfunc.upper(Rig.name) == sqlfunc.upper(registro_info_prod.RIG.strip())).first()
        if rig_de_info_prod_en_bd:
            rig_id_para_nuevo_evento = rig_de_info_prod_en_bd.id
            rig_name_final_para_obs = rig_de_info_prod_en_bd.name
            logger.info(f"Se usará RIG de info_prod: '{rig_name_final_para_obs}' (ID: {rig_id_para_nuevo_evento}) para el nuevo evento.")
        else:
            logger.warning(f"RIG '{registro_info_prod.RIG}' de info_prod (ID: {registro_info_prod.id}) no encontrado en tabla 'rigs'. Se usará RIG del LAS ('{rig_name_final_para_obs}', ID: {rig_id_del_las}) si está disponible.")
    
    if rig_id_para_nuevo_evento is None:
        logger.error(f"No se pudo determinar un RIG_ID para el nuevo evento (info_prod ID: {registro_info_prod.id}). No se puede crear evento.")
        return None

    type_event_id_str = Event.type_event.default.arg if Event.type_event.default else '0' 
    event_code_info_prod = registro_info_prod.EVENT_CODE
    pw_valor = None 

    if event_code_info_prod and event_code_info_prod.strip():
        event_code_upper = event_code_info_prod.strip().upper()
        try:
            tipo_evento_obj = db_session.query(EventType).filter(sqlfunc.upper(EventType.event_type) == event_code_upper).first()
            if tipo_evento_obj:
                type_event_id_str = str(tipo_evento_obj.id) 
                logger.info(f"EVENT_CODE '{event_code_info_prod}' mapeado a EventType ID: {type_event_id_str} (desde tabla EventType).")
                
                # IDs numéricos de tu tabla events_type: 1=DON, 7=WO, 8=REP
                if tipo_evento_obj.id == 1: # DON
                    pw_valor = "P" # Asumiendo que un evento DON desde info_prod se asocia a una actividad de Perforación (P)
                elif tipo_evento_obj.id == 8: # REP
                    pw_valor = "R"
                elif tipo_evento_obj.id == 7: # WO
                    pw_valor = "W"
            else:
                logger.warning(f"EVENT_CODE '{event_code_info_prod}' de info_prod (ID: {registro_info_prod.id}) no encontrado en tabla 'EventType'. Usando type_event por defecto: '{type_event_id_str}'.")
        except Exception as e_query_event_type:
            logger.error(f"Error consultando tabla EventType para EVENT_CODE '{event_code_info_prod}': {e_query_event_type}. Usando type_event por defecto.")
    else:
        logger.warning(f"EVENT_CODE vacío en info_prod (ID: {registro_info_prod.id}). Usando type_event por defecto: '{type_event_id_str}'.")
    
    fecha_para_evento = registro_info_prod.START_DATE 
    if not fecha_para_evento:
        logger.warning(f"InfoProd (ID: {registro_info_prod.id}) no tiene START_DATE. Usando fecha de reporte '{registro_info_prod.DATE_REPORT}' si existe.")
        fecha_para_evento = registro_info_prod.DATE_REPORT
    
    if not fecha_para_evento:
        logger.error(f"No se pudo determinar una fecha de inicio para el nuevo evento desde info_prod (ID: {registro_info_prod.id}). No se puede crear evento.")
        return None

    try:
        # --- AJUSTE EN GENERACIÓN DE event_id_ow_FINAL SI ES VACÍO ---
        event_id_ow_final = event_id_ow_candidato if event_id_ow_candidato and event_id_ow_candidato.strip() and len(event_id_ow_candidato) <= 20 else None
        if not event_id_ow_final and event_id_ow_candidato: # Si era muy largo
             logger.warning(f"EVENT_ID '{event_id_ow_candidato}' de info_prod es muy largo (>20 chars) o inválido. Se generará uno.")
        
        if not event_id_ow_final : # Si estaba vacío o era muy largo/inválido
            # Formato: IP_<ID_INFO_PROD>_<HHMMSS> (3 + ~6 + 1 + 6 = ~16 chars)
            id_info_prod_str = str(registro_info_prod.id)
            timestamp_corta = dt.now().strftime('%H%M%S')
            event_id_ow_final = f"IP_{id_info_prod_str[:8]}_{timestamp_corta}"[:20] # Acortar id_info_prod_str si es muy largo
            logger.info(f"EVENT_ID de info_prod vacío, muy largo o inválido. Generando event_id_ow: {event_id_ow_final}")
        # --- FIN AJUSTE ---

        nuevo_evento = Event(
            well_id=well_id_encontrado,
            rig_id=rig_id_para_nuevo_evento,
            type_event=type_event_id_str, 
            event_id_ow=event_id_ow_final,
            date_start_ow=fecha_para_evento,   
            date_start=None, # Dejar date_start como None                  
            pw=pw_valor, 
            obs=f"Evento creado desde info_prod ID {registro_info_prod.id} para LAS {nombre_archivo_para_obs}. Equipo: {rig_name_final_para_obs}.",
            activate=1 
        )
        db_session.add(nuevo_evento)
        db_session.flush() 
        logger.info(f"Nuevo evento (ID: {nuevo_evento.id}) creado exitosamente desde info_prod (ID: {registro_info_prod.id}).")
        return nuevo_evento.id
    except Exception as e_create:
        logger.error(f"Error al crear nuevo evento desde info_prod (ID: {registro_info_prod.id}): {e_create}", exc_info=True)
        return None

# --- FUNCIÓN _crear_evento_placeholder MODIFICADA ---
def _crear_evento_placeholder(
    db_session: Session,
    well_id_encontrado: int,
    rig_id_del_las: Optional[int], 
    rig_name_del_las: Optional[str], 
    nombre_archivo_solo: str,
    fecha_referencia_las: Optional[date]
) -> Optional[int]:
    logger.info(f"Intentando crear evento placeholder para LAS: '{nombre_archivo_solo}'")

    type_event_id_str = Event.type_event.default.arg if Event.type_event.default else '0'
    pw_valor = None
    rig_type_str_para_obs = "Desconocido" 

    if rig_id_del_las is not None:
        rig_obj = db_session.query(Rig).filter(Rig.id == rig_id_del_las).first()
        if rig_obj and rig_obj.rig_type:
            # rig_type_enum_val es el string 'PER', 'WO', o 'PUL'
            rig_type_enum_val = str(rig_obj.rig_type) # Asegurarse que es string para comparación
            rig_type_str_para_obs = rig_type_enum_val
            logger.info(f"Rig ID {rig_id_del_las} ('{rig_name_del_las}') tiene rig_type: {rig_type_str_para_obs}")
            
            # Mapeo de rig_type a type_event (ID numérico de EventType)
            # IDs de tu tabla events_type: 1=DON, 7=WO, 8=REP
            if rig_type_enum_val == 'PER': 
                type_event_id_str = '1' # "DON"
                pw_valor = 'P'
            elif rig_type_enum_val == 'PUL': 
                type_event_id_str = '8' # "REP"
                pw_valor = 'R'
            elif rig_type_enum_val == 'WO': 
                type_event_id_str = '7' # "WO"
                pw_valor = 'W'
            else:
                logger.info(f"Rig_type '{rig_type_str_para_obs}' no tiene mapeo específico para placeholder type_event. Usando default '{type_event_id_str}'.")
        elif rig_obj:
             logger.info(f"Rig ID {rig_id_del_las} ('{rig_name_del_las}') no tiene rig_type definido. Usando type_event default.")
        else:
            logger.warning(f"No se encontró Rig con ID {rig_id_del_las} para determinar rig_type. Usando type_event default.")
    else:
        logger.info("No hay rig_id_del_las disponible. Usando type_event default para placeholder.")

    # Generar event_id_ow único para el placeholder, respetando longitud de 20
    nombre_base_limpio = re.sub(r'[^a-zA-Z0-9_-]', '', nombre_archivo_solo)
    # PH_ (3) + _ (1) + _ (1) = 5 caracteres fijos. Quedan 15 para nombre_base y timestamp.
    # Asignar, por ejemplo, 7 para nombre y 8 para timestamp.
    if len(nombre_base_limpio) > 7: 
        nombre_base_limpio = nombre_base_limpio[:7]
    
    timestamp_corta = dt.now().strftime('%H%M%S%f')[:8] # HHMMSSff (8 caracteres)
    event_id_ow_placeholder = f"PH_{nombre_base_limpio}_{timestamp_corta}"
    event_id_ow_placeholder = event_id_ow_placeholder[:20] # Asegurar que no exceda los 20 caracteres

    evento_existente_check = db_session.query(Event.id).filter(Event.event_id_ow == event_id_ow_placeholder).first()
    if evento_existente_check: # Si aun así colisiona (muy raro), intentar una vez más con un sufijo simple
        logger.warning(f"event_id_ow_placeholder generado '{event_id_ow_placeholder}' ya existe. Modificando ligeramente.")
        timestamp_corta_alt = dt.now().strftime('%S%f')[:6] # Diferente formato/longitud
        event_id_ow_placeholder = f"PH_{nombre_base_limpio[:5]}_{timestamp_corta_alt}_X"[:20]


    fecha_inicio_placeholder = fecha_referencia_las if fecha_referencia_las else dt.now().date()

    logger.info(f"Valores para nuevo evento placeholder: well_id={well_id_encontrado}, rig_id={rig_id_del_las}, type_event='{type_event_id_str}', pw='{pw_valor}', event_id_ow='{event_id_ow_placeholder}', date_start_ow='{fecha_inicio_placeholder}'")
    
    try:
        nuevo_evento_placeholder = Event(
            well_id=well_id_encontrado,
            rig_id=rig_id_del_las, 
            type_event=type_event_id_str,
            event_id_ow=event_id_ow_placeholder,
            date_start_ow=fecha_inicio_placeholder,
            date_start=None, 
            pw=pw_valor,
            obs=f"Evento placeholder creado para LAS: {nombre_archivo_solo}. Rig LAS: {rig_name_del_las if rig_name_del_las else 'N/A'} (Tipo: {rig_type_str_para_obs}). Asociación pendiente.",
            activate=0 
        )
        db_session.add(nuevo_evento_placeholder)
        db_session.flush()
        logger.info(f"Evento placeholder (ID: {nuevo_evento_placeholder.id}) creado para Pozo ID: {well_id_encontrado}, Rig ID: {rig_id_del_las}, TypeEvent: {type_event_id_str}.")
        return nuevo_evento_placeholder.id
    except Exception as e_create_ph:
        logger.error(f"Error al crear evento placeholder para LAS '{nombre_archivo_solo}': {e_create_ph}", exc_info=True)
        return None
# --- FIN NUEVA FUNCIÓN ---


def procesar_un_solo_las(filepath_las: str, db_session: Session) -> Tuple[bool, str, Optional[int], Optional[str], Optional[int], Optional[str], Optional[int]]:
    nombre_archivo_solo = os.path.basename(filepath_las)
    logger.info(f"Iniciando procesamiento interno para: {nombre_archivo_solo}")
    
    well_id_encontrado: Optional[int] = None
    well_name_encontrado: Optional[str] = None
    pozo_bd_obj: Optional[UtilWell] = None 
    rig_id_encontrado: Optional[int] = None 
    rig_name_del_archivo: Optional[str] = None
    id_evento_final_para_las: Optional[int] = None 
    fecha_referencia_las: Optional[date] = None 

    try:
        partes_del_nombre = nombre_archivo_solo.split('_')
        if partes_del_nombre:
            rig_name_del_archivo = partes_del_nombre[0]
            logger.info(f"Nombre de Equipo (RIG) extraído del nombre del archivo: '{rig_name_del_archivo}'")
    except Exception as e_parse_name:
        logger.warning(f"No se pudo extraer el nombre del RIG del nombre del archivo '{nombre_archivo_solo}': {e_parse_name}")

    if not os.path.exists(filepath_las):
        return False, f"Error Crítico: Archivo LAS no existe: {filepath_las}", None, None, None, rig_name_del_archivo

    las_obj = None
    try:
        encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'ascii']
        for enc in encodings_to_try:
            try:
                las_obj = lasio.read(filepath_las, encoding=enc, ignore_data=True)
                logger.info(f"Archivo LAS '{nombre_archivo_solo}' leído con encoding '{enc}' (datos de curvas ignorados).")
                break
            except Exception as e_las_read:
                logger.debug(f"Fallo al leer LAS '{nombre_archivo_solo}' con encoding '{enc}': {type(e_las_read).__name__} - {e_las_read}")
        if not las_obj:
            return False, f"No se pudo leer LAS '{nombre_archivo_solo}'.", None, None, None, rig_name_del_archivo
    except Exception as e:
        return False, f"Error inesperado leyendo LAS '{nombre_archivo_solo}': {e}", None, None, None, rig_name_del_archivo

    well_header_info = _leer_cabecera_well(las_obj)
    if not well_header_info:
        return False, f"No se pudo extraer info del ~Well de '{nombre_archivo_solo}'.", None, None, None, rig_name_del_archivo

    fecha_strt_dt = parsear_fecha_las_simple(well_header_info.get('STRT'))
    if fecha_strt_dt:
        fecha_referencia_las = fecha_strt_dt.date()
        logger.info(f"Fecha de referencia del LAS (desde STRT cabecera): {fecha_referencia_las}")
    else:
        fecha_del_nombre_archivo = _extraer_fecha_del_nombre_archivo(nombre_archivo_solo)
        if fecha_del_nombre_archivo:
            fecha_referencia_las = fecha_del_nombre_archivo
            logger.info(f"Fecha de referencia del LAS (desde nombre de archivo): {fecha_referencia_las}")
        else:
            fecha_date_dt = parsear_fecha_las_simple(well_header_info.get('DATE'))
            if fecha_date_dt:
                fecha_referencia_las = fecha_date_dt.date()
                logger.info(f"Fecha de referencia del LAS (desde DATE cabecera): {fecha_referencia_las}")
    
    if not fecha_referencia_las: # Si aún no hay fecha de referencia, usar la fecha actual
        fecha_referencia_las = dt.now().date()
        logger.warning(f"No se pudo determinar una fecha de referencia del LAS para '{nombre_archivo_solo}'. Usando fecha actual: {fecha_referencia_las}.")


    uwi_del_las_cabecera = well_header_info.get("UWI", well_header_info.get("API", "")).strip()
    nombre_pozo_del_las_cabecera = well_header_info.get("WELL", "").strip()

    if not nombre_pozo_del_las_cabecera and not uwi_del_las_cabecera:
        msg_no_id = f"LAS '{nombre_archivo_solo}' no contiene WELL ni UWI/API. No se puede buscar pozo."
        logger.warning(msg_no_id)
        return False, msg_no_id, None, None, None, rig_name_del_archivo

    logger.info(f"Intentando identificar pozo en BD. Nombre LAS: '{nombre_pozo_del_las_cabecera}', UWI/API LAS: '{uwi_del_las_cabecera}'")
    if not identificar_pozo_db:
        return False, "Función identificar_pozo_db no disponible.", None, None, None, rig_name_del_archivo
        
    pozo_bd_obj = identificar_pozo_db(db_session, nombre_pozo_del_las_cabecera, uwi_del_las_cabecera)

    if pozo_bd_obj:
        well_id_encontrado = int(pozo_bd_obj.id)
        well_name_encontrado = pozo_bd_obj.name
        logger.info(f"Pozo identificado en BD: {well_name_encontrado} (ID: {well_id_encontrado}, UWI DB: {pozo_bd_obj.uwi if hasattr(pozo_bd_obj, 'uwi') and pozo_bd_obj.uwi else 'N/A'})")
    else:
        logger.warning(f"Pozo NO identificado en BD para LAS '{nombre_archivo_solo}'.")
        return True, f"LAS: '{nombre_archivo_solo}'. Pozo BD: No identificado. No se procesa para evento.", None, None, None, rig_name_del_archivo, None

    if rig_name_del_archivo:
        try:
            rig_en_bd = db_session.query(Rig).filter(sqlfunc.upper(Rig.name) == sqlfunc.upper(rig_name_del_archivo)).first()
            if rig_en_bd:
                rig_id_encontrado = int(rig_en_bd.id)
                logger.info(f"Equipo (del LAS) identificado en BD: {rig_en_bd.name} (ID: {rig_id_encontrado})")
            else:
                logger.warning(f"Equipo con nombre '{rig_name_del_archivo}' (del LAS) NO encontrado en tabla 'rigs'.")
        except Exception as e_rig_lookup:
            logger.error(f"Error buscando equipo '{rig_name_del_archivo}' (del LAS) en BD: {e_rig_lookup}")
    else:
        logger.info("No se extrajo nombre de equipo del nombre de archivo, no se busca en BD.")

    if well_id_encontrado is not None and rig_id_encontrado is not None:
        try:
            valor_activate_buscado = 1
            evento_activo_obj = db_session.query(Event).filter(
                Event.well_id == well_id_encontrado,
                Event.rig_id == rig_id_encontrado,
                Event.activate == valor_activate_buscado
            ).order_by(Event.date_start.desc(), Event.id.desc()).first()

            if evento_activo_obj:
                id_evento_final_para_las = evento_activo_obj.id
                logger.info(f"EVENTO ACTIVO PRIMARIO (ID: {id_evento_final_para_las}) encontrado para Well ID: {well_id_encontrado}, Rig ID: {rig_id_encontrado}.")
            else:
                logger.info(f"No se encontró evento activo primario para Well ID: {well_id_encontrado}, Rig ID: {rig_id_encontrado}.")
        except Exception as e_event_lookup:
            logger.error(f"Error en búsqueda primaria de evento activo: {e_event_lookup}", exc_info=True)
    
    if id_evento_final_para_las is None and well_id_encontrado is not None:
        logger.info(f"Iniciando búsqueda secundaria de evento vía 'info_prod' para Pozo: '{well_name_encontrado}' (ID: {well_id_encontrado}).")
        
        query_info_prod = db_session.query(InfoProd)
        uwi_del_pozo_db = pozo_bd_obj.uwi if hasattr(pozo_bd_obj, 'uwi') and pozo_bd_obj.uwi else None
        
        if uwi_del_pozo_db:
            query_info_prod = query_info_prod.filter(InfoProd.UWI == uwi_del_pozo_db)
        elif well_name_encontrado:
            query_info_prod = query_info_prod.filter(InfoProd.WELL == well_name_encontrado)
        else:
            query_info_prod = None 
            logger.warning("No hay UWI ni Nombre de Pozo para buscar en info_prod.")

        if query_info_prod is not None and fecha_referencia_las: # fecha_referencia_las ya está definida
            fecha_inicio_rango = fecha_referencia_las - timedelta(days=15)
            fecha_fin_rango = fecha_referencia_las + timedelta(days=15)
            logger.info(f"Buscando en info_prod con rango de fechas para START_DATE: {fecha_inicio_rango} a {fecha_fin_rango}")
            query_info_prod = query_info_prod.filter(InfoProd.START_DATE.between(fecha_inicio_rango, fecha_fin_rango))
        
        if query_info_prod is not None:
            candidatos_info_prod = query_info_prod.order_by(InfoProd.START_DATE.desc(), InfoProd.id.desc()).all()
            logger.info(f"Se encontraron {len(candidatos_info_prod)} candidatos en info_prod (filtrados por rango de fecha).")

            for reg_info_prod_candidato in candidatos_info_prod:
                logger.debug(f"Procesando candidato de info_prod: {reg_info_prod_candidato}")
                evento_id_creado = _obtener_o_crear_evento_desde_info_prod(
                    db_session, reg_info_prod_candidato, well_id_encontrado,
                    rig_id_encontrado, rig_name_del_archivo, nombre_archivo_solo
                )
                if evento_id_creado:
                    id_evento_final_para_las = evento_id_creado
                    break 
            
            if not id_evento_final_para_las and candidatos_info_prod: # Si hubo candidatos pero ninguno resultó en un evento
                 logger.info("Todos los candidatos de info_prod fueron descartados (EVENT_ID ya existía en events) o falló la creación de evento.")
        else:
             logger.info("No se pudo construir la consulta para info_prod (faltaba UWI/Nombre de Pozo) o no se encontraron candidatos iniciales.")

    # --- TERCERA OPCIÓN: CREAR EVENTO PLACEHOLDER ---
    if id_evento_final_para_las is None and well_id_encontrado is not None:
        logger.info(f"No se encontró ni creó evento por vías primarias o secundarias (info_prod). Intentando crear evento placeholder.")
        id_evento_placeholder = _crear_evento_placeholder(
            db_session, well_id_encontrado, rig_id_encontrado, 
            rig_name_del_archivo, nombre_archivo_solo, 
            fecha_referencia_las if fecha_referencia_las else dt.now().date() 
        )
        if id_evento_placeholder:
            id_evento_final_para_las = id_evento_placeholder
            # El log de creación ya está dentro de _crear_evento_placeholder
        else:
            logger.error(f"Falló la creación del evento placeholder para LAS: {nombre_archivo_solo}")
    # --- FIN TERCERA OPCIÓN ---

    if id_evento_final_para_las is not None:
        logger.info(f"Procediendo a guardar datos en files_import para LAS '{nombre_archivo_solo}' asociado al Evento ID: {id_evento_final_para_las}")
        variables_las_str = _procesar_curvas_va_str(las_obj)
        exito_guardado, msg_guardado, _ = _crear_o_actualizar_registro_files_import(
            db_session, nombre_archivo_solo, filepath_las, well_header_info, variables_las_str, id_evento_final_para_las
        )
        if not exito_guardado:
            logger.error(f"FALLO AL GUARDAR EN files_import (Evento ID: {id_evento_final_para_las}): {msg_guardado}")
    elif well_id_encontrado is not None : 
        logger.warning(f"No se encontró/creó ningún evento para asociar el LAS '{nombre_archivo_solo}' (Pozo ID: {well_id_encontrado}). No se guardará en files_import.")
    
    mensaje_final = f"LAS: '{nombre_archivo_solo}'."
    mensaje_final += f" Pozo BD: {well_name_encontrado if well_name_encontrado else 'No identificado'} (ID: {well_id_encontrado if well_id_encontrado is not None else 'N/A'})."
    mensaje_final += f" Equipo (del LAS): '{rig_name_del_archivo if rig_name_del_archivo else 'No extraído'}' (ID BD: {rig_id_encontrado if rig_id_encontrado is not None else 'N/A'})."
    if id_evento_final_para_las is not None:
        mensaje_final += f" Evento Asociado ID: {id_evento_final_para_las}."
    else:
        mensaje_final += " Evento Asociado: Ninguno encontrado/creado."
        
    return True, mensaje_final, well_id_encontrado, well_name_encontrado, rig_id_encontrado, rig_name_del_archivo, id_evento_final_para_las

# --- INICIO DE LA NUEVA SECCIÓN if __name__ == "__main__": ---
if __name__ == "__main__":
    # El logger ya debería estar configurado por el bloque al inicio del script
    # si se ejecuta como __main__ y config.env existe.
    # Aseguramos un logging básico si no se configuró antes.
    if not logging.getLogger().hasHandlers() or not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
    
    logger.info("--- Iniciando Script para Procesar Archivos LAS Pendientes de 'log_import_las' ---")

    # --- Configuración de Argumentos ---
    parser_main = argparse.ArgumentParser(description="Procesa archivos LAS pendientes de la tabla 'log_import_las'.")
    parser_main.add_argument(
        "directorio_las_base", 
        type=str, 
        help="Ruta al directorio base donde se encuentran los archivos LAS referenciados en log_import_las."
    )
    args_main = parser_main.parse_args()

    DIRECTORIO_BASE_LAS = Path(args_main.directorio_las_base)
    if not DIRECTORIO_BASE_LAS.is_dir():
        logger.critical(f"El directorio base de LAS especificado no existe o no es un directorio: {DIRECTORIO_BASE_LAS}")
        sys.exit(1)
    logger.info(f"Directorio base para archivos LAS: {DIRECTORIO_BASE_LAS}")

    # --- Configuración de Base de Datos ---
    DB_HOST_MAIN = os.getenv("DB_HOST")
    DB_USER_MAIN = os.getenv("DB_USER")
    DB_PASSWORD_MAIN = os.getenv("DB_PASSWORD")
    DB_NAME_MAIN = os.getenv("DB_NAME")
    DB_PORT_MAIN = os.getenv("DB_PORT", "3306")

    if not all([DB_HOST_MAIN, DB_USER_MAIN, DB_PASSWORD_MAIN, DB_NAME_MAIN]):
        logger.critical("Faltan variables de BD en .env. Saliendo.")
        sys.exit(1)
    
    DATABASE_URL_MAIN = f"mysql+pymysql://{DB_USER_MAIN}:{DB_PASSWORD_MAIN}@{DB_HOST_MAIN}:{DB_PORT_MAIN}/{DB_NAME_MAIN}"
    engine_main = None
    SessionMain = None

    try:
        engine_main = create_engine(DATABASE_URL_MAIN, echo=True if os.getenv('SQLALCHEMY_ECHO', 'False').lower() == 'true' else False)
        SessionMain = sessionmaker(bind=engine_main)
        
        # Verificar existencia de tablas clave
        inspector_main = inspect(engine_main)
        tablas_main = inspector_main.get_table_names()
        logger.info(f"Tablas disponibles en la BD: {tablas_main}")
        if 'log_import_las' not in tablas_main: 
            logger.critical("LA TABLA 'log_import_las' NO EXISTE. No se puede continuar.")
            sys.exit(1)
        # Chequeos opcionales para otras tablas que usa procesar_un_solo_las
        if 'files_import' not in tablas_main: logger.error("ADVERTENCIA: La tabla 'files_import' no existe. 'procesar_un_solo_las' podría fallar.")
        if 'events' not in tablas_main: logger.warning("ADVERTENCIA: La tabla 'events' no existe.")
        # ... (otros chequeos si son necesarios) ...
        logger.info("Motor de BD y SessionMain creados correctamente.")
    except Exception as e_db_setup_main:
        logger.critical(f"Error CRÍTICO configurando la conexión a la BD: {e_db_setup_main}", exc_info=True)
        sys.exit(1)

    # --- Constantes para estados en log_import_las (ajusta según tus valores reales) ---
    ESTADO_DESCARGA_EXITOSA = "Descarga Exitosa"  # Condición para la columna 'estado'
    ESTADO_INTERNO_PENDIENTE = "PENDIENTE"        # Condición para la columna 'estado_procesamiento_interno'

    # Estados para actualizar la columna 'estado_procesamiento_interno'
    ESTADO_INTERNO_OK = "PROCESADO_OK"
    ESTADO_INTERNO_ERROR_PROC = "ERROR_PROCESAMIENTO_INTERNO"
    ESTADO_INTERNO_ERROR_NO_ENCONTRADO = "ERROR_ARCHIVO_NO_ENCONTRADO"
    ESTADO_INTERNO_ERROR_SCRIPT_EXCEPCION = "ERROR_SCRIPT_EXCEPCION_INTERNA"
    ESTADO_INTERNO_ERROR_NOMBRE_VACIO = "ERROR_NOMBRE_ARCHIVO_VACIO"
    
    NOMBRE_SCRIPT_ACTUAL = Path(__file__).name

    # --- Procesamiento de Archivos Pendientes ---
    registros_intentados = 0
    registros_actualizados_ok = 0
    registros_con_error = 0
    
    # Variable para almacenar los registros pendientes para el resumen
    registros_pendientes_iniciales = []


    with SessionMain() as session:
        try:
            logger.info(f"Consultando archivos en 'log_import_las' con estado = '{ESTADO_DESCARGA_EXITOSA}' Y estado_procesamiento_interno = '{ESTADO_INTERNO_PENDIENTE}' (o NULO)...")
            
            # Modificación de la consulta para incluir ambas condiciones
            # Se usa or_ para permitir que estado_procesamiento_interno sea PENDIENTE o NULL
            from sqlalchemy import or_
            registros_pendientes_iniciales = session.query(LogImportLas).filter(
                LogImportLas.estado == ESTADO_DESCARGA_EXITOSA,
                or_(
                    LogImportLas.estado_procesamiento_interno == ESTADO_INTERNO_PENDIENTE,
                    LogImportLas.estado_procesamiento_interno == None  # Para la primera vez que se procesa
                )
            ).all()
            
            if not registros_pendientes_iniciales:
                logger.info("No se encontraron registros pendientes que cumplan los criterios en 'log_import_las'. Finalizando.")
            else:
                logger.info(f"Se encontraron {len(registros_pendientes_iniciales)} registros pendientes en 'log_import_las' que cumplen los criterios.")

            for log_record in registros_pendientes_iniciales:
                registros_intentados += 1
                nombre_archivo_del_log = log_record.archivo_las
                id_log_record = log_record.id
                
                logger.info(f"--- Iniciando procesamiento para log_import_las ID: {id_log_record}, Archivo: {nombre_archivo_del_log} ---")
                
                if not nombre_archivo_del_log:
                    logger.error(f"Log ID {id_log_record}: El campo 'archivo_las' está vacío. Saltando.")
                    # No se toca log_record.estado
                    log_record.estado_procesamiento_interno = ESTADO_INTERNO_ERROR_NOMBRE_VACIO
                    log_record.mensaje_procesamiento_interno = "El nombre del archivo LAS estaba vacío en el registro del log."
                    log_record.nombre_script = NOMBRE_SCRIPT_ACTUAL
                    log_record.fecha_procesamiento_interno = dt.now()
                    registros_con_error += 1
                    session.commit() 
                    continue

                ruta_completa_las = DIRECTORIO_BASE_LAS / nombre_archivo_del_log
                
                logger.info(f"Ruta completa estimada del LAS: {ruta_completa_las}")

                if not ruta_completa_las.exists() or not ruta_completa_las.is_file():
                    logger.error(f"Archivo LAS '{nombre_archivo_del_log}' (ruta: {ruta_completa_las}) no encontrado. Actualizando estado_procesamiento_interno.")
                    # No se toca log_record.estado
                    log_record.estado_procesamiento_interno = ESTADO_INTERNO_ERROR_NO_ENCONTRADO
                    log_record.mensaje_procesamiento_interno = f"Archivo LAS físico no encontrado en la ruta: {ruta_completa_las}"
                    log_record.nombre_script = NOMBRE_SCRIPT_ACTUAL
                    log_record.fecha_procesamiento_interno = dt.now()
                    registros_con_error += 1
                    session.commit()
                    continue
                
                nuevo_estado_interno_log = None
                mensaje_para_log_interno = ""

                try:
                    # Llamada a la función principal de procesamiento
                    # procesar_un_solo_las devuelve: exito_bool, mensaje_str, well_id, well_name, rig_id, rig_name_file, id_evento_asociado
                    exito_interno_las, mensaje_interno_las, _, _, _, _, id_evento_final = \
                        procesar_un_solo_las(str(ruta_completa_las), session)
                    
                    if exito_interno_las:
                        logger.info(f"Procesamiento de '{nombre_archivo_del_log}' (vía procesar_un_solo_las) finalizado con éxito interno.")
                        nuevo_estado_interno_log = ESTADO_INTERNO_OK
                        mensaje_para_log_interno = mensaje_interno_las
                        registros_actualizados_ok += 1
                    else:
                        # Fallo controlado dentro de procesar_un_solo_las
                        logger.error(f"Fallo controlado durante procesar_un_solo_las para '{nombre_archivo_del_log}'. Mensaje: {mensaje_interno_las}")
                        nuevo_estado_interno_log = ESTADO_INTERNO_ERROR_PROC
                        mensaje_para_log_interno = mensaje_interno_las
                        registros_con_error += 1
                    
                except Exception as e_procesamiento_individual:
                    logger.error(f"Excepción MAYOR durante la llamada a procesar_un_solo_las para '{nombre_archivo_del_log}' (Log ID: {id_log_record}): {e_procesamiento_individual}", exc_info=True)
                    session.rollback() 
                                       
                    nuevo_estado_interno_log = ESTADO_INTERNO_ERROR_SCRIPT_EXCEPCION
                    mensaje_para_log_interno = f"Excepción en script: {str(e_procesamiento_individual)[:1000]}" 
                    registros_con_error += 1
                
                # Actualizar el registro en log_import_las
                # log_record.estado NO SE MODIFICA
                log_record.estado_procesamiento_interno = nuevo_estado_interno_log
                log_record.mensaje_procesamiento_interno = mensaje_para_log_interno
                log_record.nombre_script = NOMBRE_SCRIPT_ACTUAL 
                log_record.fecha_procesamiento_interno = dt.now()
                
                try:
                    session.commit() 
                    logger.info(f"Registro log_import_las ID {id_log_record} actualizado. Estado interno: '{nuevo_estado_interno_log}'.")
                except Exception as e_commit_log:
                    logger.error(f"Fallo al hacer commit para el registro log_import_las ID {id_log_record} después de actualizar estado: {e_commit_log}", exc_info=True)
                    session.rollback()
                    # Aquí el estado del log_record en la BD podría ser inconsistente si el commit falla.
                    # Se podría intentar marcarlo de alguna otra forma o reintentar.
                                
                logger.info(f"--- Fin del procesamiento para log ID: {id_log_record}, Archivo: {nombre_archivo_del_log} ---")

        except Exception as e_main_loop:
            logger.error(f"Error MAYOR durante el bucle principal de procesamiento de 'log_import_las': {e_main_loop}", exc_info=True)
            session.rollback() # Rollback general si algo falla en el bucle
    
    logger.info("--- RESUMEN FINAL DEL PROCESAMIENTO DE 'log_import_las' ---")
    logger.info(f"Total registros pendientes encontrados inicialmente (estado='{ESTADO_DESCARGA_EXITOSA}' y estado_interno='{ESTADO_INTERNO_PENDIENTE}'/NULL): {len(registros_pendientes_iniciales) if 'registros_pendientes_iniciales' in locals() and registros_pendientes_iniciales is not None else 'N/A'}")
    logger.info(f"Registros de log cuyo procesamiento se intentó: {registros_intentados}")
    logger.info(f"Registros de log cuyo procesamiento interno resultó en '{ESTADO_INTERNO_OK}': {registros_actualizados_ok}")
    logger.info(f"Registros de log cuyo procesamiento interno terminó en un estado de error: {registros_con_error}")
    logger.info("--- Fin del Script ---")

# --- FIN DE LA NUEVA SECCIÓN if __name__ == "__main__": ---
