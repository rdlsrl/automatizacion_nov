#!/usr/bin/env python3
"""
Script rápido para diagnosticar las variables que siguen con OBJETIVO_NO_DEFINIDO
"""

import sys
import os
from pathlib import Path

# Agregar el directorio de scripts al path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from modelos_bd import *
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Cargar configuración
PROJECT_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = PROJECT_ROOT / "config.env"
load_dotenv(CONFIG_PATH)

# Crear engine y sesión
DB_PORT = os.getenv('DB_PORT', '3306')  # Default al puerto 3306 si no está definido
engine = create_engine(
    f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{DB_PORT}/{os.getenv('DB_NAME')}",
    echo=False
)
Session = sessionmaker(bind=engine)
session = Session()

def main():
    print("=== DIAGNÓSTICO RÁPIDO: Variables OBJETIVO_NO_DEFINIDO ===\n")
    
    # Consultar las variables problemáticas
    variables_no_definidas = session.query(
        ImportVariablesLas.mnemonic_original_las,
        ImportVariablesLas.unidad_original_las,
        ImportVariablesLas.comentarios_validacion_unidad,
        VariablesPaeAutom.name_pae,
        ImportVariablesLas.mapeado_a_variable_pae_id
    ).outerjoin(
        VariablesPaeAutom, 
        ImportVariablesLas.mapeado_a_variable_pae_id == VariablesPaeAutom.id
    ).filter(
        ImportVariablesLas.estado_validacion_unidad == 'OBJETIVO_NO_DEFINIDO'
    ).all()
    
    print(f"Variables encontradas: {len(variables_no_definidas)}\n")
    
    for i, var in enumerate(variables_no_definidas, 1):
        print(f"{i:2d}. Mnemónico: {var.mnemonic_original_las}")
        print(f"    Unidad LAS: '{var.unidad_original_las}'")
        print(f"    Variable PAE: {var.name_pae}")
        print(f"    PAE ID: {var.mapeado_a_variable_pae_id}")
        print(f"    Comentarios: {var.comentarios_validacion_unidad}")
        
        # Verificar si hay configuración para esta variable PAE
        if var.mapeado_a_variable_pae_id:
            config_count = session.query(Config_Variables_PAE).filter(
                Config_Variables_PAE.variable_pae_id == var.mapeado_a_variable_pae_id
            ).count()
            print(f"    Configs encontradas: {config_count}")
            
            if config_count > 0:
                configs = session.query(Config_Variables_PAE).filter(
                    Config_Variables_PAE.variable_pae_id == var.mapeado_a_variable_pae_id
                ).all()
                for cfg in configs:
                    print(f"      - Rig: {cfg.rig_id}, Unidad objetivo: {cfg.pae_unidad_objetivo_id}")
        
        print()
    
    session.close()

if __name__ == "__main__":
    main()
