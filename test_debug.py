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

# Analizar el problema
print("\n🔍 ANÁLISIS DEL PROBLEMA:")
print("Input: PAE.Nq.CASE- 337(h)")
print("BD:    CASE-337(h)")
print("El regex actual no extrae 'CASE' del nombre complejo")

# Probemos regex alternativo
import re
print("\n🔧 PROBANDO REGEX MEJORADO:")
# Buscar la última palabra antes del número
pattern_mejorado = r"([A-Z]+)[\s\-]+(\d+)(?:.*[\(]([A-Z])[\)])?.*"
match_mejorado = re.search(pattern_mejorado, nombre_norm)
if match_mejorado:
    codigo_nuevo = match_mejorado.group(1)
    numero_nuevo = match_mejorado.group(2)
    sufijo_nuevo = match_mejorado.group(3)
    print(f"✅ Regex mejorado encontró:")
    print(f"   - Código: '{codigo_nuevo}'")
    print(f"   - Número: '{numero_nuevo}'")
    print(f"   - Sufijo: '{sufijo_nuevo}'")
    
    if codigo_nuevo and numero_nuevo:
        nombres_posibles_nuevo = generar_nombres_pozo(codigo_nuevo, numero_nuevo, sufijo_nuevo)
        print(f"\n3️⃣ Nombres generados con regex mejorado:")
        for i, nombre in enumerate(nombres_posibles_nuevo, 1):
            print(f"   {i}. '{nombre}'")
            
        # Verificar match con el pozo real
        from rapidfuzz import fuzz
        pozo_real = "CASE-337(h)"
        print(f"\n🎯 Comparación con pozo real '{pozo_real}':")
        for nombre in nombres_posibles_nuevo:
            score = fuzz.token_sort_ratio(nombre, normalizar_nombre(pozo_real))
            marca = "✅" if score >= 85 else "❌"
            print(f"   {marca} '{nombre}' vs '{normalizar_nombre(pozo_real)}' = {score}%")
else:
    print("❌ Regex mejorado tampoco funciona")
