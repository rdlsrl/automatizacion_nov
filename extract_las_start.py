import sys
import os

def get_start_date():
    """
    Busca la fecha y hora de inicio real en el archivo de ejemplo.
    """
    file_path = "/mnt/mariadb/autom_nov/DLS-061_Pcd- 925._25-02-2025_09-45_nws.las"
    data_start_index = None
    data_start_line = None
    
    # Verificar si el archivo existe
    if not os.path.exists(file_path):
        print(f"Error: El archivo {file_path} no existe.")
        return None
    
    # Leer el archivo línea por línea para encontrar ~ASCII DATA
    with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
        lines = file.readlines()
        for i, line in enumerate(lines):
            if line.strip().startswith("~ASCII"):
                data_start_index = i + 1  # La siguiente línea es el inicio real de los datos
                break
    
    # Si encontramos la sección de datos, leer la primera línea de datos reales
    if data_start_index is not None and data_start_index < len(lines):
        data_start_line = lines[data_start_index].strip()
    
    # Extraer la fecha y la hora de la segunda y tercera columna de la primera línea de datos
    if data_start_line:
        data_parts = data_start_line.split("\t")  # Separar por tabulaciones
        if len(data_parts) > 2:
            start_date = data_parts[1]  # La fecha está en la segunda columna
            start_time = data_parts[2]  # La hora está en la tercera columna
            print(f"Fecha y hora de inicio real de los datos: {start_date} {start_time}")
            return f"{start_date} {start_time}"
    
    print("No se pudo encontrar la fecha y hora de inicio real.")
    return None

if __name__ == "__main__":
    get_start_date()
