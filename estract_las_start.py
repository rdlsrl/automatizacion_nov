import sys
import os

def get_start_date():
    """
    Busca la fecha de inicio real en el archivo de ejemplo.
    """
    file_path = "/mnt/data/DLS-061_Pcd- 925._25-02-2025_09-45_nws.las"
    data_start_index = None
    data_start_line = None
    
    # Verificar si el archivo existe
    if not os.path.exists(file_path):
        print(f"Error: El archivo {file_path} no existe.")
        return None
    
    # Leer el archivo línea por línea
    with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
        for i, line in enumerate(file):
            if line.strip().startswith("~ASCII"):
                data_start_index = i + 1  # La siguiente línea es el inicio real de los datos
                break
    
    # Si encontramos la sección de datos, leer la primera línea de datos reales
    if data_start_index is not None:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            lines = file.readlines()
            if len(lines) > data_start_index:
                data_start_line = lines[data_start_index].strip()
    
    # Extraer la fecha de la primera línea de datos
    if data_start_line:
        data_parts = data_start_line.split("\t")  # Separar por tabulaciones
        for part in data_parts:
            if "/" in part and ":" in data_parts:  # Busca un dato con formato de fecha y hora
                print(f"Fecha de inicio real de los datos: {part}")
                return part
    
    print("No se pudo encontrar la fecha de inicio real.")
    return None

if __name__ == "__main__":
    get_start_date()
