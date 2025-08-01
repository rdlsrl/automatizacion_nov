#!/usr/bin/env python3
import os
import re
import subprocess
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
from rapidfuzz import fuzz

# ==============================
# Configuración
# ==============================
EJEMPLO = "Pvm(a)- 1005"  # Cambiar para probar
UMBRAL_OILFIELD = 60
UMBRAL_WELL = 85  # Más estricto para evitar falsos positivos
LONGITUD_MIN_CODIGO = 4

# ==============================
# Base de Datos
# ==============================
load_dotenv("/mnt/mariadb/autom_nov/config.env")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = os.getenv("DB_PORT", 3306)
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

Base = declarative_base()

class Well(Base):
    __tablename__ = 'wells'
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    id_oilfield = Column(Integer)

class Oilfield(Base):
    __tablename__ = 'oildfield'
    id = Column(Integer, primary_key=True)
    yacimiento = Column(String(255))
    codigo = Column(String(50))

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

# ==============================
# Funciones Clave (Versión Mejorada)
# ==============================
def normalizar_nombre_pozo(raw_name):
    """Normaliza el nombre y maneja duplicados"""
    normalized = raw_name.upper()
    normalized = normalized.replace("Ñ", "N")
    normalized = re.sub(r"[^\w\s\-]", "", normalized)
    partes = normalized.split()
    if len(partes) % 2 == 0 and partes[:len(partes)//2] == partes[len(partes)//2:]:
        return " ".join(partes[:len(partes)//2])
    return normalized

def extraer_solo_numero(texto):
    """Extrae solo los dígitos, ignorando letras"""
    match = re.search(r'(\d+)', str(texto))
    return match.group(1) if match else None

def extraer_componentes_pozo(normalized_name):
    """Extrae código, texto y número del pozo"""
    if re.match(r'^[A-Z]{2,}-\d+$', normalized_name):
        oilfield_code, well_number = normalized_name.split('-')
        return oilfield_code, None, well_number
    
    tokens = normalized_name.split()
    if tokens and tokens[-1].isdigit():
        oilfield_text = " ".join(tokens[:-1]) if len(tokens) > 1 else None
        return None, oilfield_text, tokens[-1]
    
    return None, None, None

def buscar_oilfield_candidates(oilfield_text, extracted_code=None):
    """Busca TODOS los yacimientos posibles con sus scores"""
    candidates = []
    oilfields = session.query(Oilfield).all()
    
    if extracted_code:
        for of in oilfields:
            if of.codigo and of.codigo.upper() == extracted_code.upper():
                candidates.append((of, 100))  # Máxima prioridad a códigos exactos
    
    if oilfield_text:
        for of in oilfields:
            score = fuzz.token_sort_ratio(oilfield_text, of.yacimiento.upper())
            if score >= UMBRAL_OILFIELD:
                candidates.append((of, score))
    
    # Eliminar duplicados y ordenar por score
    seen_ids = set()
    return sorted([(of, score) for of, score in candidates if of.id not in seen_ids and not seen_ids.add(of.id)],
                 key=lambda x: x[1], reverse=True)

def generar_nombres_pozo(oilfield, well_number):
    """Genera nombres alternativos priorizando el código oficial"""
    nombres = []
    if oilfield.codigo:
        nombres.append(f"{oilfield.codigo}-{well_number}")  # Código oficial (PVH-1038)
        iniciales = "".join([p[0] for p in oilfield.yacimiento.split()])
        if iniciales.upper() != oilfield.codigo.upper():  # Evita duplicar si son iguales
            nombres.append(f"{iniciales}-{well_number}")   # Iniciales (VH-1038)
    return nombres

def buscar_well(nombre_refinado, well_number, oilfield_id=None):
    """Busca un pozo específico con número exacto"""
    query = session.query(Well)
    if oilfield_id is not None:
        query = query.filter(Well.id_oilfield == oilfield_id)
    
    for well in query.all():
        numero_pozo = extraer_solo_numero(well.name)
        if numero_pozo != well_number:
            continue
        
        well_normalizado = normalizar_nombre_pozo(well.name)
        score = fuzz.token_sort_ratio(nombre_refinado, well_normalizado)
        if score >= UMBRAL_WELL:
            return well, score
    return None, 0

def buscar_mejor_well_consolidado(nombres_posibles, well_number, oilfield_id):
    """Busca el pozo y consolida todos los matches válidos"""
    mejor_well = None
    mejores_matches = []
    
    for nombre in nombres_posibles:
        well, score = buscar_well(nombre, well_number, oilfield_id)
        if well:
            if not mejor_well or score > mejores_matches[0][1]:
                mejor_well = well
                mejores_matches = [(nombre, score)]
            elif well.id == mejor_well.id:
                mejores_matches.append((nombre, score))
    
    return mejor_well, sorted(mejores_matches, key=lambda x: x[1], reverse=True)

def procesar_ejemplo(raw_name):
    """Flujo completo de procesamiento"""
    print(f"\n{'='*50}")
    print(f"Procesando: {raw_name}")
    
    # Paso 1: Normalización
    normalized = normalizar_nombre_pozo(raw_name)
    print(f"Normalizado: {normalized}")
    
    # Paso 2: Extracción de componentes
    oilfield_code, oilfield_text, well_number = extraer_componentes_pozo(normalized)
    print(f"Componentes extraídos - Código: {oilfield_code}, Texto: {oilfield_text}, Número: {well_number}")
    
    if not well_number:
        print("¡Error! No se pudo extraer número de pozo válido")
        return
    
    # Paso 3: Búsqueda de yacimientos
    oilfield_candidates = buscar_oilfield_candidates(oilfield_text, oilfield_code)
    
    if not oilfield_candidates:
        print("No se encontraron yacimientos coincidentes")
        return
    
    print(f"\nSe encontraron {len(oilfield_candidates)} yacimientos posibles:")
    
    # Paso 4: Procesar cada yacimiento
    for oilfield, score in oilfield_candidates:
        print(f"\n• Yacimiento: {oilfield.yacimiento} (ID: {oilfield.id})")
        print(f"  Código: {oilfield.codigo}, Score: {score}")
        
        nombres_posibles = generar_nombres_pozo(oilfield, well_number)
        print(f"  Nombres propuestos: {', '.join(nombres_posibles)}")
        
        well, matches = buscar_mejor_well_consolidado(nombres_posibles, well_number, oilfield.id)
        if well:
            print(f"  → Pozo encontrado: {well.name} (ID: {well.id})")
            for nombre, match_score in matches:
                print(f"    Coincide con: {nombre} (Score: {match_score:.2f})")
        else:
            print("  → No se encontraron pozos para este yacimiento")

def procesar_con_algoritmo_mejorado(raw_name):
    """Ejecuta el algoritmo mejorado del archivo unificado usando subprocess"""
    print(f"\n{'='*50}")
    print(f"Procesando con algoritmo mejorado: {raw_name}")
    
    try:
        # Ejecutar el script unificado pasando el nombre del pozo como input
        python_path = "/mnt/mariadb/autom_nov/venv/bin/python"
        script_path = "/mnt/mariadb/autom_nov/scripts/import_las_autom_unificado.py"
        
        # Preparar el input (nombre del pozo + enter + enter para UWI vacío)
        input_data = f"{raw_name}\n\n"
        
        result = subprocess.run(
            [python_path, script_path],
            input=input_data,
            text=True,
            capture_output=True,
            cwd="/mnt/mariadb/autom_nov/scripts"
        )
        
        print("Salida del algoritmo mejorado:")
        print(result.stdout)
        
        if result.stderr:
            print("Errores:")
            print(result.stderr)
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"Error al ejecutar el algoritmo mejorado: {e}")
        return False

def ejecutar_script_unificado(raw_name):
    """Ejecuta directamente el script unificado"""
    print(f"\n{'='*50}")
    print(f"Ejecutando script unificado con: {raw_name}")
    
    try:
        python_path = "/mnt/mariadb/autom_nov/venv/bin/python"
        script_path = "/mnt/mariadb/autom_nov/scripts/import_las_autom_unificado.py"
        
        # Preparar el input
        input_data = f"{raw_name}\n\n"
        
        # Ejecutar y mostrar salida en tiempo real
        process = subprocess.Popen(
            [python_path, script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd="/mnt/mariadb/autom_nov/scripts"
        )
        
        stdout, _ = process.communicate(input=input_data)
        print(stdout)
        
        return process.returncode == 0
        
    except Exception as e:
        print(f"Error al ejecutar el script: {e}")
        return False

def main():
    # Usar el algoritmo original de este archivo
    procesar_ejemplo(EJEMPLO)
    
    # Usar el algoritmo mejorado del archivo unificado
    procesar_con_algoritmo_mejorado(EJEMPLO)
    
    # O ejecutar directamente el script
    print(f"\n{'='*50}")
    print("EJECUTANDO SCRIPT UNIFICADO DIRECTAMENTE:")
    ejecutar_script_unificado(EJEMPLO)

if __name__ == "__main__":
    main()
