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

Base = declarative_base()

class Well(Base):
    __tablename__ = 'wells'
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    id_oilfield = Column(Integer)
    uwi = Column(String(50))

class Oilfield(Base):
    __tablename__ = 'oildfield'
    id = Column(Integer, primary_key=True)
    yacimiento = Column(String(255))
    codigo = Column(String(50))

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

def buscar_pozo_por_uwi(uwi):
    return session.query(Well).filter(Well.uwi == uwi).first()

def normalizar_entrada(nombre):
    nombre = nombre.upper().strip()
    nombre = re.sub(r"^(T/P|T-P|C/D|C-D|[A-Z]{1,2}/[A-Z]{1,2})\s+", "", nombre)
    nombre = nombre.replace("/", "-")
    nombre = re.sub(r"[^\w\s\.\-()]", "", nombre)
    nombre = re.sub(r"\s*\-\s*", "-", nombre)
    nombre = re.sub(r"\s+", " ", nombre).strip()
    nombre = re.sub(r"-+$", "", nombre)
    return nombre

def detectar_componentes(nombre):
    m = re.search(r"([A-Z\.()]+)[\s\-]+(\d+)(?:[\(\s\-\/]*([A-Z]))?\.?\)?$", nombre)
    codigo, numero, sufijo_medio_letra = None, None, None
    sufijo_final = False
    sufijo_medio = False
    if m:
        codigo = m.group(1).replace("-", "").replace("(", "").replace(")", "")
        numero = m.group(2)
        sufijo_final = bool(m.group(3))
        if len(codigo) == 4 and not session.query(Oilfield).filter(Oilfield.codigo.ilike(codigo)).first():
            sufijo_medio_letra = codigo[3]
            codigo = codigo[:3]
            sufijo_medio = True
    return codigo, numero, sufijo_medio, sufijo_medio_letra, sufijo_final

def buscar_yacimiento(yac_frag):
    yacis = session.query(Oilfield).filter(Oilfield.yacimiento.ilike(f"%{yac_frag}%")).all()
    if yacis:
        return yacis
    candidatos = []
    for o in session.query(Oilfield).all():
        score = fuzz.token_sort_ratio(yac_frag, o.yacimiento.upper())
        if score >= 80:
            candidatos.append((o, score))
    candidatos.sort(key=lambda x: x[1], reverse=True)
    return [c[0] for c in candidatos]

def buscar_codigos(codigo_input):
    encontrados = session.query(Oilfield).filter(Oilfield.codigo.ilike(codigo_input)).all()
    return [(o.codigo, o.id, o.yacimiento) for o in encontrados]

def buscar_pozo(nombre_refinado, id_oilfield):
    return session.query(Well).filter(Well.name == nombre_refinado, Well.id_oilfield == id_oilfield).first()

def buscar_pozo_like(nombre_refinado, id_oilfield):
    return session.query(Well).filter(Well.name.like(f"{nombre_refinado}%"), Well.id_oilfield == id_oilfield).first()

def buscar_pozo_general(nombre_pozo, uwi=None):
    if uwi:
        pozo = buscar_pozo_por_uwi(uwi)
        if pozo:
            return pozo

    nombre_normalizado = normalizar_entrada(nombre_pozo)
    codigo, numero, sufijo_medio, sufijo_medio_letra, sufijo_final = detectar_componentes(nombre_normalizado)

    codigos = []
    if codigo:
        codigos = buscar_codigos(codigo)

    for cod, oid, yac in codigos:
        nombre_refinado = cod
        if sufijo_medio:
            nombre_refinado += f".{sufijo_medio_letra}"
        nombre_refinado += f"-{numero}"
        pozo = buscar_pozo(nombre_refinado, oid)
        if pozo:
            return pozo
        pozo = buscar_pozo_like(nombre_refinado, oid)
        if pozo:
            return pozo

        if sufijo_medio or sufijo_final:
            patron = f"{cod}%-{numero}%"
            pozo = session.query(Well).filter(Well.name.like(patron), Well.id_oilfield == oid).first()
            if pozo:
                return pozo

    return None

if __name__ == '__main__':
    entrada = input("Ingrese nombre de pozo: ").strip()
    pozo = buscar_pozo_general(entrada)
    if pozo:
        print(f"✅ Pozo encontrado: {pozo.name} (ID: {pozo.id})")
    else:
        print("⚠️ Pozo no encontrado.")
