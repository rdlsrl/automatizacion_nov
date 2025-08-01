#!/usr/bin/env python3
"""
Script para crear configuraciones faltantes para el rig 97
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
DB_PORT = os.getenv('DB_PORT', '3306')
engine = create_engine(
    f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{DB_PORT}/{os.getenv('DB_NAME')}",
    echo=False
)
Session = sessionmaker(bind=engine)
session = Session()

def main():
    print("=== CREANDO CONFIGURACIONES FALTANTES PARA RIG 97 ===\n")
    
    # Mapeo de variables PAE a unidades objetivo (basado en las configuraciones existentes)
    configuraciones_base = {
        890: 10,  # Profundidad Pozo -> m
        874: 10,  # Posicion Trepano -> m  
        823: 7,   # Peso sobre Trepano -> klb
        767: 33,  # Flujo de Entrada -> L/min
        821: 7,   # Overpull -> klb
        763: 12,  # EPM Bomba 1 -> SPM
        894: 8,   # RPM Mesa Rotary -> RPM
        906: 9,   # Torque Mesa Rotary -> psi
        858: 49,  # Pileta Trip Tank 1 -> L
        859: 49,  # Pileta Trip Tank 2 -> L
        824: 49,  # Pileta Agua -> L
    }
    
    creadas = 0
    
    for variable_pae_id, unidad_objetivo_id in configuraciones_base.items():
        # Verificar si ya existe la configuración para rig 97
        existe = session.query(Config_Variables_PAE).filter(
            Config_Variables_PAE.rig_id == 97,
            Config_Variables_PAE.variable_pae_id == variable_pae_id
        ).first()
        
        if not existe:
            # Crear nueva configuración
            nueva_config = Config_Variables_PAE(
                rig_id=97,
                variable_pae_id=variable_pae_id,
                pae_unidad_objetivo_id=unidad_objetivo_id,
                descripcion_pae_objetivo=f"Configuración automática para rig 97 - Variable PAE {variable_pae_id}",
                mostrar_en_dashboard=True
            )
            session.add(nueva_config)
            creadas += 1
            
            # Obtener nombre de la variable PAE
            var_pae = session.query(VariablesPaeAutom).filter(
                VariablesPaeAutom.id == variable_pae_id
            ).first()
            
            print(f"✓ Creada configuración: {var_pae.name_pae if var_pae else f'PAE {variable_pae_id}'} -> Unidad {unidad_objetivo_id}")
        else:
            print(f"- Ya existe configuración para Variable PAE {variable_pae_id}")
    
    if creadas > 0:
        session.commit()
        print(f"\n✅ Se crearon {creadas} configuraciones nuevas para el rig 97")
    else:
        print("\n✅ Todas las configuraciones ya existían")
    
    session.close()

if __name__ == "__main__":
    main()
