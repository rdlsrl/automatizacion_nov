#!/usr/bin/env python3
import sys
sys.path.append('/mnt/mariadb/autom_nov/scripts')

from import_las_autom_unificado import SessionLocal, Well

# Buscar el pozo por ID directo
print("🔍 Buscando pozo por ID 8835...")
with SessionLocal() as session:
    pozo = session.query(Well).filter(Well.id == 8835).first()
    if pozo:
        print(f"✅ Pozo encontrado:")
        print(f"  - ID: {pozo.id}")
        print(f"  - Nombre: {pozo.name}")
        print(f"  - UWI: {pozo.uwi}")
        print(f"  - ID Yacimiento: {pozo.id_oilfield}")
    else:
        print("❌ No se encontró el pozo con ID 8835")
        
    # Buscar pozos con nombre similar a PCH-861
    print("\n🔍 Buscando pozos similares a PCH-861...")
    pozos_similares = session.query(Well).filter(Well.name.like('%861%')).all()
    print(f"Encontrados {len(pozos_similares)} pozos con '861' en el nombre:")
    for p in pozos_similares:
        print(f"  - {p.name} (ID: {p.id}, Yacimiento: {p.id_oilfield})")
