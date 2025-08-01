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

# Probar con PCH-861d
nombre_las = "PCH- 861d"
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

# Paso 3: Generar nombres posibles
if codigo and numero:
    nombres_posibles = generar_nombres_pozo(codigo, numero, sufijo)
    print(f"3️⃣ Nombres generados para búsqueda:")
    for i, nombre in enumerate(nombres_posibles, 1):
        print(f"   {i}. '{nombre}'")
else:
    print("❌ No se pudieron extraer los componentes correctamente")
    print("   Posibles problemas:")
    print("   - El formato no coincide con el patrón regex")
    print("   - El sufijo 'd' no se detecta como letra")
    print("   - Hay caracteres especiales no reconocidos")
