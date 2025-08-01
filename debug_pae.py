#!/usr/bin/env python3
import re
from typing import Optional, List, Tuple

# Copiar las funciones necesarias
def normalizar_nombre(texto: Optional[str]) -> str:
    if not texto:
        return ""
    texto = texto.upper().replace("Ñ", "N")
    texto = re.sub(r"[^\w\s\-.()\/]+", "", texto)
    texto = texto.replace("/", "-")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto

def extraer_componentes(nombre: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    match = re.search(r"([A-Z\.-]+)[\s\-]+(\d+)(?:[\(\s\-/]*([A-Z]))?", nombre)
    if match:
        codigo = match.group(1).replace("-", "").replace("(", "").replace(")", "")
        numero = match.group(2)
        sufijo = match.group(3)
        if len(codigo) == 4:
            return codigo[:3], numero, codigo[3]
        return codigo, numero, sufijo
    return None, None, None

def generar_nombres_pozo(codigo: str, numero: str, sufijo: Optional[str] = None) -> List[str]:
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
    # siempre agregar sin sufijo
    nombres.append(f"{codigo}-{numero}")
    nombres.append(f"{codigo} {numero}")
    return list(set(nombres))

# Probar con PAE.Nq.CASE- 337(h)
nombre_las = "PAE.Nq.CASE- 337(h)"
print(f"🔍 Analizando: '{nombre_las}'")
print("=" * 50)

# Paso 1: Normalización
nombre_norm = normalizar_nombre(nombre_las)
print(f"1️⃣ Normalizado: '{nombre_norm}'")

# Paso 2: Extracción de componentes
codigo, numero, sufijo = extraer_componentes(nombre_norm)
print(f"2️⃣ Componentes extraídos:")
print(f"   - Código: '{codigo}'")
print(f"   - Número: '{numero}'")
print(f"   - Sufijo: '{sufijo}'")

if not codigo or not numero:
    print("❌ PROBLEMA: No se pudieron extraer los componentes correctamente")
    print("🔧 ANÁLISIS DEL PATRÓN REGEX:")
    print(f"   Patrón actual: r'([A-Z\\.-]+)[\\s\\-]+(\\d+)(?:[\\(\\s\\-/]*([A-Z]))?'")
    print(f"   Texto a analizar: '{nombre_norm}'")
    
    # Analicemos paso a paso
    print("\n🔍 ANÁLISIS DETALLADO:")
    print("El nombre completo es: PAE.Nq.CASE- 337(h)")
    print("Posibles problemas:")
    print("1. 'Nq' tiene minúsculas que se normalizan a 'NQ'")
    print("2. El patrón podría no capturar 'PAE.NQ.CASE' como código")
    print("3. El sufijo 'h' está en minúsculas")
    
    # Probemos el regex manualmente
    import re
    pattern = r"([A-Z\.-]+)[\s\-]+(\d+)(?:[\(\s\-/]*([A-Z]))?"
    match = re.search(pattern, nombre_norm)
    if match:
        print(f"\n✅ Match encontrado:")
        print(f"   Grupo 1 (código): '{match.group(1)}'")
        print(f"   Grupo 2 (número): '{match.group(2)}'")
        print(f"   Grupo 3 (sufijo): '{match.group(3)}'")
    else:
        print(f"\n❌ No hay match con el patrón actual")
        
        # Probemos patrones alternativos
        print("\n🔧 PROBANDO PATRONES ALTERNATIVOS:")
        
        # Patrón más flexible
        pattern2 = r"([A-Z\.]+)[\s\-]*(\d+)(?:[\(\s\-]*([A-Z]))?.*"
        match2 = re.search(pattern2, nombre_norm)
        if match2:
            print(f"Patrón 2: ✅ '{match2.group(1)}' - '{match2.group(2)}' - '{match2.group(3)}'")
        
        # Patrón para nombres con múltiples puntos
        pattern3 = r"([A-Z\.\-]+)[\s\-]*(\d+)(?:.*[\(]([A-Z])[\)])?.*"
        match3 = re.search(pattern3, nombre_norm)
        if match3:
            print(f"Patrón 3: ✅ '{match3.group(1)}' - '{match3.group(2)}' - '{match3.group(3)}'")
else:
    # Paso 3: Generar nombres posibles
    nombres_posibles = generar_nombres_pozo(codigo, numero, sufijo)
    print(f"3️⃣ Nombres generados para búsqueda:")
    for i, nombre in enumerate(nombres_posibles, 1):
        print(f"   {i}. '{nombre}'")
        
print("\n💡 RECOMENDACIONES:")
print("1. El patrón regex actual podría necesitar mejoras para nombres complejos")
print("2. Verificar si existe un yacimiento con código similar en la BD")
print("3. Buscar pozos con número 337 en la base de datos")
