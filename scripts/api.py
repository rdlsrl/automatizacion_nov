import os
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional

# --- Importación de Modelos ---
try:
    from modelos_bd import Rigs, VariablesPaeAutom
except ImportError:
    print("Error: No se pudo encontrar 'modelos_bd.py' o los modelos necesarios.")
    exit()

# --- Carga de Configuración .env ---
try:
    SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = SCRIPT_DIR.parent
    CONFIG_PATH = PROJECT_ROOT / "config.env"
    load_dotenv(CONFIG_PATH)
except Exception:
    print(f"No se pudo cargar {CONFIG_PATH}, asegúrate de que el archivo existe.")
    exit()

# --- Configuración de la Base de Datos ---
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = os.getenv("DB_PORT", "3306")

DATABASE_URL = f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Esquemas Pydantic ---
class RigSchema(BaseModel):
    id: int
    name: str
    rig_type: Optional[str] = None

    class Config:
        from_attributes = True

class VariableSchema(BaseModel):
    id: int
    name_pae: str
    rdl_nombre_interno: Optional[str] = None
    categoria_pae: Optional[str] = None
    subcategoria_pae: Optional[str] = None
    activa: bool

    class Config:
        from_attributes = True

# --- Creación de la Aplicación FastAPI ---
app = FastAPI()

# --- Función para obtener la sesión de la base de datos ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Endpoints de la API ---

@app.get("/equipos", response_model=List[RigSchema])
def leer_equipos(db: Session = Depends(get_db)):
    """Devuelve una lista de todos los equipos."""
    try:
        equipos = db.query(Rigs).all()
        return equipos
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar la base de datos: {str(e)}")


@app.get("/equipos/{equipo_id}", response_model=RigSchema)
def leer_equipo(equipo_id: int, db: Session = Depends(get_db)):
    """Devuelve un equipo específico por su ID."""
    try:
        equipo = db.query(Rigs).filter(Rigs.id == equipo_id).first()
        if equipo is None:
            raise HTTPException(status_code=404, detail="Equipo no encontrado")
        return equipo
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar la base de datos: {str(e)}")


@app.get("/variables", response_model=List[VariableSchema])
def leer_variables(db: Session = Depends(get_db)):
    """Devuelve una lista de todas las variables maestras."""
    try:
        variables = db.query(VariablesPaeAutom).all()
        return variables
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar variables: {str(e)}")


@app.get("/variables/{variable_id}", response_model=VariableSchema)
def leer_variable(variable_id: int, db: Session = Depends(get_db)):
    """Devuelve una variable maestra específica por su ID."""
    try:
        variable = db.query(VariablesPaeAutom).filter(VariablesPaeAutom.id == variable_id).first()
        if variable is None:
            raise HTTPException(status_code=404, detail="Variable no encontrada")
        return variable
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar la base de datos: {str(e)}")