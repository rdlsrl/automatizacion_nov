# 🛢️ Sistema de Automatización LAS - RDL Import

## 📋 Descripción
Sistema avanzado para procesamiento automatizado de archivos LAS (Log ASCII Standard) con funcionalidades de:
- **Mapeo inteligente fuzzy** con categorización automática
- **Validación de unidades** con conversiones automáticas  
- **Análisis de cobertura** de variables PAE
- **Reportería detallada** en CSV
- **Visualizaciones** de presiones y datos

## 🚀 Características Principales

### ✨ Sistema de Categorización Inteligente
- **15+ categorías** de variables automáticas (PRESION_AIRE, FLUJO_ENTRADA, H2S_PILETA, etc.)
- **Filtros de compatibilidad** que rechazan matches incorrectos
- **Penalizaciones inteligentes** para mejorar precisión

### 📊 Mapeo Multi-nivel
1. **Mapeos exactos** de configuración
2. **Mapeos por alias** exactos
3. **Sugerencias fuzzy** con penalización por incompatibilidad

### 🔧 Archivos Principales

#### Core del Sistema
- `scripts/manejador_curves_las.py` - **Motor principal** con sistema fuzzy avanzado
- `scripts/modelos_bd.py` - Modelos SQLAlchemy de base de datos
- `automatizacion_*.py` - Scripts de automatización web

#### Análisis y Visualización
- `analisis_*.py` - Scripts de análisis avanzado
- `grafico_*.py` - Generación de visualizaciones
- `debug_*.py` - Herramientas de debugging

## 🎯 Resultados del Sistema
- **678 curvas** procesadas exitosamente
- **85.71% cobertura** de variables esperadas
- **Rechazo inteligente** de matches incorrectos (ej: AIR_PRESSURE → drawworks.pressure)
- **Aceptación precisa** de matches válidos (ej: H2S_PILETA → H2S Pileta 100%)

## 📈 Estado Actual
✅ **Sistema de categorización fuzzy completamente funcional**
✅ **Todos los imports y dependencias corregidos**
✅ **Pruebas exitosas con datos reales**
✅ **Reportería CSV implementada**

## 🔄 Próximas Mejoras Planificadas
1. **Logging avanzado** con métricas de rendimiento
2. **Sistema de caché inteligente** 
3. **Interfaz web** para gestión de mapeos
4. **Sistema de aprendizaje** ML para refinamiento continuo

## 🛠️ Tecnologías
- **Python 3.9+**
- **SQLAlchemy** - ORM
- **rapidfuzz** - Matching fuzzy optimizado
- **pandas** - Procesamiento de datos
- **lasio** - Lectura de archivos LAS
- **matplotlib/seaborn** - Visualizaciones

## 📅 Última Actualización
**1 de agosto de 2025** - Sistema de categorización fuzzy completamente implementado y funcional

---
*Desarrollado para RDL Import - Sistema de procesamiento automatizado de datos de perforación*
