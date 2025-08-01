#!/usr/bin/env python3
import os
import re
import sys
import logging
from typing import Optional, List, Tuple, Dict
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from rapidfuzz import fuzz

# ==============================
# Configuración del Logger
# ==============================
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# ==============================
# Umbrales y Constantes
# ==============================
UMBRAL_OILFIELD = 60
UMBRAL_WELL = 85

# ==============================
# Cargar Configuración .env
# ==============================
config_path = Path(__file__).resolve().parent.parent / "config.env"
if config_path.exists():
    load_dotenv(config_path)
else:
    logger.warning(f"Archivo de configuración no encontrado: {config_path}")

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = os.getenv("DB_PORT", 3306)

if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
    logger.critical("Faltan variables de entorno para la conexión a la base de datos.")
    sys.exit(1)

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# ==============================
# Modelos ORM
# ==============================
Base = declarative_base()

class Well(Base):
    __tablename__ = 'wells'
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    id_oilfield = Column(Integer)
    uwi = Column(String(50), index=True)

class Oilfield(Base):
    __tablename__ = 'oildfield'
    id = Column(Integer, primary_key=True)
    yacimiento = Column(String(255))
    codigo = Column(String(50))

# ==============================
# Funciones de Utilidad
# ==============================
def normalizar_nombre(texto: Optional[str]) -> str:
    if not texto:
        return ""
    texto = texto.upper().replace("Ñ", "N")
    texto = re.sub(r"[^\w\s\-.()\/]+", "", texto)
    texto = texto.replace("/", "-")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto

def extraer_solo_numero(texto: Optional[str]) -> Optional[str]:
    if not texto:
        return None
    m = re.search(r"(\d+)", texto)
    return m.group(1) if m else None

def extraer_componentes(nombre: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    # Patrón especial para formato "YAC.code-number" (ej: PZ.xp-1654)
    match_yac = re.search(r"([A-Z]+)\.([a-zA-Z]+)[\s\-]+(\d+)(?:[\(\s\-/]*([A-Z]))?", nombre)
    if match_yac:
        yacimiento = match_yac.group(1)
        codigo = match_yac.group(2).upper()
        numero = match_yac.group(3) 
        sufijo = match_yac.group(4)
        logger.debug(f"Patrón YAC.code detectado: yac='{yacimiento}', code='{codigo}', num='{numero}', sufijo='{sufijo}'")
        return codigo, numero, sufijo, yacimiento
    
    # Patrón original para casos simples
    match = re.search(r"([A-Z\.-]+)[\s\-]+(\d+)(?:[\(\s\-/]*([A-Z]))?", nombre)
    if match:
        codigo = match.group(1).replace("-", "").replace("(", "").replace(")", "")
        numero = match.group(2)
        sufijo = match.group(3)
        
        # SOLO dividir código de 4 caracteres si hay un sufijo explícito en paréntesis
        # o si el sufijo está claramente separado en el match original
        if len(codigo) == 4 and sufijo is None:
            # No dividir automáticamente códigos de 4 caracteres
            # Solo si hay evidencia clara de sufijo
            return codigo, numero, sufijo, None
        elif len(codigo) == 4 and sufijo:
            # Hay sufijo explícito, mantener la lógica original
            return codigo[:3], numero, codigo[3] if not sufijo else sufijo, None
        
        # Si el código es muy largo (como PAE.NQ.CASE), extraer solo la última palabra
        if len(codigo) > 6 and '.' in codigo:
            partes = codigo.split('.')
            codigo_simple = partes[-1]  # Tomar la última parte (CASE)
            logger.debug(f"Código largo detectado: '{codigo}' -> simplificado a '{codigo_simple}'")
            return codigo_simple, numero, sufijo, None
            
        return codigo, numero, sufijo, None
    
    # Patrón alternativo para nombres complejos: buscar la última palabra antes del número
    match_alt = re.search(r"([A-Z]+)[\s\-]+(\d+)(?:.*[\(]([A-Z])[\)])?.*", nombre)
    if match_alt:
        codigo = match_alt.group(1)
        numero = match_alt.group(2)
        sufijo = match_alt.group(3)
        logger.debug(f"Usando patrón alternativo: código='{codigo}', número='{numero}', sufijo='{sufijo}'")
        return codigo, numero, sufijo, None
    
    return None, None, None, None

def buscar_oilfield_candidates(session: Session, texto: Optional[str], codigo: Optional[str]) -> List[Tuple[Oilfield, int]]:
    candidatos = []
    if codigo:
        resultados = session.query(Oilfield).filter(Oilfield.codigo.ilike(codigo)).all()
        for r in resultados:
            candidatos.append((r, 100))
    if texto:
        todos = session.query(Oilfield).all()
        for r in todos:
            score = fuzz.token_sort_ratio(texto, r.yacimiento.upper())
            if score >= UMBRAL_OILFIELD:
                candidatos.append((r, score))
    vistos = set()
    unicos = []
    for o, s in sorted(candidatos, key=lambda x: x[1], reverse=True):
        if o.id not in vistos:
            vistos.add(o.id)
            unicos.append((o, s))
    return unicos

def generar_nombres_pozo(codigo: str, numero: str, sufijo: Optional[str] = None, yacimiento_prefix: Optional[str] = None) -> List[str]:
    nombres = []

    if sufijo:
        sufijos = [
            f"{numero}{sufijo}",
            f"{numero}({sufijo})",
            f"{numero} ({sufijo})"
        ]
        for suf in sufijos:
            nombres.append(f"{codigo}-{suf}")
            nombres.append(f"{codigo}.{sufijo}-{numero}")
            nombres.append(f"{codigo} {suf}")
            # Si hay prefijo de yacimiento, agregar formatos compuestos
            if yacimiento_prefix:
                nombres.append(f"{yacimiento_prefix}.{codigo.lower()}-{suf}")
                nombres.append(f"{yacimiento_prefix}.{codigo}-{suf}")
    
    # siempre agregar sin sufijo
    nombres.append(f"{codigo}-{numero}")
    nombres.append(f"{codigo} {numero}")
    
    # Si hay prefijo de yacimiento, agregar formatos compuestos
    if yacimiento_prefix:
        nombres.append(f"{yacimiento_prefix}.{codigo.lower()}-{numero}")
        nombres.append(f"{yacimiento_prefix}.{codigo}-{numero}")
        nombres.append(f"{yacimiento_prefix}.{codigo.lower()} {numero}")
        nombres.append(f"{yacimiento_prefix}.{codigo} {numero}")
    
    return list(set(nombres))

   

def buscar_well(session: Session, nombres: List[str], numero: str, oilfield_id: int) -> Optional[Well]:
    # Buscar primero en el yacimiento específico
    wells = session.query(Well).filter(Well.id_oilfield == oilfield_id).all()
    logger.debug(f"Pozos encontrados en yacimiento {oilfield_id}: {len(wells)}")
    
    # TAMBIÉN buscar pozos sin yacimiento asignado (id_oilfield = NULL)
    wells_sin_yacimiento = session.query(Well).filter(Well.id_oilfield.is_(None)).all()
    logger.debug(f"Pozos sin yacimiento asignado: {len(wells_sin_yacimiento)}")
    
    # Combinar ambas listas
    all_wells = wells + wells_sin_yacimiento
    logger.debug(f"Total de pozos a evaluar: {len(all_wells)}")
    
    mejor_pozo = None
    mejor_score = 0
    
    # Detectar si alguno de los nombres generados tiene sufijo (paréntesis o letra al final)
    tiene_sufijo_input = any('(' in n or re.search(r'[A-Z]$', n) for n in nombres)
    
    for well in all_wells:
        if extraer_solo_numero(well.name) != numero:
            logger.debug(f"Saltando pozo {well.name} - número no coincide (esperado: {numero}, obtenido: {extraer_solo_numero(well.name)})")
            continue
        
        logger.debug(f"Evaluando pozo: {well.name} (Yacimiento: {well.id_oilfield})")
            
        # Detectar si el pozo en BD tiene sufijo
        tiene_sufijo_pozo = '(' in well.name or re.search(r'[A-Z]$', well.name.replace('-', '').replace(' ', ''))
        
        for n in nombres:
            # Normalizar AMBOS nombres antes de comparar
            nombre_pozo_norm = normalizar_nombre(well.name)
            score = fuzz.token_sort_ratio(n, nombre_pozo_norm)
            logger.debug(f"  Comparando '{n}' vs '{nombre_pozo_norm}' = {score}%")
            
            if score >= UMBRAL_WELL:
                # Lógica de priorización:
                # 1. Preferir pozos del yacimiento específico sobre pozos sin yacimiento
                # 2. Si el input tiene sufijo, preferir pozos con sufijo
                # 3. Si hay empate en score, preferir el más específico
                es_mejor = False
                
                if score > mejor_score:
                    es_mejor = True
                elif score == mejor_score and mejor_pozo:
                    # En caso de empate, aplicar lógica de priorización
                    # Preferir pozos con yacimiento asignado
                    if well.id_oilfield is not None and mejor_pozo.id_oilfield is None:
                        es_mejor = True
                    elif tiene_sufijo_input and tiene_sufijo_pozo and not ('(' in mejor_pozo.name):
                        es_mejor = True  # Preferir pozo con sufijo si input tiene sufijo
                    elif tiene_sufijo_input and tiene_sufijo_pozo and len(well.name) > len(mejor_pozo.name):
                        es_mejor = True  # Preferir el nombre más específico
                
                if es_mejor:
                    mejor_pozo = well
                    mejor_score = score
                    logger.debug(f"Nuevo mejor match: {well.name} con score {score}% (sufijo: {tiene_sufijo_pozo}, yacimiento: {well.id_oilfield})")
    
    if mejor_pozo:
        logger.info(f"Mejor match encontrado: {mejor_pozo.name} (score: {mejor_score}%, yacimiento: {mejor_pozo.id_oilfield})")
    else:
        logger.debug(f"No se encontraron pozos que superen el umbral de {UMBRAL_WELL}%")
    return mejor_pozo

def identificar_pozo(nombre_las: str, uwi: Optional[str] = None) -> Optional[Well]:
    with SessionLocal() as session:
        if uwi:
            pozo = session.query(Well).filter(Well.uwi.ilike(uwi)).first()
            if pozo:
                return pozo

        nombre_norm = normalizar_nombre(nombre_las)
        codigo, numero, sufijo, yacimiento_prefix = extraer_componentes(nombre_norm)
        if not numero:
            logger.warning("No se pudo extraer número del pozo.")
            return None

        # Si tenemos un prefijo de yacimiento (como "PZ" en "PZ.xp-1654"), usar ese primero
        if yacimiento_prefix:
            logger.debug(f"Prefijo de yacimiento detectado: '{yacimiento_prefix}'")
            candidatos = buscar_oilfield_candidates(session, yacimiento_prefix, yacimiento_prefix)
        else:
            candidatos = buscar_oilfield_candidates(session, codigo, codigo)
        logger.debug(f"Candidatos de yacimiento encontrados: {len(candidatos)}")
        for oilfield, score in candidatos:
            logger.debug(f"  - {oilfield.yacimiento} (código: {oilfield.codigo}) - Score: {score}%")
            nombres_posibles = generar_nombres_pozo(oilfield.codigo or codigo, numero, sufijo, yacimiento_prefix)
            logger.debug(f"Nombres generados para búsqueda: {nombres_posibles}")
            pozo = buscar_well(session, nombres_posibles, numero, oilfield.id)
            if pozo:
                return pozo
        
        if not candidatos:
            logger.warning(f"No se encontraron yacimientos candidatos para código '{codigo}'")        
        return None

# ==============================
# Ejecución desde consola
# ==============================
if __name__ == '__main__':
    import json
    
    try:
        # Leer entrada desde stdin (para subprocess)
        entrada = input().strip()
        uwi_input = input().strip() if entrada else ""
        if not uwi_input:
            uwi_input = None
            
        if not entrada:
            resultado = {
                "exito": False,
                "mensaje": "Entrada vacía",
                "well_id": None,
                "well_name": None,
                "well_uwi": None
            }
        else:
            pozo = identificar_pozo(entrada, uwi_input)
            if pozo:
                resultado = {
                    "exito": True,
                    "mensaje": f"Pozo encontrado: {pozo.name}",
                    "well_id": pozo.id,
                    "well_name": pozo.name,
                    "well_uwi": pozo.uwi if hasattr(pozo, 'uwi') else None
                }
                logger.info(f"✅ Pozo encontrado: {pozo.name} (ID: {pozo.id})")
            else:
                resultado = {
                    "exito": False,
                    "mensaje": "Pozo no encontrado",
                    "well_id": None,
                    "well_name": None,
                    "well_uwi": None
                }
                logger.warning("⚠️ Pozo no encontrado.")
        
        # Imprimir resultado en formato JSON para subprocess
        print(f"RESULTADO:{json.dumps(resultado)}")
        
    except Exception as e:
        logger.error(f"Error en script unificado: {e}")
        resultado = {
            "exito": False,
            "mensaje": f"Error: {str(e)}",
            "well_id": None,
            "well_name": None,
            "well_uwi": None
        }
        print(f"RESULTADO:{json.dumps(resultado)}")
        sys.exit(1)
