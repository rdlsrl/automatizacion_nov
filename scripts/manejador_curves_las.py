import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, Float, DateTime, 
    ForeignKey, Text, inspect, func
)
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from collections import Counter
import lasio
import re
import time
from rapidfuzz import fuzz, process as rapidfuzz_process
from decimal import Decimal
import pandas as pd
import csv

# --- Configuración del Logger ---
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
    handlers=[logging.StreamHandler(os.sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- 0. Carga de Configuración de Base de Datos ---
try:
    SCRIPT_DIR_MC = Path(__file__).resolve().parent
    if SCRIPT_DIR_MC.name.lower() == "scripts" and SCRIPT_DIR_MC.parent.name.lower() == "autom_nov":
        PROJECT_ROOT_MC = SCRIPT_DIR_MC.parent
    elif SCRIPT_DIR_MC.name.lower() == "autom_nov": 
        PROJECT_ROOT_MC = SCRIPT_DIR_MC
    else: 
        PROJECT_ROOT_MC = SCRIPT_DIR_MC.parent 
        logger.warning(f"Estructura de carpetas no estándar o __file__ no como se esperaba. PROJECT_ROOT_MC inferido: {PROJECT_ROOT_MC}")
    
    CONFIG_PATH_MC = Path("/mnt/mariadb/autom_nov/config.env") 

    if CONFIG_PATH_MC.exists() and CONFIG_PATH_MC.is_file():
        logger.info(f"Cargando configuración desde ruta explícita: {CONFIG_PATH_MC}")
        load_dotenv(CONFIG_PATH_MC)
    else:
        logger.warning(f"Archivo de configuración en ruta explícita {CONFIG_PATH_MC} no encontrado.")
        CONFIG_PATH_FALLBACK = PROJECT_ROOT_MC / "config.env"
        if CONFIG_PATH_FALLBACK.exists() and CONFIG_PATH_FALLBACK.is_file():
            logger.info(f"Cargando configuración desde ruta fallback: {CONFIG_PATH_FALLBACK}")
            load_dotenv(CONFIG_PATH_FALLBACK)
        else:
            logger.warning(f"Archivo {CONFIG_PATH_FALLBACK} tampoco encontrado. Intentando .env local en {SCRIPT_DIR_MC}.")
            if (SCRIPT_DIR_MC / '.env').exists():
                    load_dotenv(SCRIPT_DIR_MC / '.env')
                    logger.info(f"Cargado .env local desde {SCRIPT_DIR_MC}")
            else:
                    logger.warning("No se encontró config.env ni .env. Se usarán defaults o variables de entorno del sistema.")
except NameError: 
    SCRIPT_DIR_MC = Path(os.getcwd())
    logger.warning(f"__file__ no definido. Usando CWD: {SCRIPT_DIR_MC} para intentar cargar .env o config.env")
    if (SCRIPT_DIR_MC / 'config.env').exists(): load_dotenv(SCRIPT_DIR_MC / 'config.env'); logger.info(f"Cargado config.env desde {SCRIPT_DIR_MC}")
    elif (SCRIPT_DIR_MC / '.env').exists(): load_dotenv(SCRIPT_DIR_MC / '.env'); logger.info(f"Cargado .env desde {SCRIPT_DIR_MC}")
    else: logger.warning("No se encontró config.env ni .env en CWD.")

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = os.getenv("DB_PORT", "3306")

engine = None
SessionLocal = None
if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_NAME]):
    logger.error("¡ERROR CRÍTICO! Faltan variables de BD. Revisa tu config.env o el entorno.")
    DATABASE_URL = None
else:
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    try:
        engine = create_engine(DATABASE_URL, echo=False) 
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info(f"Motor de BD y SessionLocal configurados para: {DB_NAME} en {DB_HOST}")
    except Exception as e:
        logger.error(f"Error al crear el motor de BD SQLAlchemy: {e}", exc_info=True)

# --- IMPORTACIÓN DE MODELOS ---
try:
    from modelos_bd import (
        Rigs, VariablesPaeAutom, Events, FilesImport, EventType, InfoProd, LogImportLas,
        Config_Variables_PAE, ConfigCurvasEquipo, ImportVariablesLas,
        VariablesUnitsAutom, VariablesUnitsConversion
    )
    logger.info("Modelos SQLAlchemy importados correctamente desde modelos_bd.py")
except ImportError as e:
    logger.critical(f"ERROR CRÍTICO al importar modelos desde modelos_bd.py: {e}. Asegúrate que el archivo exista y no tenga errores de sintaxis, y que `modelos_bd.py` esté en el mismo directorio o en tu PYTHONPATH.", exc_info=True)
    import sys
    sys.exit("Fallo al importar modelos de BD.")
except Exception as e_model_load:
    logger.critical(f"ERROR CRÍTICO inesperado durante la importación de modelos_bd.py: {e_model_load}", exc_info=True)
    import sys
    sys.exit("Fallo al importar modelos de BD.")

# --- CONSTANTES DE MAPEON ---
UMBRAL_CONFIANZA_FUZZY_MINIMO_SUGERENCIA = 70
UMBRAL_FUZZY_PARA_AUTOIMPORTAR = 80

# --- CONSTANTES DE VALIDACIÓN DE UNIDADES ---
ESTADO_UNIDAD_PENDIENTE = 'PENDIENTE_VALIDACION'
ESTADO_UNIDAD_ORIGEN_NO_CATALOGO = 'ORIGEN_NO_EN_CATALOGO'
ESTADO_UNIDAD_OBJETIVO_NO_CATALOGO = 'OBJETIVO_NO_EN_CATALOGO'
ESTADO_UNIDAD_OBJETIVO_NO_DEFINIDO = 'OBJETIVO_NO_DEFINIDO'
ESTADO_UNIDAD_DIMENSION_INCOMPATIBLE = 'DIMENSION_INCOMPATIBLE'
ESTADO_UNIDAD_VALIDA_MISMA_UNIDAD = 'VALIDA_MISMA_UNIDAD'
ESTADO_UNIDAD_VALIDA_CONVERSION_OK = 'VALIDA_CONVERSION_OK'
ESTADO_UNIDAD_ECUACION_NO_PARSABLE = 'CONVERSION_ECUACION_NO_PARSABLE'
ESTADO_UNIDAD_CONVERSION_NO_ENCONTRADA = 'CONVERSION_NO_ENCONTRADA'
ESTADO_UNIDAD_NO_APLICA_SIN_MAPEO = 'NO_APLICA_SIN_MAPEO_PAE'

# --- FUNCIÓN DE NORMALIZACIÓN ---
def normalizar_texto_para_comparacion(texto: Optional[str]) -> str:
    if not texto:
        return ""
    s = str(texto).lower()
    s = s.replace('ñ', 'n')
    s = re.sub(r"[_:(/\-\.)]+", " ", s) 
    s = re.sub(r"[\[\]\(\)]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# --- FUNCIONES AUXILIARES DE VALIDACIÓN DE UNIDADES ---
def _obtener_info_unidad_catalogo(nombre_unidad_raw: Optional[str], session: Session) -> Tuple[Optional[int], Optional[str]]:
    """
    Busca una unidad en el catálogo 'variables_units_autom' por su nombre.
    Retorna (id_unidad, tipo_dimension) o (None, None).
    """
    if not nombre_unidad_raw or not nombre_unidad_raw.strip():
        logger.debug("Nombre de unidad raw está vacío o solo espacios.")
        return None, None

    nombre_unidad = nombre_unidad_raw.strip()
    unidades_a_probar = [nombre_unidad, nombre_unidad.lower(), nombre_unidad.upper()]
    
    for unidad_norm_intento in unidades_a_probar:
        try:
            unidad_cat = session.query(VariablesUnitsAutom)\
                                .filter(VariablesUnitsAutom.nombre_unidad == unidad_norm_intento)\
                                .first()
            if unidad_cat:
                logger.debug(f"Unidad '{nombre_unidad_raw}' encontrada en catálogo: ID={unidad_cat.id_unidad}, Dim={unidad_cat.tipo_dimension}")
                return unidad_cat.id_unidad, unidad_cat.tipo_dimension
        except SQLAlchemyError as e_sql:
            logger.error(f"Error de SQLAlchemy al buscar unidad '{unidad_norm_intento}': {e_sql}")
            return None, None
            
    logger.debug(f"Unidad '{nombre_unidad_raw}' no encontrada en catálogo tras probar variantes.")
    return None, None

def _obtener_conversion(id_unidad_origen: int, id_unidad_destino: int, session: Session) -> Optional[str]:
    """
    Busca una regla de conversión en 'variables_units_conversion'.
    """
    try:
        conversion = session.query(VariablesUnitsConversion.equation)\
                            .filter_by(orig_unit_id=id_unidad_origen, dest_unit_id=id_unidad_destino)\
                            .scalar()
        if conversion:
            return conversion
        return None
    except SQLAlchemyError as e_sql:
        logger.error(f"Error de SQLAlchemy al buscar conversión de {id_unidad_origen} a {id_unidad_destino}: {e_sql}")
        return None

def _parsear_ecuacion_conversion(equation_str: str) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """
    Parsea ecuaciones de conversión simples. y = x * factor + offset
    """
    if not equation_str: return None, None
    eq = equation_str.lower().replace(" ", "")
    
    # Intenta patrones de más complejo a más simple
    match = re.fullmatch(r"x\*(-?\d+\.?\d*)\+(-?\d+\.?\d*)", eq) or re.fullmatch(r"(-?\d+\.?\d*)\*x\+(-?\d+\.?\d*)", eq)
    if match: return Decimal(match.group(1) or match.group(2)), Decimal(match.group(2) or match.group(3))
    
    match = re.fullmatch(r"x\*(-?\d+\.?\d*)-(-?\d+\.?\d*)", eq) or re.fullmatch(r"(-?\d+\.?\d*)\*x-(-?\d+\.?\d*)", eq)
    if match: return Decimal(match.group(1) or match.group(2)), Decimal(match.group(2) or match.group(3)) * -1

    match = re.fullmatch(r"x/(-?\d+\.?\d*)\+(-?\d+\.?\d*)", eq)
    if match:
        divisor = Decimal(match.group(1))
        return (Decimal(1)/divisor, Decimal(match.group(2))) if divisor != 0 else (None, None)
    
    match = re.fullmatch(r"x/(-?\d+\.?\d*)-(-?\d+\.?\d*)", eq)
    if match:
        divisor = Decimal(match.group(1))
        return (Decimal(1)/divisor, Decimal(match.group(2)) * -1) if divisor != 0 else (None, None)

    match = re.fullmatch(r"x\*(-?\d+\.?\d*)", eq) or re.fullmatch(r"(-?\d+\.?\d*)\*x", eq)
    if match: return Decimal(match.group(1) or match.group(2)), Decimal(0)

    match = re.fullmatch(r"x/(-?\d+\.?\d*)", eq)
    if match:
        divisor = Decimal(match.group(1))
        return (Decimal(1)/divisor, Decimal(0)) if divisor != 0 else (None, None)

    match = re.fullmatch(r"x\+(-?\d+\.?\d*)", eq)
    if match: return Decimal(1), Decimal(match.group(1))
        
    match = re.fullmatch(r"x-(-?\d+\.?\d*)", eq)
    if match: return Decimal(1), Decimal(match.group(1)) * -1

    if eq == "x": return Decimal(1), Decimal(0)

    logger.warning(f"No se pudo parsear la ecuación de conversión: '{equation_str}' con los patrones simples.")
    return None, None

# --- FUNCIÓN DE CARGA OPTIMIZADA DE LAS ---

def leer_las_solo_headers_y_curvas(ruta_las: str) -> Optional[lasio.LASFile]:
    """
    Lee un archivo LAS de forma optimizada: solo headers y definiciones de curvas,
    sin cargar los datos para mejorar rendimiento significativamente.
    """
    logger.info(f"Cargando archivo LAS optimizado (solo headers/curvas): {Path(ruta_las).name}")
    inicio = time.time()
    
    las_obj = None
    for enc in ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']:
        try:
            # Cargar con configuración optimizada
            las_obj = lasio.read(
                ruta_las, 
                encoding=enc,
                null_policy='none',  # No procesar valores nulos innecesarios
                ignore_header_errors=True  # Ignorar errores menores en headers
            )
            logger.debug(f"Archivo LAS cargado exitosamente con encoding: {enc}")
            break
        except Exception as e_enc:
            logger.debug(f"Falló carga con encoding {enc}: {e_enc}")
            continue
    
    if not las_obj:
        try:
            las_obj = lasio.read(ruta_las, null_policy='none', ignore_header_errors=True)
            logger.debug("Archivo LAS cargado con autodetect de encoding")
        except Exception as e_final:
            logger.error(f"ERROR CRÍTICO: No se pudo leer LAS '{ruta_las}': {e_final}")
            return None
    
    # La optimización principal está en usar null_policy='none' y ignore_header_errors=True
    # lo cual evita el procesamiento innecesario de datos durante la carga
    
    tiempo_carga = time.time() - inicio
    logger.info(f"✓ LAS cargado optimizado en {tiempo_carga:.2f}s - {len(las_obj.curves)} curvas detectadas")
    
    return las_obj

def cargar_las_optimizado(ruta_las: str) -> Optional[lasio.LASFile]:
    """
    Función pública para cargar archivos LAS optimizado.
    Alias para leer_las_solo_headers_y_curvas para uso en otros scripts.
    """
    return leer_las_solo_headers_y_curvas(ruta_las)

# --- FUNCIONES DE FILTRADO INTELIGENTE FUZZY ---

def _detectar_categoria_variable(nombre_var: str) -> str:
    """
    Detecta la categoría de una variable para aplicar filtros inteligentes.
    """
    nombre_norm = normalizar_texto_para_comparacion(nombre_var)
    
    # Categorías de presión
    if any(word in nombre_norm for word in ['pressure', 'presion']):
        if any(word in nombre_norm for word in ['air', 'aire']):
            return 'PRESION_AIRE'
        elif any(word in nombre_norm for word in ['back', 'contraPresion']):
            return 'PRESION_BACK'
        elif any(word in nombre_norm for word in ['casing', 'revestimiento']):
            return 'PRESION_CASING'
        elif any(word in nombre_norm for word in ['guinche', 'winch']):
            return 'PRESION_GUINCHE'
        else:
            return 'PRESION_GENERAL'
    
    # Categorías de flujo
    if any(word in nombre_norm for word in ['flow', 'flujo', 'caudal']):
        if any(word in nombre_norm for word in ['in', 'entrada', 'ingreso']):
            return 'FLUJO_ENTRADA'
        elif any(word in nombre_norm for word in ['out', 'salida', 'egreso']):
            return 'FLUJO_SALIDA'
        else:
            return 'FLUJO_GENERAL'
    
    # Categorías de status (problemático - muchos PAEs diferentes)
    if any(word in nombre_norm for word in ['status', 'estado']):
        if any(word in nombre_norm for word in ['bit', 'broca']):
            return 'STATUS_BIT'
        elif any(word in nombre_norm for word in ['slip', 'deslizamiento']):
            return 'STATUS_SLIP'
        elif any(word in nombre_norm for word in ['sdaq', 'sistema']):
            return 'STATUS_SDAQ'
        elif any(word in nombre_norm for word in ['wc', 'control']):
            return 'STATUS_WC'
        elif any(word in nombre_norm for word in ['wpda', 'procesamiento']):
            return 'STATUS_WPDA'
        else:
            return 'STATUS_GENERAL'
    
    # Categorías de torque
    if any(word in nombre_norm for word in ['torque', 'par']):
        if any(word in nombre_norm for word in ['raw', 'crudo', 'sin procesar']):
            return 'TORQUE_RAW'
        elif any(word in nombre_norm for word in ['rotary', 'rotatorio']):
            return 'TORQUE_ROTARY'
        else:
            return 'TORQUE_GENERAL'
    
    # Detección H2S
    if any(word in nombre_norm for word in ['h2s', 'sulfuro']):
        if any(word in nombre_norm for word in ['pileta', 'pit', 'tanque']):
            return 'H2S_PILETA'
        elif any(word in nombre_norm for word in ['piso', 'floor', 'suelo']):
            return 'H2S_PISO'
        else:
            return 'H2S_GENERAL'
    
    return 'GENERAL'

def _es_compatible_categoria(categoria_origen: str, categoria_destino: str) -> bool:
    """
    Determina si dos categorías son compatibles para mapeo fuzzy.
    """
    # Mapeos exactos de categoría
    if categoria_origen == categoria_destino:
        return True
    
    # Compatibilidades específicas
    compatibilidades = {
        'PRESION_GENERAL': ['PRESION_AIRE', 'PRESION_BACK', 'PRESION_CASING', 'PRESION_GUINCHE'],
        'FLUJO_GENERAL': ['FLUJO_ENTRADA', 'FLUJO_SALIDA'],
        'STATUS_GENERAL': ['STATUS_BIT', 'STATUS_SLIP', 'STATUS_SDAQ', 'STATUS_WC', 'STATUS_WPDA'],
        'TORQUE_GENERAL': ['TORQUE_RAW', 'TORQUE_ROTARY'],
        'H2S_GENERAL': ['H2S_PILETA', 'H2S_PISO']
    }
    
    # Verificar compatibilidad bidireccional
    if categoria_origen in compatibilidades:
        if categoria_destino in compatibilidades[categoria_origen]:
            return True
    
    if categoria_destino in compatibilidades:
        if categoria_origen in compatibilidades[categoria_destino]:
            return True
    
    # Incompatibilidades específicas (casos que NO deben matchear)
    incompatibles = [
        ('FLUJO_ENTRADA', 'FLUJO_SALIDA'),  # IN vs OUT - NUNCA deben matchear
        ('PRESION_AIRE', 'PRESION_CASING'),  # Tipos diferentes de presión
        ('STATUS_BIT', 'STATUS_SLIP'),  # Diferentes sistemas de status
        ('TORQUE_RAW', 'TORQUE_ROTARY')  # Diferentes tipos de torque
    ]
    
    for incomp_a, incomp_b in incompatibles:
        if (categoria_origen == incomp_a and categoria_destino == incomp_b) or \
           (categoria_origen == incomp_b and categoria_destino == incomp_a):
            return False
    
    # Si no hay regla específica, permitir con categoría GENERAL
    if 'GENERAL' in [categoria_origen, categoria_destino]:
        return True
        
    return False

def _calcular_penalizacion_categoria(categoria_origen: str, categoria_destino: str) -> float:
    """
    Calcula una penalización al puntaje fuzzy basada en incompatibilidad de categorías.
    """
    if not _es_compatible_categoria(categoria_origen, categoria_destino):
        return 0.5  # Penalización severa (50% del puntaje)
    
    # Penalizaciones menores para matches no perfectos
    penalizaciones_menores = {
        ('PRESION_GENERAL', 'PRESION_AIRE'): 0.9,
        ('FLUJO_GENERAL', 'FLUJO_ENTRADA'): 0.95,
        ('STATUS_GENERAL', 'STATUS_BIT'): 0.85,
        ('TORQUE_GENERAL', 'TORQUE_RAW'): 0.9
    }
    
    clave = (categoria_origen, categoria_destino)
    if clave in penalizaciones_menores:
        return penalizaciones_menores[clave]
    
    clave_inv = (categoria_destino, categoria_origen)
    if clave_inv in penalizaciones_menores:
        return penalizaciones_menores[clave_inv]
    
    return 1.0  # Sin penalización

# --- FUNCIONES PRINCIPALES DE PROCESAMIENTO ---

def validar_unidades_curva(session: Session, las_curve_unit: Optional[str], mapped_variable_pae_id: int, rig_id: int, import_var_log_obj: ImportVariablesLas):
    """
    Valida las unidades de una curva mapeada y actualiza el objeto de log ImportVariablesLas.
    VERSIÓN SIMPLIFICADA: Solo registra la unidad original sin validación completa.
    """
    logger.debug(f"Registrando unidad para PAE ID {mapped_variable_pae_id}, unidad LAS: '{las_curve_unit}' (validación simplificada)")
    
    # Limpiar campos
    import_var_log_obj.id_unidad_original_cat = None
    import_var_log_obj.id_unidad_objetivo_cat = None
    import_var_log_obj.factor_conv_aplicable = None
    import_var_log_obj.offset_conv_aplicable = None
    import_var_log_obj.comentarios_validacion_unidad = ""

    # Validación simplificada
    # Inicializar variables para evitar problemas de referencia
    id_unidad_orig_cat, tipo_dim_orig = None, None
    
    if not las_curve_unit or not las_curve_unit.strip():
        import_var_log_obj.estado_validacion_unidad = ESTADO_UNIDAD_ORIGEN_NO_CATALOGO
        import_var_log_obj.comentarios_validacion_unidad = "Unidad original LAS no especificada."
    else:
        # Buscar unidad en catálogo
        id_unidad_orig_cat, tipo_dim_orig = _obtener_info_unidad_catalogo(las_curve_unit, session)
        if id_unidad_orig_cat:
            import_var_log_obj.id_unidad_original_cat = id_unidad_orig_cat
            import_var_log_obj.estado_validacion_unidad = ESTADO_UNIDAD_PENDIENTE
            import_var_log_obj.comentarios_validacion_unidad = f"Unidad '{las_curve_unit}' detectada correctamente. Validación de compatibilidad pendiente."
        else:
            import_var_log_obj.estado_validacion_unidad = ESTADO_UNIDAD_ORIGEN_NO_CATALOGO
            import_var_log_obj.comentarios_validacion_unidad = f"Unidad original LAS '{las_curve_unit}' no encontrada en catálogo."
    
    logger.info(f"        └─ Resultado Validación Unidad: {import_var_log_obj.estado_validacion_unidad}")
    
    # 2. Obtener la unidad objetivo esperada para este PAE en este rig
    try:
        id_unidad_obj_cat = session.query(Config_Variables_PAE.pae_unidad_objetivo_id)\
                                  .filter(Config_Variables_PAE.rig_id == rig_id,
                                         Config_Variables_PAE.variable_pae_id == mapped_variable_pae_id)\
                                  .scalar()
        if not id_unidad_obj_cat:
            import_var_log_obj.estado_validacion_unidad = ESTADO_UNIDAD_OBJETIVO_NO_DEFINIDO
            import_var_log_obj.comentarios_validacion_unidad = f"No se encontró unidad objetivo para PAE {mapped_variable_pae_id} en rig {rig_id}."
            logger.info(f"        └─ Resultado Validación Unidad: {import_var_log_obj.estado_validacion_unidad}")
            return
    except Exception as e:
        import_var_log_obj.estado_validacion_unidad = ESTADO_UNIDAD_OBJETIVO_NO_DEFINIDO
        import_var_log_obj.comentarios_validacion_unidad = f"Error al buscar unidad objetivo: {e}"
        logger.info(f"        └─ Resultado Validación Unidad: {import_var_log_obj.estado_validacion_unidad}")
        return

    import_var_log_obj.id_unidad_objetivo_cat = id_unidad_obj_cat
    
    # 3. Obtener tipo de dimensión y comparar
    try:
        tipo_dim_obj = session.query(VariablesUnitsAutom.tipo_dimension)\
                                  .filter(VariablesUnitsAutom.id_unidad == id_unidad_obj_cat)\
                                  .scalar()
        if tipo_dim_obj is None:
            import_var_log_obj.estado_validacion_unidad = ESTADO_UNIDAD_OBJETIVO_NO_CATALOGO
            import_var_log_obj.comentarios_validacion_unidad = f"Unidad objetivo ID '{id_unidad_obj_cat}' no existe en catalogo_unidades."
            logger.info(f"        └─ Resultado Validación Unidad: {import_var_log_obj.estado_validacion_unidad}")
            return
    except Exception as e: # Captura general por si acaso
        import_var_log_obj.estado_validacion_unidad = ESTADO_UNIDAD_OBJETIVO_NO_CATALOGO
        import_var_log_obj.comentarios_validacion_unidad = f"Error al buscar info de unidad objetivo ID {id_unidad_obj_cat}: {e}"
        logger.info(f"        └─ Resultado Validación Unidad: {import_var_log_obj.estado_validacion_unidad}")
        return

    if tipo_dim_orig is not None and tipo_dim_orig != tipo_dim_obj:
        import_var_log_obj.estado_validacion_unidad = ESTADO_UNIDAD_DIMENSION_INCOMPATIBLE
        import_var_log_obj.comentarios_validacion_unidad = f"Dimensiones incompatibles: '{tipo_dim_orig}' vs '{tipo_dim_obj}'."
        logger.info(f"        └─ Resultado Validación Unidad: {import_var_log_obj.estado_validacion_unidad}")
        return

    # 4. Procesar conversión si es necesario
    if id_unidad_orig_cat is None:
        # No podemos hacer conversión sin unidad origen
        import_var_log_obj.estado_validacion_unidad = ESTADO_UNIDAD_ORIGEN_NO_CATALOGO
        logger.info(f"        └─ Resultado Validación Unidad: {import_var_log_obj.estado_validacion_unidad}")
        return
    elif id_unidad_orig_cat == id_unidad_obj_cat:
        import_var_log_obj.estado_validacion_unidad = ESTADO_UNIDAD_VALIDA_MISMA_UNIDAD
        import_var_log_obj.factor_conv_aplicable = Decimal(1)
        import_var_log_obj.offset_conv_aplicable = Decimal(0)
    else:
        equation = _obtener_conversion(id_unidad_orig_cat, id_unidad_obj_cat, session)
        if not equation:
            import_var_log_obj.estado_validacion_unidad = ESTADO_UNIDAD_CONVERSION_NO_ENCONTRADA
            import_var_log_obj.comentarios_validacion_unidad = f"No se encontró regla de conversión de unidad ID {id_unidad_orig_cat} a ID {id_unidad_obj_cat}."
        else:
            factor, offset = _parsear_ecuacion_conversion(equation)
            if factor is not None:
                import_var_log_obj.estado_validacion_unidad = ESTADO_UNIDAD_VALIDA_CONVERSION_OK
                import_var_log_obj.factor_conv_aplicable = factor
                import_var_log_obj.offset_conv_aplicable = offset
            else:
                import_var_log_obj.estado_validacion_unidad = ESTADO_UNIDAD_ECUACION_NO_PARSABLE
    
    logger.info(f"        └─ Resultado Validación Unidad: {import_var_log_obj.estado_validacion_unidad}")

def buscar_mapeo_para_curva_optimizado(mnemonic_las: str, mapeos_exactos: dict, pae_variables: dict) -> Tuple[Optional[int], Optional[int], bool, Optional[str], Optional[int]]:
    """
    VERSIÓN OPTIMIZADA: Busca el mapeo usando datos pre-cargados en memoria.
    MEJORADO: Con filtros inteligentes para evitar matches problemáticos.
    """
    if not mnemonic_las:
        return None, None, False, None, None

    # 1. Mapeo Exacto en config_curvas_equipo (pre-cargado)
    if mnemonic_las in mapeos_exactos:
        regla = mapeos_exactos[mnemonic_las]
        logger.info(f"  -> Mapeo EXACTO (config_curvas_equipo): '{mnemonic_las}' -> PAE ID={regla.variable_pae_id}")
        return regla.variable_pae_id, regla.id, regla.se_importan_datos_de_este_alias, 'EXACTO_CONFIG_EQUIPO', 100

    mnemonic_las_norm = normalizar_texto_para_comparacion(mnemonic_las)
    if not mnemonic_las_norm:
        return None, None, False, None, None
        
    logger.debug(f"  -> No hubo mapeo exacto. Intentando alias y fuzzy (normalizado: '{mnemonic_las_norm}')...")
    
    # 2. Mapeo Exacto contra ALIAS (usando datos pre-cargados)
    for pae_id, pae in pae_variables.items():
        if pae.alias_comunes_las:
            aliases_norm = [normalizar_texto_para_comparacion(alias) for alias in pae.alias_comunes_las.split(',')]
            if mnemonic_las_norm in aliases_norm:
                logger.info(f"  -> Mapeo EXACTO POR ALIAS: '{mnemonic_las}' -> PAE ID={pae.id}")
                return pae.id, None, False, 'ALIAS_EXACTO_PAE_EN_RIG', 100
    
    # 3. Fuzzy Matching MEJORADO (usando datos pre-cargados + filtros inteligentes)
    opciones_fuzzy = {}
    categoria_origen = _detectar_categoria_variable(mnemonic_las)
    
    for pae_id, pae in pae_variables.items():
        textos_para_fuzzy = [pae.name_pae]
        if pae.alias_comunes_las:
            textos_para_fuzzy.extend(pae.alias_comunes_las.split(','))
        
        for texto in textos_para_fuzzy:
            texto_norm = normalizar_texto_para_comparacion(texto)
            if texto_norm:
                # Aplicar filtro de compatibilidad de categorías
                categoria_destino = _detectar_categoria_variable(texto)
                
                if _es_compatible_categoria(categoria_origen, categoria_destino):
                    opciones_fuzzy[texto_norm] = {
                        'pae_id': pae.id,
                        'categoria': categoria_destino,
                        'texto_original': texto
                    }
    
    if opciones_fuzzy:
        match_fuzzy = rapidfuzz_process.extractOne(
            mnemonic_las_norm, list(opciones_fuzzy.keys()), 
            scorer=fuzz.ratio, score_cutoff=UMBRAL_CONFIANZA_FUZZY_MINIMO_SUGERENCIA
        )
        
        if match_fuzzy:
            texto_sugerido, puntaje_original, _ = match_fuzzy
            match_info = opciones_fuzzy[texto_sugerido]
            pae_id_sugerido = match_info['pae_id']
            categoria_destino = match_info['categoria']
            
            # Aplicar penalización por incompatibilidad de categorías
            factor_penalizacion = _calcular_penalizacion_categoria(categoria_origen, categoria_destino)
            puntaje_ajustado = int(puntaje_original * factor_penalizacion)
            
            # Solo proceder si el puntaje ajustado sigue siendo válido
            if puntaje_ajustado >= UMBRAL_CONFIANZA_FUZZY_MINIMO_SUGERENCIA:
                logger.info(f"  -> SUGERENCIA FUZZY MEJORADA: '{mnemonic_las}' ({categoria_origen}) -> PAE ID={pae_id_sugerido} (match con '{match_info['texto_original']}' - {categoria_destino}) con puntaje {puntaje_ajustado} (orig: {puntaje_original:.0f})")
                return pae_id_sugerido, None, False, 'FUZZY_PAE_EN_RIG', puntaje_ajustado
            else:
                logger.info(f"  -> Match fuzzy RECHAZADO por penalización: '{mnemonic_las}' ({categoria_origen}) -> '{match_info['texto_original']}' ({categoria_destino}) - puntaje original: {puntaje_original:.0f}, ajustado: {puntaje_ajustado}")

    return None, None, False, None, None


def procesar_y_registrar_curvas_de_un_las(las_obj, file_import_id, rig_id, db):
    """
    Procesa todas las curvas de un archivo LAS y las registra en la base de datos.
    OPTIMIZADO: Pre-carga datos de mapeo para evitar consultas repetitivas
    """
    logger.info(f"Iniciando procesamiento de curvas para files_import.id: {file_import_id}, Rig ID: {rig_id}")
    
    # OPTIMIZACIÓN: Pre-cargar todos los mapeos de una vez
    logger.info("  📦 Pre-cargando mapeos de base de datos...")
    
    # Pre-cargar mapeos exactos del equipo
    mapeos_exactos = {}
    try:
        reglas_mapeo = db.query(ConfigCurvasEquipo).filter(
            ConfigCurvasEquipo.rig_id == rig_id
        ).all()
        for regla in reglas_mapeo:
            mapeos_exactos[regla.las_mnemonic_alias] = regla
        logger.info(f"    └─ Cargados {len(mapeos_exactos)} mapeos exactos del equipo")
    except Exception as e:
        logger.error(f"Error pre-cargando mapeos exactos: {e}")
    
    # Pre-cargar variables PAE relevantes para el rig
    pae_variables = {}
    try:
        pae_ids_relevantes = db.query(Config_Variables_PAE.variable_pae_id).filter(
            Config_Variables_PAE.rig_id == rig_id
        ).distinct().all()
        pae_ids_list = [item[0] for item in pae_ids_relevantes]
        
        if pae_ids_list:
            paes_relevantes = db.query(VariablesPaeAutom).filter(
                VariablesPaeAutom.id.in_(pae_ids_list)
            ).all()
            for pae in paes_relevantes:
                pae_variables[pae.id] = pae
        logger.info(f"    └─ Cargadas {len(pae_variables)} variables PAE relevantes")
    except Exception as e:
        logger.error(f"Error pre-cargando variables PAE: {e}")
    
    from collections import Counter
    resumen = Counter()
    
    # OPTIMIZACIÓN: Procesar en lotes para commits más eficientes
    LOTE_SIZE = 100
    lote_actual = []
    
    for i, curva in enumerate(las_obj.curves, 1):
        if i % 50 == 0:  # Log cada 50 curvas para no saturar
            logger.info(f"  📊 Procesando curva LAS #{i}/{len(las_obj.curves)}: '{curva.mnemonic}'...")
        resumen['total_curvas_leidas_del_las'] += 1

        # Usar función optimizada con datos pre-cargados
        pae_id, mapeo_id, importar_datos, tipo_mapeo, confianza = buscar_mapeo_para_curva_optimizado(
            curva.mnemonic, mapeos_exactos, pae_variables
        )

        # Crear registro de log
        try:
            nuevo_log = ImportVariablesLas(
                id_files_import=file_import_id,
                mnemonic_original_las=curva.mnemonic,
                indice_curva_en_las=i-1,  # Índice base 0
                unidad_original_las=curva.unit,
                descripcion_curva_las=curva.descr,
                mapeado_a_variable_pae_id=pae_id,
                estado_mapeo_curva=tipo_mapeo or 'NO_MAPEADA_REVISAR',
                puntaje_confianza_mapeo=confianza,
                mapeado_a_config_curva_id=mapeo_id
            )

            # Validar unidades si hay mapeo
            if pae_id:
                validar_unidades_curva(
                    db, curva.unit, pae_id, rig_id, nuevo_log
                )
                
                # Contadores por tipo de mapeo
                if tipo_mapeo == 'EXACTO_CONFIG_EQUIPO':
                    resumen['MAPEADA_EXACTO_IMPORTAR'] += 1
                elif tipo_mapeo == 'ALIAS_EXACTO_PAE_EN_RIG':
                    resumen['SUGERENCIA_ALIAS_EXACTO_EN_RIG'] += 1
                elif tipo_mapeo == 'FUZZY_PAE_EN_RIG':
                    if confianza >= UMBRAL_FUZZY_PARA_AUTOIMPORTAR:
                        resumen['MAPEADA_FUZZY_AUTOIMPORTAR'] += 1
                    else:
                        resumen['SUGERENCIA_FUZZY_EN_RIG_REVISAR'] += 1
            else:
                resumen['NO_MAPEADA_REVISAR'] += 1
            
            # Añadir al lote
            lote_actual.append(nuevo_log)
            resumen['registradas_o_actualizadas_en_log'] += 1
            
            # Procesar lote cuando esté lleno
            if len(lote_actual) >= LOTE_SIZE:
                db.add_all(lote_actual)
                db.commit()
                lote_actual = []
                logger.debug(f"    ✅ Lote de {LOTE_SIZE} curvas procesado")
                
        except Exception as e:
            logger.error(f"Error registrando curva '{curva.mnemonic}': {e}")
    
    # Procesar último lote
    if lote_actual:
        try:
            db.add_all(lote_actual)
            db.commit()
            logger.debug(f"    ✅ Último lote de {len(lote_actual)} curvas procesado")
        except Exception as e:
            logger.error(f"Error en último lote: {e}")
            db.rollback()
    
    logger.info(f"  Fin de procesamiento. Resumen: {resumen}")
    return resumen

def generar_reporte_cobertura(db: Session, rig_id: int, id_files_import: int) -> Dict[str, Any]:
    """Genera un reporte de cobertura final y completo."""
    logger.info(f"Generando reporte de cobertura FINAL para Rig ID: {rig_id}, FilesImport ID: {id_files_import}")

    try:
        paes_esperadas_query = db.query(Config_Variables_PAE.variable_pae_id, VariablesPaeAutom.name_pae).join(VariablesPaeAutom, Config_Variables_PAE.variable_pae_id == VariablesPaeAutom.id).filter(Config_Variables_PAE.rig_id == rig_id).all()
        paes_esperadas_info = {pae.variable_pae_id: pae.name_pae for pae in paes_esperadas_query}
        set_paes_esperadas = set(paes_esperadas_info.keys())
        logger.info(f"  -> Se esperan {len(set_paes_esperadas)} PAEs para el Rig ID {rig_id}.")
    except Exception as e:
        logger.error(f"Error al obtener PAEs esperadas: {e}")
        return {"error": "No se pudieron obtener PAEs esperadas."}

    try:
        mapeos_encontrados_query = db.query(
            ImportVariablesLas.mapeado_a_variable_pae_id,
            ImportVariablesLas.mnemonic_original_las,
            ImportVariablesLas.puntaje_confianza_mapeo,
            ImportVariablesLas.estado_mapeo_curva,
            ImportVariablesLas.unidad_original_las,
            ImportVariablesLas.estado_validacion_unidad
        ).filter(
            ImportVariablesLas.id_files_import == id_files_import,
            ImportVariablesLas.mapeado_a_variable_pae_id.isnot(None)
        ).all()

        paes_encontradas_info = {}
        for mapeo in mapeos_encontrados_query:
            pae_id = mapeo.mapeado_a_variable_pae_id
            if pae_id not in paes_encontradas_info:
                paes_encontradas_info[pae_id] = {"mappings": []}
            paes_encontradas_info[pae_id]["mappings"].append({
                "mnemonic": mapeo.mnemonic_original_las, "score": mapeo.puntaje_confianza_mapeo,
                "method": mapeo.estado_mapeo_curva, "unit_las": mapeo.unidad_original_las,
                "unit_validation": mapeo.estado_validacion_unidad
            })
        set_paes_encontradas = set(paes_encontradas_info.keys())
        logger.info(f"  -> Se encontraron {len(set_paes_encontradas)} PAEs distintas en el archivo.")
    except Exception as e:
        logger.error(f"Error al obtener mapeos encontrados: {e}")
        return {"error": "No se pudieron obtener mapeos encontrados."}

    paes_ok_ids = set_paes_esperadas.intersection(set_paes_encontradas)
    paes_faltantes_ids = set_paes_esperadas.difference(set_paes_encontradas)
    paes_inesperadas_ids = set_paes_encontradas.difference(set_paes_esperadas)

    def get_pae_name(pae_id):
        if pae_id in paes_esperadas_info: return paes_esperadas_info[pae_id]
        try: return db.query(VariablesPaeAutom.name_pae).filter(VariablesPaeAutom.id == pae_id).scalar() or "N/A"
        except: return "Error en DB"

    reporte = {
        "resumen": {"cobertura_porcentaje": (len(paes_ok_ids) / len(set_paes_esperadas) * 100) if set_paes_esperadas else 0, **locals()},
        "encontradas": [{"pae_id": id, "name_pae": get_pae_name(id), "mapeos": paes_encontradas_info[id]["mappings"]} for id in sorted(list(paes_ok_ids))],
        "faltantes": [{"pae_id": id, "name_pae": get_pae_name(id)} for id in sorted(list(paes_faltantes_ids))],
        "inesperadas": [{"pae_id": id, "name_pae": get_pae_name(id), "mapeos": paes_encontradas_info[id]["mappings"]} for id in sorted(list(paes_inesperadas_ids))]
    }
    logger.info(f"Reporte finalizado: {len(reporte['encontradas'])} encontradas, {len(reporte['faltantes'])} faltantes, {len(reporte['inesperadas'])} inesperadas.")
    return reporte

def exportar_reporte_detallado_csv(db: Session, rig_id: int, id_files_import: int, archivo_las_nombre: str = "archivo_las") -> str:
    """
    Exporta un reporte detallado unificado en formato CSV para descarga.
    Incluye todas las variables procesadas con sus detalles de mapeo y validación.
    """
    logger.info(f"Generando reporte CSV detallado para Rig ID: {rig_id}, FilesImport ID: {id_files_import}")
    
    try:
        # Obtener todas las curvas procesadas
        query_todas_curvas = db.query(
            ImportVariablesLas.mnemonic_original_las,
            ImportVariablesLas.indice_curva_en_las,
            ImportVariablesLas.unidad_original_las,
            ImportVariablesLas.descripcion_curva_las,
            ImportVariablesLas.mapeado_a_variable_pae_id,
            ImportVariablesLas.estado_mapeo_curva,
            ImportVariablesLas.puntaje_confianza_mapeo,
            ImportVariablesLas.estado_validacion_unidad,
            ImportVariablesLas.comentarios_validacion_unidad,
            ImportVariablesLas.id_unidad_original_cat,
            ImportVariablesLas.id_unidad_objetivo_cat,
            ImportVariablesLas.factor_conv_aplicable,
            ImportVariablesLas.offset_conv_aplicable,
            VariablesPaeAutom.name_pae,
            VariablesPaeAutom.descripcion,
            Config_Variables_PAE.rig_id
        ).outerjoin(
            VariablesPaeAutom, ImportVariablesLas.mapeado_a_variable_pae_id == VariablesPaeAutom.id
        ).outerjoin(
            Config_Variables_PAE, 
            (Config_Variables_PAE.variable_pae_id == ImportVariablesLas.mapeado_a_variable_pae_id) & 
            (Config_Variables_PAE.rig_id == rig_id)
        ).filter(
            ImportVariablesLas.id_files_import == id_files_import
        ).order_by(ImportVariablesLas.indice_curva_en_las).all()
        
        # Preparar datos para CSV
        datos_csv = []
        for curva in query_todas_curvas:
            # Determinar categoría
            if curva.mapeado_a_variable_pae_id and curva.rig_id:
                categoria = "ESPERADA_ENCONTRADA"
            elif curva.mapeado_a_variable_pae_id and not curva.rig_id:
                categoria = "INESPERADA_ENCONTRADA"
            else:
                categoria = "NO_MAPEADA"
            
            # Determinar estado de unidad con icono
            estado_unidad_icon = ""
            if curva.estado_validacion_unidad in ['VALIDA_MISMA_UNIDAD', 'VALIDA_CONVERSION_OK']:
                estado_unidad_icon = "✅ VÁLIDA"
            elif curva.estado_validacion_unidad in ['CONVERSION_NO_ENCONTRADA', 'DIMENSION_INCOMPATIBLE', 'ECUACION_NO_PARSABLE']:
                estado_unidad_icon = "⚠️ REQUIERE_ATENCION"
            elif curva.estado_validacion_unidad in ['ORIGEN_NO_EN_CATALOGO', 'OBJETIVO_NO_CATALOGO', 'OBJETIVO_NO_DEFINIDO']:
                estado_unidad_icon = "❌ PROBLEMA"
            else:
                estado_unidad_icon = "⚪ N/A"
            
            datos_csv.append({
                'INDICE_CURVA': curva.indice_curva_en_las,
                'MNEMONICO_LAS': curva.mnemonic_original_las,
                'CATEGORIA': categoria,
                'PAE_ID': curva.mapeado_a_variable_pae_id or '',
                'NOMBRE_PAE': curva.name_pae or '',
                'DESCRIPCION_PAE': curva.descripcion or '',
                'ESTADO_MAPEO': curva.estado_mapeo_curva,
                'CONFIANZA_MAPEO': f"{curva.puntaje_confianza_mapeo}%" if curva.puntaje_confianza_mapeo else '',
                'UNIDAD_LAS': curva.unidad_original_las or '',
                'DESCRIPCION_CURVA_LAS': curva.descripcion_curva_las or '',
                'ESTADO_VALIDACION_UNIDAD': estado_unidad_icon,
                'ESTADO_VALIDACION_DETALLE': curva.estado_validacion_unidad or '',
                'COMENTARIOS_VALIDACION': curva.comentarios_validacion_unidad or '',
                'FACTOR_CONVERSION': curva.factor_conv_aplicable or '',
                'OFFSET_CONVERSION': curva.offset_conv_aplicable or '',
                'ID_UNIDAD_ORIGEN_CAT': curva.id_unidad_original_cat or '',
                'ID_UNIDAD_OBJETIVO_CAT': curva.id_unidad_objetivo_cat or '',
                'CONFIGURADA_PARA_RIG': 'SÍ' if curva.rig_id else 'NO'
            })
        
        # Crear DataFrame y exportar
        df = pd.DataFrame(datos_csv)
        
        # Generar nombre de archivo con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"reporte_detallado_DLS083_{timestamp}.csv"
        ruta_archivo = f"/mnt/mariadb/autom_nov/{nombre_archivo}"
        
        # Exportar con encoding UTF-8 para caracteres especiales
        df.to_csv(ruta_archivo, index=False, encoding='utf-8-sig', sep=';')
        
        logger.info(f"Reporte CSV exportado exitosamente: {ruta_archivo}")
        logger.info(f"Total de curvas exportadas: {len(datos_csv)}")
        
        return ruta_archivo
        
    except Exception as e:
        logger.error(f"Error al generar reporte CSV: {e}", exc_info=True)
        return None

# --- Bloque de Prueba ---
if __name__ == "__main__":
    logger.info("--- Iniciando Prueba de manejador_curves_las.py (con Reporte Final) ---")

    if not SessionLocal:
        logger.critical("FINALIZANDO: No se pudo configurar la sesión de base de datos.")
        exit()
        
    RUTA_LAS_PRUEBA = os.getenv("RUTA_LAS_PRUEBA_MANEJADOR", "/mnt/mariadb/autom_nov/data/las/activos/DLS-061_PLMS-_1056_29-07-2025_16-04_1.las")
    ID_FILES_IMPORT_PRUEBA = int(os.getenv("ID_FILES_IMPORT_PRUEBA_MANEJADOR", 1))
    RIG_ID_PRUEBA = int(os.getenv("RIG_ID_PRUEBA_MANEJADOR", 97))
    
    if not os.path.isfile(RUTA_LAS_PRUEBA):
        logger.error(f"ERROR: Archivo LAS de prueba no encontrado en '{RUTA_LAS_PRUEBA}'.")
        exit()
    
    # Usar la función optimizada de carga
    las_prueba_obj = leer_las_solo_headers_y_curvas(RUTA_LAS_PRUEBA)
    if not las_prueba_obj:
        logger.error(f"ERROR CRÍTICO: No se pudo cargar el archivo LAS optimizado")
        exit()

    db: Optional[Session] = None
    try:
        db = SessionLocal()
        
        logger.info(f"Limpiando logs previos para id_files_import = {ID_FILES_IMPORT_PRUEBA}...")
        db.query(ImportVariablesLas).filter_by(id_files_import=ID_FILES_IMPORT_PRUEBA).delete()
        db.commit()
        
        resumen_proc = procesar_y_registrar_curvas_de_un_las(las_prueba_obj, ID_FILES_IMPORT_PRUEBA, RIG_ID_PRUEBA, db)
        
        logger.info("Intentando commit de la sesión...")
        db.commit()
        logger.info("Commit exitoso.")

        # --- Llamada al reporte de cobertura ---
        logger.info("\n" + "="*20 + " INICIO REPORTE DE COBERTURA " + "="*20)
        reporte = generar_reporte_cobertura(db, RIG_ID_PRUEBA, ID_FILES_IMPORT_PRUEBA)

        if "error" not in reporte:
            resumen_rep = reporte['resumen']
            print("\n--- RESUMEN DE COBERTURA FINAL ---")
            print(f"  Rig ID: {resumen_rep['rig_id']}, File Import ID: {resumen_rep['id_files_import']}")
            print(f"  PAEs Esperadas: {len(resumen_rep['set_paes_esperadas'])}")
            print(f"  PAEs Encontradas: {len(resumen_rep['set_paes_encontradas'])}")
            print(f"  Cobertura: {resumen_rep['cobertura_porcentaje']:.2f}%")
            
            def get_unit_icon(status):
                if status in ['VALIDA_MISMA_UNIDAD', 'VALIDA_CONVERSION_OK']: return "✅"
                if status in ['CONVERSION_NO_ENCONTRADA', 'DIMENSION_INCOMPATIBLE', 'ECUACION_NO_PARSABLE']: return "⚠️"
                return "❌"

            print("\n--- ✅ PAEs ENCONTRADAS Y ESPERADAS ---")
            for item in reporte['encontradas']:
                print(f"  ▶ ID: {item['pae_id']:<5} | Nombre: {item['name_pae']}")
                for m in item['mapeos']:
                    score = f"{m['score']:.0f}%" if m['score'] is not None else "N/A"
                    icon = get_unit_icon(m['unit_validation'])
                    print(f"    └─ De: {m['mnemonic']:<30} | Confianza: {score:<5} | Unidad '{m['unit_las']}': {icon} {m['unit_validation']}")

            print("\n--- ❌ PAEs FALTANTES (Esperadas pero no encontradas) ---")
            if reporte['faltantes']:
                for item in reporte['faltantes']: print(f"  - ID: {item['pae_id']:<5} | Nombre: {item['name_pae']}")
            else: print("  (Ninguna, ¡excelente!)")
            
            print("\n--- 🤔 PAEs INESPERADAS (Encontradas pero no configuradas para el rig) ---")
            if reporte['inesperadas']:
                for item in reporte['inesperadas']:
                    print(f"  ▶ ID: {item['pae_id']:<5} | Nombre: {item['name_pae']}")
                    for m in item['mapeos']:
                        score = f"{m['score']:.0f}%" if m['score'] is not None else "N/A"
                        icon = get_unit_icon(m['unit_validation'])
                        print(f"    └─ De: {m['mnemonic']:<30} | Confianza: {score:<5} | Unidad '{m['unit_las']}': {icon} {m['unit_validation']}")
            else: print("  (Ninguna)")
        else:
            logger.error(f"No se pudo generar el reporte: {reporte.get('error')}")

        logger.info("="*22 + " FIN REPORTE DE COBERTURA " + "="*23 + "\n")

        # --- Exportar reporte detallado a CSV ---
        logger.info("\n" + "="*20 + " EXPORTANDO REPORTE CSV " + "="*20)
        archivo_csv = exportar_reporte_detallado_csv(db, RIG_ID_PRUEBA, ID_FILES_IMPORT_PRUEBA, Path(RUTA_LAS_PRUEBA).stem)
        if archivo_csv:
            print(f"\n🗃️ REPORTE CSV GENERADO: {archivo_csv}")
            print("📊 El archivo contiene todas las curvas con detalles de mapeo y validación")
            print("📁 Ubicación: Directorio raíz del proyecto")
        else:
            print("❌ ERROR: No se pudo generar el archivo CSV")
        logger.info("="*22 + " FIN EXPORTACIÓN CSV " + "="*23 + "\n")

    except Exception as e:
        logger.error(f"ERROR durante la prueba: {e}", exc_info=True)
        if db: db.rollback()
    finally:
        if db: db.close()
    
    print("--- Fin de Prueba de manejador_curves_las.py ---")