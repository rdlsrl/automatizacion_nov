#!/usr/bin/env python3
import os
import re
import logging
import sys
from typing import Dict, Optional, List, Tuple, Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from rapidfuzz import fuzz
from pathlib import Path

# Configuración del logger para este módulo
logger = logging.getLogger(__name__)

# ==============================
# Configuración de Constantes
# ==============================
UMBRAL_OILFIELD = 60
UMBRAL_WELL = 85

# ==============================
# Base de Datos (Carga de .env y Modelos)
# ==============================
DB_HOST_ENV = None
DB_USER_ENV = None
DB_PASSWORD_ENV = None
DB_NAME_ENV = None
DB_PORT_ENV = None

if __name__ == '__main__':
    try:
        SCRIPT_DIR_MODULE_TEST = Path(__file__).resolve().parent
        PROJECT_ROOT_MODULE_TEST = SCRIPT_DIR_MODULE_TEST.parent
    except NameError:
        SCRIPT_DIR_MODULE_TEST = Path(os.getcwd())
        PROJECT_ROOT_MODULE_TEST = SCRIPT_DIR_MODULE_TEST.parent if SCRIPT_DIR_MODULE_TEST.name.lower() == "scripts" else SCRIPT_DIR_MODULE_TEST

    config_path_module_test = PROJECT_ROOT_MODULE_TEST / "config.env"
    if config_path_module_test.exists():
        if not logging.getLogger().hasHandlers() or not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.DEBUG,
                format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
                handlers=[logging.StreamHandler(sys.stdout)]
            )
        logger.info(f"Cargando .env desde {config_path_module_test} para prueba de este módulo.")
        load_dotenv(config_path_module_test)
    else:
        if not logging.getLogger().hasHandlers():
            logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
        logger.warning(f"Archivo de configuración {config_path_module_test} no encontrado.")

    DB_HOST_ENV = os.getenv("DB_HOST")
    DB_USER_ENV = os.getenv("DB_USER")
    DB_PASSWORD_ENV = os.getenv("DB_PASSWORD")
    DB_NAME_ENV = os.getenv("DB_NAME")
    DB_PORT_ENV = os.getenv("DB_PORT", "3306")

Base = declarative_base()

class Well(Base):
    __tablename__ = 'wells'
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    id_oilfield = Column(Integer)
    uwi = Column(String(50), unique=True, nullable=True, index=True)

class Oilfield(Base):
    __tablename__ = 'oildfield' # Nombre confirmado por ti
    id = Column(Integer, primary_key=True)
    yacimiento = Column(String(255))
    codigo = Column(String(50))

# ==============================
# Funciones de Normalización y Extracción
# ==============================

def normalizar_para_extraccion(raw_name: Optional[str]) -> str:
    if raw_name is None: return ""
    if not isinstance(raw_name, str): raw_name = str(raw_name)
    
    normalized = raw_name.upper().replace("Ñ", "N")
    normalized = re.sub(r"[^\w\s\-.()]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized

def normalizar_para_comparacion(raw_name: Optional[str]) -> str:
    if raw_name is None: return ""
    if not isinstance(raw_name, str): raw_name = str(raw_name)

    normalized = raw_name.upper().replace("Ñ", "N")
    normalized = re.sub(r"[().]", " ", normalized) 
    normalized = re.sub(r"[^\w\s\-]", "", normalized)
    normalized = re.sub(r"\s*-\s*", "-", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    
    partes = normalized.split()
    if len(partes) > 1 and len(partes) % 2 == 0:
        mitad = len(partes) // 2
        if partes[:mitad] == partes[mitad:]:
            normalized = " ".join(partes[:mitad])
    return normalized

def extraer_solo_numero(texto: Optional[str]) -> Optional[str]:
    if not texto: return None
    match = re.search(r'(\d+)', str(texto))
    return match.group(1) if match else None

def extraer_componentes_y_sufijos_detallado(db_session: Session, nombre_crudo: str) -> Dict[str, Optional[str]]:
    partes = {
        "codigo_yac_base": None, "texto_yac_bruto": None, "numero_pozo": None,
        "sufijo_medio_letra": None, "sufijo_final_letra": None
    }
    if not nombre_crudo or not nombre_crudo.strip(): return partes

    nombre_norm_extr = normalizar_para_extraccion(nombre_crudo)
    logger.debug(f"Ext. Detallada - Nombre normalizado para extracción: '{nombre_norm_extr}'")

    match_ppal = re.search(r"^(.*?)(?:[\s\-]|(?=\d))(\d+)(?:[\s\(\-\/]*([A-Z]))?\.?\)?$", nombre_norm_extr)

    main_part_bruta = None
    if match_ppal:
        main_part_bruta = match_ppal.group(1).strip(" .-()")
        partes["numero_pozo"] = match_ppal.group(2)
        partes["sufijo_final_letra"] = match_ppal.group(3).upper() if match_ppal.group(3) else None
    else:
        partes["numero_pozo"] = extraer_solo_numero(nombre_norm_extr)
        if partes["numero_pozo"]:
            pos_num = nombre_norm_extr.rfind(partes["numero_pozo"])
            main_part_bruta = nombre_norm_extr[:pos_num].strip(" .-()")
        else:
            main_part_bruta = nombre_norm_extr
            logger.warning(f"No se pudo extraer número de pozo de '{nombre_norm_extr}'.")
    
    logger.debug(f"Ext. Detallada - Regex Principal -> MainPartBruta='{main_part_bruta}', Num='{partes['numero_pozo']}', SufFin='{partes['sufijo_final_letra']}'")

    if main_part_bruta:
        main_part_analisis_codigo = main_part_bruta.replace("(", "").replace(")", "").strip()
        if " " in main_part_analisis_codigo:
            codigo_compactado_cand = main_part_analisis_codigo.replace(" ", "")
            # Verificar si el código compactado es un candidato válido (2-4 caracteres, alfanumérico, no solo dígitos)
            if 2 <= len(codigo_compactado_cand) <= 4 and \
               codigo_compactado_cand.isalnum() and not codigo_compactado_cand.isdigit():
                
                logger.debug(f"Ext. Detallada - Probando código compactado: '{codigo_compactado_cand}'")
                yac_por_cod_compactado = db_session.query(Oilfield).filter(Oilfield.codigo.ilike(codigo_compactado_cand)).first()
                if yac_por_cod_compactado:
                    partes["codigo_yac_base"] = codigo_compactado_cand
                    partes["texto_yac_bruto"] = yac_por_cod_compactado.yacimiento 
                    partes["sufijo_medio_letra"] = None # Asumir que no hay sufijo medio si se usa este método
                    logger.info(f"Ext. Detallada - Encontrado por Código Compactado (de '{main_part_analisis_codigo}'): Código='{codigo_compactado_cand}', TextoYac='{partes['texto_yac_bruto']}'")
                    return partes # ¡Encontrado por código compactado, retornar inmediatamente!
         # --- INICIO DE LA MODIFICACIÓN SUGERIDA ---
        # 1. Intentar main_part_analisis_codigo como un código de yacimiento COMPLETO primero
        if len(main_part_analisis_codigo) >= 2 and len(main_part_analisis_codigo) <= 4 and \
           main_part_analisis_codigo.isalnum() and not main_part_analisis_codigo.isdigit():
            
            yac_por_cod_directo = db_session.query(Oilfield).filter(Oilfield.codigo.ilike(main_part_analisis_codigo)).first()
            if yac_por_cod_directo:
                partes["codigo_yac_base"] = main_part_analisis_codigo # Usar "PMC" completo
                partes["texto_yac_bruto"] = yac_por_cod_directo.yacimiento
                partes["sufijo_medio_letra"] = None # No hay sufijo medio si es un código completo
                logger.debug(f"Ext. Detallada - Patrón Código Directo PRIORITARIO: Código='{main_part_analisis_codigo}', TextoYac='{partes['texto_yac_bruto']}'")
                return partes # Se encontró por código completo, salir.
        # --- FIN DE LA MODIFICACIÓN SUGERIDA ---

        match_cod_suf = re.match(r"^([A-Z]{2,3})[\s\.]?([A-Z0-9])$", main_part_analisis_codigo)
        if match_cod_suf:
            cod_base_cand = match_cod_suf.group(1)
            suf_medio_cand = match_cod_suf.group(2)
            yac_por_cod_base = db_session.query(Oilfield).filter(Oilfield.codigo.ilike(cod_base_cand)).first()
            if yac_por_cod_base:
                partes["codigo_yac_base"] = cod_base_cand
                partes["sufijo_medio_letra"] = suf_medio_cand
                partes["texto_yac_bruto"] = yac_por_cod_base.yacimiento
                logger.debug(f"Ext. Detallada - Patrón COD.SUF: Código='{cod_base_cand}', SufMedio='{suf_medio_cand}', TextoYac='{partes['texto_yac_bruto']}'")
                return partes

        if len(main_part_analisis_codigo) == 4 and main_part_analisis_codigo.isalnum() and not main_part_analisis_codigo.isdigit():
            cod_3_letras = main_part_analisis_codigo[:3]
            suf_potencial = main_part_analisis_codigo[3]
            yac_por_cod_3 = db_session.query(Oilfield).filter(Oilfield.codigo.ilike(cod_3_letras)).first()
            if yac_por_cod_3:
                partes["codigo_yac_base"] = cod_3_letras
                partes["sufijo_medio_letra"] = suf_potencial
                partes["texto_yac_bruto"] = yac_por_cod_3.yacimiento
                logger.debug(f"Ext. Detallada - Patrón 3+1: Código='{cod_3_letras}', SufMedio='{suf_potencial}', TextoYac='{partes['texto_yac_bruto']}'")
                return partes
        
        if len(main_part_analisis_codigo) >= 2 and len(main_part_analisis_codigo) <= 4 and \
           main_part_analisis_codigo.isalnum() and not main_part_analisis_codigo.isdigit():
            yac_por_cod_directo = db_session.query(Oilfield).filter(Oilfield.codigo.ilike(main_part_analisis_codigo)).first()
            if yac_por_cod_directo:
                partes["codigo_yac_base"] = main_part_analisis_codigo
                partes["texto_yac_bruto"] = yac_por_cod_directo.yacimiento
                logger.debug(f"Ext. Detallada - Patrón Código Directo: Código='{main_part_analisis_codigo}', TextoYac='{partes['texto_yac_bruto']}'")
                return partes
        
        partes["texto_yac_bruto"] = main_part_bruta
        logger.debug(f"Ext. Detallada - MainPartBruta es TextoYac: '{main_part_bruta}'")

    return partes

def buscar_oilfield_candidates(db_session: Session, texto_yac_input: Optional[str], codigo_yac_input: Optional[str]) -> List[Tuple[Oilfield, int]]:
    candidates: List[Tuple[Oilfield, int]] = []
    
    if codigo_yac_input:
        found_by_code = db_session.query(Oilfield).filter(Oilfield.codigo.ilike(codigo_yac_input)).all()
        for of_code in found_by_code:
            logger.debug(f"Candidato Yac por Código ('{codigo_yac_input}'): {of_code.yacimiento} (ID:{of_code.id}) -> Score:100")
            candidates.append((of_code, 100)) 

    if texto_yac_input:
        texto_yac_norm_comp = normalizar_para_comparacion(texto_yac_input)
        if texto_yac_norm_comp:
            oilfields_all = db_session.query(Oilfield).all()
            for of_text_db in oilfields_all:
                if not of_text_db.yacimiento: continue
                nombre_yac_db_norm_comp = normalizar_para_comparacion(of_text_db.yacimiento)
                score = fuzz.token_set_ratio(texto_yac_norm_comp, nombre_yac_db_norm_comp)
                if score >= UMBRAL_OILFIELD:
                    logger.debug(f"Candidato Yac por Texto ('{texto_yac_input}' norm:'{texto_yac_norm_comp}') vs DB:'{of_text_db.yacimiento}' norm:'{nombre_yac_db_norm_comp}' (ID:{of_text_db.id}) -> Score:{score}")
                    candidates.append((of_text_db, score))
    
    final_candidates_dict: Dict[int, Tuple[Oilfield, int]] = {}
    for of, score in candidates:
        if of.id not in final_candidates_dict or score > final_candidates_dict[of.id][1]:
            final_candidates_dict[of.id] = (of, score)
            
    return sorted(final_candidates_dict.values(), key=lambda x: x[1], reverse=True)

def generar_nombres_pozo_con_sufijos(
    oilfield_obj: Optional[Oilfield],
    codigo_yac_base_extraido: Optional[str],
    texto_yac_crudo_extraido: Optional[str],
    well_number: str,
    sufijo_medio: Optional[str] = None,
    sufijo_final: Optional[str] = None
) -> List[str]:
    nombres_generados: List[str] = []
    if not well_number: return nombres_generados

    num_con_suf_final = f"{well_number}{sufijo_final if sufijo_final else ''}"

    cod_yac_efectivo = None
    if oilfield_obj and oilfield_obj.codigo and oilfield_obj.codigo.strip():
        cod_yac_efectivo = oilfield_obj.codigo.strip().upper()
    elif codigo_yac_base_extraido and codigo_yac_base_extraido.strip():
        cod_yac_efectivo = codigo_yac_base_extraido.strip().upper()

    if cod_yac_efectivo:
        if sufijo_medio:
            nombres_generados.append(f"{cod_yac_efectivo}.{sufijo_medio}-{num_con_suf_final}")
            nombres_generados.append(f"{cod_yac_efectivo}{sufijo_medio}-{num_con_suf_final}")
        else:
            nombres_generados.append(f"{cod_yac_efectivo}-{num_con_suf_final}")

    nombre_yac_a_usar = None
    if oilfield_obj and oilfield_obj.yacimiento and oilfield_obj.yacimiento.strip():
        nombre_yac_a_usar = normalizar_para_comparacion(oilfield_obj.yacimiento)
    elif texto_yac_crudo_extraido and texto_yac_crudo_extraido.strip():
        nombre_yac_a_usar = normalizar_para_comparacion(texto_yac_crudo_extraido)

    if nombre_yac_a_usar:
        nombres_generados.append(f"{nombre_yac_a_usar}-{num_con_suf_final}")
        partes_yac = nombre_yac_a_usar.split()
        if len(partes_yac) > 0:
            iniciales = "".join([p[0] for p in partes_yac if p and p[0].isalnum()])
            if iniciales and (not cod_yac_efectivo or iniciales != cod_yac_efectivo): # Usa cod_yac_efectivo definido antes
                if sufijo_medio:
                     nombres_generados.append(f"{iniciales}.{sufijo_medio}-{num_con_suf_final}")
                     nombres_generados.append(f"{iniciales}{sufijo_medio}-{num_con_suf_final}")
                else:
                    nombres_generados.append(f"{iniciales}-{num_con_suf_final}")
    
    if texto_yac_crudo_extraido and texto_yac_crudo_extraido.strip():
        norm_texto_crudo_comp = normalizar_para_comparacion(texto_yac_crudo_extraido)
        if norm_texto_crudo_comp and \
           norm_texto_crudo_comp != (cod_yac_efectivo if cod_yac_efectivo else "") and \
           norm_texto_crudo_comp != (nombre_yac_a_usar if nombre_yac_a_usar else ""):
             nombres_generados.append(f"{norm_texto_crudo_comp}-{num_con_suf_final}")

    nombres_limpios = [re.sub(r"\s*-\s*", "-", n.strip()).replace(".-", "-").replace(". -", "-") for n in nombres_generados if n]
    nombres_unicos = sorted(list(set(nombres_limpios)))
    logger.debug(f"Nombres generados para Nro:{well_number} SufM:'{sufijo_medio}' SufF:'{sufijo_final}': {nombres_unicos}")
    return nombres_unicos

def buscar_well_por_nombre_y_numero(db_session: Session, nombre_pozo_a_buscar: str, 
                                 well_number_esperado: str, oilfield_id: Optional[int] = None) -> Optional[Tuple[Well, int]]:
    query = db_session.query(Well)
    if oilfield_id is not None:
        query = query.filter(Well.id_oilfield == oilfield_id)
    
    best_match_well: Optional[Well] = None
    highest_score: int = 0
    nombre_pozo_a_buscar_norm = normalizar_para_comparacion(nombre_pozo_a_buscar)

    if not nombre_pozo_a_buscar_norm:
        logger.debug(f"Nombre a buscar '{nombre_pozo_a_buscar}' se normalizó a vacío. Saltando búsqueda.")
        return None, 0

    for well_in_db in query.all():
        if not well_in_db.name: continue
        numero_en_db = extraer_solo_numero(well_in_db.name)
        if numero_en_db != well_number_esperado:
            continue
        
        nombre_pozo_db_norm = normalizar_para_comparacion(well_in_db.name)
        if not nombre_pozo_db_norm: continue

        score = fuzz.token_set_ratio(nombre_pozo_a_buscar_norm, nombre_pozo_db_norm)
        
        logger.debug(f"Comparando (SetRatio) '{nombre_pozo_a_buscar_norm}' con DB:'{nombre_pozo_db_norm}' (PozoID:{well_in_db.id}) -> Score:{score}")
        if score >= UMBRAL_WELL and score > highest_score:
            highest_score = score
            best_match_well = well_in_db
            
    if best_match_well:
        logger.info(f"Match para '{nombre_pozo_a_buscar_norm}' (Nro:{well_number_esperado}, YacID:{oilfield_id if oilfield_id is not None else 'Any'}) -> Pozo:'{best_match_well.name}', Score:{highest_score}")
        return best_match_well, highest_score
    return None, 0

def buscar_mejor_well_consolidado(db_session: Session, nombres_posibles_pozo: List[str], 
                                  well_number: str, oilfield_id: int) -> Optional[Tuple[Well, List[Tuple[str, int]]]]:
    mejor_well_encontrado: Optional[Well] = None
    mejor_score_general: int = 0
    todos_los_matches_del_mejor_well: List[Tuple[str, int]] = []

    if not well_number or not nombres_posibles_pozo: return None

    for nombre_a_probar in nombres_posibles_pozo:
        resultado_busqueda_well = buscar_well_por_nombre_y_numero(db_session, nombre_a_probar, well_number, oilfield_id)
        if resultado_busqueda_well:
            well_match, score_match = resultado_busqueda_well
            if not mejor_well_encontrado or score_match > mejor_score_general:
                mejor_well_encontrado = well_match
                mejor_score_general = score_match
                todos_los_matches_del_mejor_well = [(nombre_a_probar, score_match)]
            elif well_match and mejor_well_encontrado and well_match.id == mejor_well_encontrado.id:
                if score_match >= UMBRAL_WELL:
                     todos_los_matches_del_mejor_well.append((nombre_a_probar, score_match))
    
    if mejor_well_encontrado:
        return mejor_well_encontrado, sorted(list(set(todos_los_matches_del_mejor_well)), key=lambda x: x[1], reverse=True)
    return None

def identificar_pozo_db(db_session: Session, nombre_crudo_las: Optional[str], uwi_las: Optional[str]) -> Optional[Well]:
    logger.info(f"Identificando pozo. UWI: '{uwi_las}', Nombre LAS: '{nombre_crudo_las}'")

    if uwi_las and uwi_las.strip():
        uwi_norm = normalizar_para_comparacion(uwi_las)
        pozo_por_uwi = db_session.query(Well).filter(Well.uwi.ilike(uwi_norm)).first()
        if pozo_por_uwi:
            logger.info(f"Pozo encontrado por UWI '{uwi_norm}': {pozo_por_uwi.name} (ID: {pozo_por_uwi.id})")
            return pozo_por_uwi
        else:
            logger.info(f"No se encontró pozo para UWI '{uwi_norm}'.")

    if not nombre_crudo_las or not nombre_crudo_las.strip():
        logger.warning("UWI no encontró/no provisto, y no hay nombre LAS para buscar.")
        return None

    partes_extraidas = extraer_componentes_y_sufijos_detallado(db_session, nombre_crudo_las)
    
    codigo_yac_base = partes_extraidas["codigo_yac_base"]
    texto_yac_bruto = partes_extraidas["texto_yac_bruto"]
    numero_pozo = partes_extraidas["numero_pozo"]
    sufijo_medio = partes_extraidas["sufijo_medio_letra"]
    sufijo_final = partes_extraidas["sufijo_final_letra"]

    logger.debug(f"Partes detalladas extraídas de '{nombre_crudo_las}': "
                 f"CodBase='{codigo_yac_base}', TxtYacBruto='{texto_yac_bruto}', Num='{numero_pozo}', "
                 f"SufMedio='{sufijo_medio}', SufFinal='{sufijo_final}'")

    if not numero_pozo:
        logger.warning(f"No se pudo extraer número de pozo de '{nombre_crudo_las}'. No se puede buscar por nombre.")
        return None

    texto_para_buscar_yac = texto_yac_bruto if texto_yac_bruto else (codigo_yac_base if not texto_yac_bruto else None)
    yac_cand_codigo = codigo_yac_base
    
    yacimientos_candidatos = buscar_oilfield_candidates(db_session, texto_para_buscar_yac, yac_cand_codigo)

    if not yacimientos_candidatos:
        # Reintento: si no hay candidatos, intentar buscar yacimiento solo con el texto_yac_bruto si no se usó antes
        if texto_yac_bruto and texto_para_buscar_yac != texto_yac_bruto :
             logger.debug(f"Reintentando búsqueda de yacimiento solo con texto_yac_bruto: '{texto_yac_bruto}'")
             yacimientos_candidatos = buscar_oilfield_candidates(db_session, texto_yac_bruto, None) # Solo texto
        
        if not yacimientos_candidatos: # Aún no hay candidatos
            logger.warning(f"No se encontraron yacimientos candidatos para '{nombre_crudo_las}'.")
            return None
    
    logger.info(f"Se encontraron {len(yacimientos_candidatos)} yacimientos candidatos. Probando...")

    for yacimiento_obj, score_yac in yacimientos_candidatos:
        logger.debug(f"Probando con Yac. Cand.: '{yacimiento_obj.yacimiento}' (ID:{yacimiento_obj.id}, Cod:{yacimiento_obj.codigo}, ScoreYac:{score_yac})")
        
        nombres_pozo_generados = generar_nombres_pozo_con_sufijos(
            yacimiento_obj, 
            codigo_yac_base,
            texto_yac_bruto,
            numero_pozo, 
            sufijo_medio, 
            sufijo_final
        )
        
        nombre_las_norm_comp = normalizar_para_comparacion(nombre_crudo_las)
        nombres_adicionales = {nombre_las_norm_comp}
        if codigo_yac_base:
            num_con_suf_final_temp = f"{numero_pozo}{sufijo_final if sufijo_final else ''}"
            if sufijo_medio:
                nombres_adicionales.add(f"{codigo_yac_base}.{sufijo_medio}-{num_con_suf_final_temp}")
                nombres_adicionales.add(f"{codigo_yac_base}{sufijo_medio}-{num_con_suf_final_temp}")
            else:
                nombres_adicionales.add(f"{codigo_yac_base}-{num_con_suf_final_temp}")
        
        if texto_yac_bruto and (not yacimiento_obj or normalizar_para_comparacion(texto_yac_bruto) != normalizar_para_comparacion(yacimiento_obj.yacimiento)):
            nombres_adicionales.add(f"{normalizar_para_comparacion(texto_yac_bruto)}-{numero_pozo}{sufijo_final if sufijo_final else ''}")

        nombres_pozo_a_probar_final = sorted(list(set(nombres_pozo_generados) | nombres_adicionales))
        if not nombres_pozo_a_probar_final and nombre_las_norm_comp:
             nombres_pozo_a_probar_final = [nombre_las_norm_comp]

        logger.debug(f"Nombres de pozo finales a probar para yac. '{yacimiento_obj.yacimiento}': {nombres_pozo_a_probar_final}")
        
        if not nombres_pozo_a_probar_final:
            logger.debug("No se generaron nombres de pozo para probar con este yacimiento.")
            continue

        resultado_busqueda = buscar_mejor_well_consolidado(db_session, nombres_pozo_a_probar_final, numero_pozo, yacimiento_obj.id)
        
        if resultado_busqueda:
            pozo_encontrado, matches_info = resultado_busqueda
            logger.info(f"¡POZO ENCONTRADO! '{pozo_encontrado.name}' (ID:{pozo_encontrado.id}, UWI:{pozo_encontrado.uwi}) "
                        f"en Yac: '{yacimiento_obj.yacimiento}' (ID:{yacimiento_obj.id})")
            for nombre_m, score_m in matches_info: 
                logger.info(f"  Match con candidato '{nombre_m}' (Score:{score_m:.2f})")
            return pozo_encontrado
        else:
            logger.debug(f"No se encontraron pozos para yac. '{yacimiento_obj.yacimiento}'.")

    logger.warning(f"No se encontró pozo para '{nombre_crudo_las}' (UWI: {uwi_las}).")
    return None

def _funcion_de_prueba_interna(db_session: Session, nombre_pozo_a_probar: Optional[str], uwi_a_probar: Optional[str] = None):
    logger.info(f"\n{'='*50}")
    msg_prueba = "Prueba Interna - "
    if nombre_pozo_a_probar: msg_prueba += f"Nombre: '{nombre_pozo_a_probar}'"
    if uwi_a_probar: msg_prueba += f"{', ' if nombre_pozo_a_probar else ''}UWI: '{uwi_a_probar}'"
    if not nombre_pozo_a_probar and not uwi_a_probar: msg_prueba += "Sin Nombre ni UWI provisto."
    logger.info(msg_prueba)

    pozo = identificar_pozo_db(db_session, nombre_pozo_a_probar, uwi_a_probar)
    
    if pozo:
        logger.info(f"RESULTADO PRUEBA: Pozo Encontrado -> ID: {pozo.id}, Nombre: {pozo.name}, UWI: {pozo.uwi}, YacID: {pozo.id_oilfield}")
        if pozo.id_oilfield:
            yacimiento_info = db_session.query(Oilfield).filter(Oilfield.id == pozo.id_oilfield).first()
            if yacimiento_info:
                logger.info(f"  Yacimiento: {yacimiento_info.yacimiento} (Código: {yacimiento_info.codigo})")
            else:
                logger.warning(f"  No se encontró info de yacimiento para id_oilfield: {pozo.id_oilfield}")
    else:
        logger.info(f"RESULTADO PRUEBA: No se encontró pozo {msg_prueba.replace('Prueba Interna - ','')}.")

if __name__ == "__main__":
    logger.info(f"--- Iniciando Pruebas de Módulo Consolidado de Búsqueda de Pozos ---")

    if not all([DB_HOST_ENV, DB_USER_ENV, DB_PASSWORD_ENV, DB_NAME_ENV]):
        logger.critical("Faltan variables de config. de BD en .env para pruebas. Saliendo.")
        sys.exit(1)

    DATABASE_URL_TEST = f"mysql+pymysql://{DB_USER_ENV}:{DB_PASSWORD_ENV}@{DB_HOST_ENV}:{DB_PORT_ENV}/{DB_NAME_ENV}"
    
    try:
        engine_test = create_engine(DATABASE_URL_TEST, echo=False) 
        # Base.metadata.create_all(bind=engine_test) # Comentado.
        SessionTest = sessionmaker(bind=engine_test)
        logger.info("Motor de BD y SessionTest creados para pruebas.")
    except Exception as e_db_setup_test:
        logger.error(f"Error CRÍTICO config. BD para prueba: {e_db_setup_test}", exc_info=True)
        sys.exit(1)

    with SessionTest() as test_session:
        try:
        
            logger.info("--- INICIANDO PRUEBAS CON CASOS DEFINIDOS ---")
            
            # Casos de prueba
            _funcion_de_prueba_interna(test_session, "PJ- 865 i", None) 
           # _funcion_de_prueba_interna(test_session, "PVM.A-1005", None) 
           #  _funcion_de_prueba_interna(test_session, "PVM A 1005", None) 
          #   _funcion_de_prueba_interna(test_session, "PVMA-1005", None) 
          #   _funcion_de_prueba_interna(test_session, "Pozo Xyz (B)-777", None) 
          #   _funcion_de_prueba_interna(test_session, "Pozo Xyz-777B", None)   
          #   _funcion_de_prueba_interna(test_session, "CHAS CM-10(A)", None) 
          #   _funcion_de_prueba_interna(test_session, "Pozo Inexistente 9999", None)
          #   _funcion_de_prueba_interna(test_session, "V/H 1204", None) # Este ya funcionó bien
           #  _funcion_de_prueba_interna(test_session, None, "5400005545") # Prueba con UWI de PVH-1476
            
            logger.info("--- FIN DE LAS PRUEBAS ---")
        except Exception as e_test_run:
            logger.error(f"Error durante la ejecución de las pruebas: {e_test_run}", exc_info=True)

