#!/usr/bin/env python3
import re
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
import os
from rapidfuzz import fuzz

# ======================
# Configuración
# ======================
load_dotenv("/mnt/mariadb/autom_nov/config.env")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = os.getenv("DB_PORT", 3306)
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ======================
# Modelos
# ======================
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

# ======================
# Conexión
# ======================
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

# ======================
# Funciones
# ======================
def normalizar_entrada(nombre):
    nombre = nombre.strip()
    prefijo_match = re.match(r"^(T\/P|T\-P|C\/D|C\-D|[A-Z]{1,2}\/[A-Z]{1,2})\s+", nombre.upper())
    if prefijo_match and not re.match(r"^(V\/H|V\-H)\s+\d+", nombre.upper()):
        nombre = re.sub(r"^(T\/P|T\-P|C\/D|C\-D|[A-Z]{1,2}\/[A-Z]{1,2})\s+", "", nombre, flags=re.IGNORECASE)
    nombre = nombre.upper()
    tokens = nombre.split()
    if len(tokens) == 2 and re.match(r"^[A-Z]/[A-Z]$", tokens[0]) and re.match(r"^\d+[A-Z]?$", tokens[1]):
        tokens[0] = tokens[0].replace("/", "")
    nombre = " ".join(tokens)
    nombre = nombre.replace("/", "-")
    nombre = re.sub(r"[^\w\s\.\-()]", "", nombre)
    nombre = re.sub(r"\s*-\s*", "-", nombre)
    nombre = re.sub(r"\s+", " ", nombre).strip()
    nombre = re.sub(r"-+$", "", nombre)
    partes = nombre.split()
    if len(partes) == 2 and partes[0] == partes[1]:
        nombre = partes[0]
    numeros = re.findall(r"\b\d+\b", nombre)
    if len(numeros) == 2 and numeros[0] == numeros[1]:
        nombre = re.sub(rf"\b{numeros[1]}\b$", "", nombre).strip()
    nombre = re.sub(r"\s+[A-Z]{2,}$", "", nombre).strip()
    return nombre

def detectar_componentes(nombre):
    tokens = nombre.split()
    posibles_yac = []
    codigo = None
    numero = None
    sufijo_final = False
    sufijo_medio = False
    sufijo_medio_letra = ""
    for token in tokens:
        if re.search(r"\d", token):
            break
        posibles_yac.append(token)
    yacimiento = None
    if len("".join(posibles_yac)) > 4:
        yacimiento = posibles_yac[-1]
    m = re.search(r"([A-Z\.()]+)[\s\-]+(\d+)(?:[\(\s\-\/]*([A-Z]))?\.?\)?$", nombre)
    if m:
        codigo_completo = m.group(1).replace("-", "").replace("(", "").replace(")", "")
        numero = m.group(2)
        partes = codigo_completo.split(".")
        if len(partes) >= 4:
            codigo = partes[2]
            sufijo_medio = True
            sufijo_medio_letra = partes[3]
        elif len(partes) == 3:
            codigo = partes[2]
        elif len(partes) == 2:
            codigo = partes[0]
            sufijo_medio = True
            sufijo_medio_letra = partes[1]
        else:
            codigo = partes[0]
        if m.group(3):
            sufijo_final = True
        if len(codigo) == 4:
            existe = session.query(Oilfield).filter(Oilfield.codigo.ilike(codigo)).first()
            if not existe:
                codigo_base = codigo[:3]
                sufijo_medio = True
                sufijo_medio_letra = codigo[3]
                codigo = codigo_base
    if codigo and len(codigo) > 4:
        existe = session.query(Oilfield).filter(Oilfield.codigo.ilike(codigo)).first()
        if not existe:
            yacimiento = codigo
            codigo = None
    return yacimiento, codigo, numero, sufijo_medio, sufijo_medio_letra, sufijo_final

def buscar_yacimiento(yac_frag):
    yacis = session.query(Oilfield).filter(Oilfield.yacimiento.ilike(f"%{yac_frag}%")).all()
    if yacis:
        return yacis, False
    candidatos = []
    for o in session.query(Oilfield).all():
        score = fuzz.token_sort_ratio(yac_frag, o.yacimiento.upper())
        if score >= 80:
            candidatos.append((o, score))
    if candidatos:
        candidatos.sort(key=lambda x: x[1], reverse=True)
        print(f"⚠️ Usando fuzzy matching para yacimiento: {candidatos[0][0].yacimiento} (score: {candidatos[0][1]})")
        return [c[0] for c in candidatos], True
    return [], False

def buscar_codigos(codigo_input):
    encontrados = session.query(Oilfield).filter(Oilfield.codigo.ilike(codigo_input)).all()
    return [(o.codigo, o.id, o.yacimiento) for o in encontrados]

def buscar_pozo(nombre_refinado, id_oilfield):
    return session.query(Well).filter(Well.name == nombre_refinado, Well.id_oilfield == id_oilfield).first()

def buscar_pozo_like(nombre_refinado, id_oilfield):
    return session.query(Well).filter(Well.name.like(f"{nombre_refinado}%"), Well.id_oilfield == id_oilfield).first()

# ======================
# Ejecución principal
# ======================
entrada = input("Ingrese nombre de pozo: ").strip()
nombre = normalizar_entrada(entrada)
print(f"🧪 Nombre normalizado: {nombre}")
yac_frag, codigo_input, numero, sufijo_medio, sufijo_medio_letra, sufijo_final = detectar_componentes(nombre)
print(f"📦 Detectado -> Código: {codigo_input}, Número: {numero}, Yacimiento: {yac_frag}, Sufijo medio: {sufijo_medio_letra}, Final: {sufijo_final}")

if numero and (codigo_input or yac_frag):
    pozo_encontrado = False
    codigos = []
    fuzzy_usado = False

    if yac_frag:
        yacis, fuzzy_usado = buscar_yacimiento(yac_frag)
        if yacis:
            codigos = [(y.codigo, y.id, y.yacimiento) for y in yacis]
            if codigo_input:
                codigos.sort(key=lambda x: (x[0].upper() != codigo_input.upper(), -len(x[0])))

    if not codigos and codigo_input:
        codigos = buscar_codigos(codigo_input)

    for cod, oid, yac in codigos:
        nombre_refinado = cod
        if sufijo_medio:
            nombre_refinado += f".{sufijo_medio_letra}"
        nombre_refinado += f"-{numero}"

        pozo = buscar_pozo(nombre_refinado, oid)
        if pozo:
            print(f"✅ Pozo encontrado: {pozo.name} (ID: {pozo.id}) en yacimiento: {yac}")
            pozo_encontrado = True
            break

        pozo = buscar_pozo_like(nombre_refinado, oid)
        if pozo:
            print(f"✅ Pozo encontrado (LIKE): {pozo.name} (ID: {pozo.id}) en yacimiento: {yac}")
            pozo_encontrado = True
            break

    if not pozo_encontrado and codigo_input and len(codigo_input) <= 3 and not codigo_input.startswith("P"):
        codigo_alt = f"P{codigo_input}"
        print(f"🔁 Reintentando con código alternativo: {codigo_alt}")
        codigos = buscar_codigos(codigo_alt)
        for cod, oid, yac in codigos:
            nombre_refinado = cod
            if sufijo_medio:
                nombre_refinado += f".{sufijo_medio_letra}"
            nombre_refinado += f"-{numero}"
            pozo = buscar_pozo(nombre_refinado, oid)
            if pozo:
                print(f"✅ Pozo encontrado: {pozo.name} (ID: {pozo.id}) en yacimiento: {yac}")
                pozo_encontrado = True
                break
            pozo = buscar_pozo_like(nombre_refinado, oid)
            if pozo:
                print(f"✅ Pozo encontrado (LIKE): {pozo.name} (ID: {pozo.id}) en yacimiento: {yac}")
                pozo_encontrado = True
                break

    if not pozo_encontrado:
        print("⚠️ Pozo no encontrado con los datos provistos.")
else:
    print("❌ No se pudo interpretar el nombre del pozo.")
