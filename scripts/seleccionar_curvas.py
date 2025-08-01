# seleccion_curvas.py
import re
import logging
from typing import List, Dict, Any, Optional, Set
import lasio # Asegúrate de que lasio esté importado
from rapidfuzz import fuzz # Para el "fuzzy matching"
from sqlalchemy.orm import Session # Para type hinting si se usa con DB
from sqlalchemy import Column, Integer, String, Boolean, TEXT, DateTime, ForeignKey, Enum as SQLAlchemyEnum, func as sqlfunc # Para el bloque de prueba con DB en memoria
from sqlalchemy.ext.declarative import declarative_base # Para el bloque de prueba con DB en memoria
from sqlalchemy import create_engine # Para el bloque de prueba
from sqlalchemy.orm import sessionmaker # Para el bloque de prueba

logger = logging.getLogger(__name__)

# Configuración de constantes para la selección
UMBRAL_SIMILITUD_ALTA_DEFAULT = 90
UMBRAL_SIMILITUD_MEDIA_DEFAULT = 75
PREFIJOS_A_IGNORAR_PARA_BASE = ["DBA_", "WC_", "KZ_", "RAW_", "WSGD_", "DIR-", "GEO-"]
SUFIJOS_A_IGNORAR_PARA_BASE = ["_EST", "_CALC", "_RT", "_CORR", "_FINAL", "_PROMEDIO", "_REPROCESSED"]

def normalizar_nombre(texto: Optional[str], quitar_afijos: bool = False,
                      prefijos_a_quitar: Optional[List[str]] = None,
                      sufijos_a_quitar: Optional[List[str]] = None) -> str:
    """
    Normaliza un nombre de curva o concepto para facilitar la comparación.
    """
    if texto is None or not str(texto).strip():
        return ""
    
    norm = str(texto).upper().strip()

    if quitar_afijos:
        temp_norm = norm
        
        lista_prefijos = prefijos_a_quitar if prefijos_a_quitar is not None else PREFIJOS_A_IGNORAR_PARA_BASE
        for prefijo in lista_prefijos:
            if temp_norm.startswith(prefijo.upper()): # Asegurar que el prefijo también esté en mayúsculas para comparar
                temp_norm = temp_norm[len(prefijo):]
                break 
        
        lista_sufijos = sufijos_a_quitar if sufijos_a_quitar is not None else SUFIJOS_A_IGNORAR_PARA_BASE
        for sufijo in lista_sufijos:
            if temp_norm.endswith(sufijo.upper()): # Asegurar que el sufijo también esté en mayúsculas
                temp_norm = temp_norm[:-len(sufijo)]
                break
        norm = temp_norm.strip("_")

    norm = re.sub(r"[\s.\-/()]+", "_", norm)
    norm = re.sub(r"[^A-Z0-9_]", "", norm)
    norm = re.sub(r"_{2,}", "_", norm)
    norm = norm.strip("_")
    
    return norm

def analizar_y_mapear_curvas(
    las_file: lasio.LASFile,
    lista_conceptos_ideales_usuario: List[str],
    db_session: Session, 
    MapeosCurvasConfig_model: Any, 
    id_equipo_actual: Optional[int],
    umbral_similitud_alta: int = UMBRAL_SIMILITUD_ALTA_DEFAULT,
    umbral_similitud_media: int = UMBRAL_SIMILITUD_MEDIA_DEFAULT,
    config_seleccion: Optional[Dict[str, Any]] = None # Para pasar prefijos/sufijos personalizados
) -> Dict[str, Any]:
    """
    Analiza las curvas de un archivo LAS y las mapea a una lista de conceptos ideales.
    Utiliza una tabla de BD 'MapeosCurvasConfig' y fuzzy matching.
    Devuelve un diccionario con los mapeos, conceptos no encontrados y curvas LAS no mapeadas.
    """
    informe: Dict[str, Any] = {
        "mapeos_por_concepto_ideal": {},
        "conceptos_ideales_no_encontrados": [],
        "curvas_las_no_mapeadas_final": [] 
    }
    
    if config_seleccion is None:
        config_seleccion = {}

    prefijos_cfg = config_seleccion.get('prefijos_a_quitar', PREFIJOS_A_IGNORAR_PARA_BASE)
    sufijos_cfg = config_seleccion.get('sufijos_a_quitar', SUFIJOS_A_IGNORAR_PARA_BASE)

    if not las_file or not hasattr(las_file, 'curves'):
        logger.error("Archivo LAS inválido o sin curvas.")
        return informe

    mapeos_conocidos_bd: Dict[str, List[Dict[str, Any]]] = {}
    try:
        query_mapeos = db_session.query(MapeosCurvasConfig_model).filter(MapeosCurvasConfig_model.activo == True)
        if id_equipo_actual is not None:
            query_mapeos = query_mapeos.filter(
                (MapeosCurvasConfig_model.id_equipo == id_equipo_actual) | 
                (MapeosCurvasConfig_model.id_equipo == None) 
            )
        else:
            query_mapeos = query_mapeos.filter(MapeosCurvasConfig_model.id_equipo == None)
        
        for mapeo_db in query_mapeos.order_by(MapeosCurvasConfig_model.concepto_ideal, MapeosCurvasConfig_model.prioridad).all():
            concepto_norm_db = normalizar_nombre(mapeo_db.concepto_ideal)
            mnemonico_las_norm_db = normalizar_nombre(mapeo_db.mnemonico_las) 
            
            if concepto_norm_db not in mapeos_conocidos_bd:
                mapeos_conocidos_bd[concepto_norm_db] = []
            
            mapeos_conocidos_bd[concepto_norm_db].append({
                "mnemonico_las_config_norm": mnemonico_las_norm_db, 
                "mnemonico_las_config_orig": mapeo_db.mnemonico_las, 
                "prioridad": mapeo_db.prioridad,
                "es_especifico_equipo": mapeo_db.id_equipo is not None
            })
        logger.info(f"Cargados {sum(len(v) for v in mapeos_conocidos_bd.values())} mapeos conocidos desde BD para equipo ID: {id_equipo_actual}")
    except Exception as e_db_query:
        logger.error(f"Error al cargar mapeos conocidos desde la BD: {e_db_query}", exc_info=True)

    curvas_info_las = []
    mnemonicos_originales_en_las_set: Set[str] = set() 
    for curva_las_obj in las_file.curves:
        if curva_las_obj.mnemonic and curva_las_obj.mnemonic.strip():
            mnem_orig = curva_las_obj.mnemonic.strip()
            mnemonicos_originales_en_las_set.add(mnem_orig)
            curvas_info_las.append({
                "mnemonico_original": mnem_orig,
                "unidad": curva_las_obj.unit,
                "descripcion": curva_las_obj.descr,
                "mnemonico_normalizado_completo": normalizar_nombre(mnem_orig, quitar_afijos=False),
                "mnemonico_normalizado_base": normalizar_nombre(mnem_orig, quitar_afijos=True, prefijos_a_quitar=prefijos_cfg, sufijos_a_quitar=sufijos_cfg)
            })

    for concepto_ideal_usr in lista_conceptos_ideales_usuario:
        concepto_ideal_norm = normalizar_nombre(concepto_ideal_usr, quitar_afijos=False)
        if not concepto_ideal_norm:
            logger.warning(f"Concepto ideal del usuario '{concepto_ideal_usr}' se normalizó a vacío. Omitiendo.")
            continue
        
        informe["mapeos_por_concepto_ideal"][concepto_ideal_norm] = []
        candidatas_para_este_concepto: List[Dict[str, Any]] = []
        mnemonicos_las_ya_usados_para_este_concepto_actual: Set[str] = set()

        logger.debug(f"\nProcesando Concepto Ideal: '{concepto_ideal_usr}' (Normalizado: '{concepto_ideal_norm}')")
        
        if concepto_ideal_norm in mapeos_conocidos_bd:
            for mapeo_conocido in mapeos_conocidos_bd[concepto_ideal_norm]:
                mnemonico_config_norm = mapeo_conocido["mnemonico_las_config_norm"]
                for curva_info in curvas_info_las:
                    if curva_info["mnemonico_original"] in mnemonicos_las_ya_usados_para_este_concepto_actual:
                        continue
                    if curva_info["mnemonico_normalizado_completo"] == mnemonico_config_norm or \
                       curva_info["mnemonico_normalizado_base"] == mnemonico_config_norm:
                        detalle = {
                            "mnemonico_las_original": curva_info["mnemonico_original"],
                            "unidad_las": curva_info["unidad"],
                            "descripcion_las": curva_info["descripcion"],
                            "metodo_match": f"BD_CONFIG (Mnem LAS Config: '{mapeo_conocido['mnemonico_las_config_orig']}', Prio: {mapeo_conocido['prioridad']}, EqEsp: {mapeo_conocido['es_especifico_equipo']})",
                            "score_similitud": 100,
                            "nombre_base_detectado": curva_info["mnemonico_normalizado_base"]
                        }
                        candidatas_para_este_concepto.append(detalle)
                        mnemonicos_las_ya_usados_para_este_concepto_actual.add(curva_info["mnemonico_original"])
                        
        for curva_info in curvas_info_las:
            if curva_info["mnemonico_original"] in mnemonicos_las_ya_usados_para_este_concepto_actual:
                continue

            score_base = fuzz.token_set_ratio(concepto_ideal_norm, curva_info["mnemonico_normalizado_base"])
            score_completo = fuzz.token_set_ratio(concepto_ideal_norm, curva_info["mnemonico_normalizado_completo"])
            score_final_fuzzy = max(score_base, score_completo)

            metodo_fuzzy_desc = ""
            if score_final_fuzzy >= umbral_similitud_alta:
                metodo_fuzzy_desc = f"FUZZY_ALTA (Base: {score_base}%, Completo: {score_completo}%)"
            elif score_final_fuzzy >= umbral_similitud_media:
                metodo_fuzzy_desc = f"FUZZY_MEDIA (Base: {score_base}%, Completo: {score_completo}%)"
            
            if metodo_fuzzy_desc:
                detalle = {
                    "mnemonico_las_original": curva_info["mnemonico_original"],
                    "unidad_las": curva_info["unidad"],
                    "descripcion_las": curva_info["descripcion"],
                    "metodo_match": metodo_fuzzy_desc,
                    "score_similitud": score_final_fuzzy,
                    "nombre_base_detectado": curva_info["mnemonico_normalizado_base"]
                }
                candidatas_para_este_concepto.append(detalle)
                mnemonicos_las_ya_usados_para_este_concepto_actual.add(curva_info["mnemonico_original"])

        if candidatas_para_este_concepto:
            candidatas_para_este_concepto.sort(
                key=lambda x: (not x["metodo_match"].startswith("BD_CONFIG"), -x.get("score_similitud", 0))
            )
            informe["mapeos_por_concepto_ideal"][concepto_ideal_norm] = candidatas_para_este_concepto
            for cand in candidatas_para_este_concepto: 
                 mnemonicos_originales_en_las_set.discard(cand["mnemonico_las_original"])
        else:
            informe["conceptos_ideales_no_encontrados"].append(concepto_ideal_usr)

    for mnem_orig_restante in mnemonicos_originales_en_las_set: 
        curva_info_no_mapeada = next((c for c in curvas_info_las if c["mnemonico_original"] == mnem_orig_restante), None)
        if curva_info_no_mapeada:
            informe["curvas_las_no_mapeadas_final"].append({
                "mnemonico_las_original": curva_info_no_mapeada["mnemonico_original"],
                "unidad_las": curva_info_no_mapeada["unidad"],
                "descripcion_las": curva_info_no_mapeada["descripcion"]
            })
            
    return informe


if __name__ == '__main__':
    if not logging.getLogger().handlers: 
         logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')

    logger.info("Ejecutando pruebas para seleccion_curvas.py...")

    BaseTest = declarative_base() 
    class MapeosCurvasConfigTest(BaseTest): 
        __tablename__ = 'mapeos_curvas_config_test_table' 
        id = Column(Integer, primary_key=True)
        id_equipo = Column(Integer, nullable=True)
        concepto_ideal = Column(String)
        mnemonico_las = Column(String)
        prioridad = Column(Integer, default=1)
        activo = Column(Boolean, default=True)
    
    engine_test = create_engine("sqlite:///:memory:") 
    BaseTest.metadata.create_all(engine_test) 
    SessionTest = sessionmaker(bind=engine_test)
    test_session = SessionTest()

    mapeos_test_data_source = [
        {"id_equipo": None, "concepto_ideal": "Gamma Ray", "mnemonico_las": "GR", "prioridad": 1, "activo": True},
        {"id_equipo": None, "concepto_ideal": "Peso en el Gancho", "mnemonico_las": "HKLD", "prioridad": 1, "activo": True},
        {"id_equipo": None, "concepto_ideal": "Profundidad Principal", "mnemonico_las": "DEPT", "prioridad": 1, "activo": True},
        {"id_equipo": None, "concepto_ideal": "Tasa de Penetración", "mnemonico_las": "ROP_AVG", "prioridad": 1, "activo": True},
        {"id_equipo": None, "concepto_ideal": "Densidad Bulk", "mnemonico_las": "RHOB", "prioridad": 1, "activo": True},
    ]
    for data_row in mapeos_test_data_source:
        test_session.add(MapeosCurvasConfigTest(**data_row))
    test_session.commit()

    las_prueba = lasio.LASFile()
    las_prueba.append_curve_item(lasio.CurveItem(mnemonic='DEPT', data=[1,2,3], unit='M', descr='Profundidad'))
    las_prueba.append_curve_item(lasio.CurveItem(mnemonic='GR', data=[10,20,30], unit='GAPI', descr='Gamma Ray Bruto'))
    las_prueba.append_curve_item(lasio.CurveItem(mnemonic='Gamma_Ray_Corr', data=[11,21,31], unit='GAPI', descr='Gamma Ray Corregido'))
    las_prueba.append_curve_item(lasio.CurveItem(mnemonic='HKLD', data=[100,110,120], unit='KLB', descr='Hookload Medido'))
    las_prueba.append_curve_item(lasio.CurveItem(mnemonic='Peso Gancho LAS', data=[45,50,55], unit='TONS', descr='Peso en el Gancho del LAS'))
    las_prueba.append_curve_item(lasio.CurveItem(mnemonic='DBA_ROP_AVG', data=[5,6,7], unit='M/HR', descr='DBA Rate of Penetration Average'))
    las_prueba.append_curve_item(lasio.CurveItem(mnemonic='TEMP_BHT', data=[60,65,70], unit='DEGC', descr='Bottom Hole Temperature'))
    las_prueba.append_curve_item(lasio.CurveItem(mnemonic='CALIPER_X', data=[8.5,8.6,8.5], unit='IN', descr='Caliper X Arm'))
    las_prueba.append_curve_item(lasio.CurveItem(mnemonic='RHOB_CORR', data=[2.1,2.2,2.3], unit='G/CC', descr='Densidad Corregida'))

    conceptos_ideales_test = [
        "Profundidad Principal", 
        "Gamma Ray", 
        "Peso en el Gancho", 
        "Tasa de Penetración",
        "Temperatura de Fondo",
        "Densidad Bulk"
    ]
    
    config_prueba = {
        'umbral_similitud_alta': 85,
        'umbral_similitud_media': 70,
        'prefijos_a_quitar': ["DBA_"],
        'sufijos_a_quitar': ["_AVG", "_CORR", "_EST"]
    }

    logger.info("\n--- INICIANDO ANÁLISIS DE CURVAS (PRUEBA DE MÓDULO) ---")
    informe_resultado = analizar_y_mapear_curvas(
        las_file=las_prueba,
        lista_conceptos_ideales_usuario=conceptos_ideales_test,
        db_session=test_session,
        MapeosCurvasConfig_model=MapeosCurvasConfigTest, 
        id_equipo_actual=None, 
        umbral_similitud_alta=config_prueba['umbral_similitud_alta'],
        umbral_similitud_media=config_prueba['umbral_similitud_media'],
        config_seleccion=config_prueba
    )

    logger.info("\n--- INFORME DE MAPEO DE CURVAS (PRUEBA DE MÓDULO) ---")
    print("Mapeos Encontrados por Concepto Ideal:")
    for concepto_norm_usr, mapeos_encontrados in informe_resultado["mapeos_por_concepto_ideal"].items():
        concepto_original_display = concepto_norm_usr
        for con_orig in conceptos_ideales_test:
            if normalizar_nombre(con_orig) == concepto_norm_usr:
                concepto_original_display = con_orig
                break
        
        print(f"  Concepto Ideal: '{concepto_original_display}' (Normalizado: '{concepto_norm_usr}')")
        if mapeos_encontrados:
            for m in mapeos_encontrados:
                print(f"    - LAS: '{m['mnemonico_las_original']}' (Unidad: {m['unidad_las']}, Descr: '{m['descripcion_las']}')")
                print(f"      Método: {m['metodo_match']}, Score: {m.get('score_similitud', 'N/A')}, Base Detectada: '{m.get('nombre_base_detectado', 'N/A')}'")
            
    if informe_resultado["conceptos_ideales_no_encontrados"]:
        print("\nConceptos Ideales del Usuario NO Encontrados en el LAS (o sin match suficiente):")
        for concepto_no_enc in informe_resultado["conceptos_ideales_no_encontrados"]:
            print(f"  - {concepto_no_enc}")

    if informe_resultado["curvas_las_no_mapeadas_final"]:
        print("\nCurvas del Archivo LAS que NO fueron mapeadas a ningún Concepto Ideal:")
        for curva_no_map in informe_resultado["curvas_las_no_mapeadas_final"]:
            print(f"  - {curva_no_map['mnemonico_las_original']} (Unidad: {curva_no_map['unidad_las']}, Descr: '{curva_no_map['descripcion_las']}')")
    
    logger.info("--- FIN PRUEBAS seleccion_curvas.py ---")
    test_session.close()
    engine_test.dispose()
