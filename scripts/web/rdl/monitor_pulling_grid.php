<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Monitor Equipos Pulling - Grid Dinámico</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }

        .container {
            padding: 20px;
            max-width: 1600px;
            margin: 0 auto;
        }

        .header {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
        }

        .header h1 {
            color: #2c3e50;
            font-size: 2.5em;
            text-align: center;
            margin-bottom: 15px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
        }

        .filters-container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
        }

        .filters-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            align-items: end;
        }

        .filter-group {
            display: flex;
            flex-direction: column;
        }

        .filter-group label {
            font-weight: 600;
            color: #2c3e50;
            margin-bottom: 5px;
            font-size: 0.9em;
        }

        .filter-input {
            padding: 12px;
            border: 2px solid #e1e8ed;
            border-radius: 8px;
            font-size: 14px;
            transition: all 0.3s ease;
            background: white;
        }

        .filter-input:focus {
            border-color: #3498db;
            outline: none;
            box-shadow: 0 0 0 3px rgba(52, 152, 219, 0.1);
        }

        .btn {
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
        }

        .btn-primary {
            background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
            color: white;
        }

        .btn-success {
            background: linear-gradient(135deg, #27ae60 0%, #229954 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }

        .stats-container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }

        .stat-card {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }

        .stat-card h3 {
            font-size: 2em;
            margin-bottom: 5px;
        }

        .stat-card p {
            font-size: 0.9em;
            opacity: 0.9;
        }

        .grid-container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
        }

        .grid-header {
            background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
            color: white;
            padding: 20px;
            font-weight: 600;
            font-size: 1.2em;
        }

        .data-grid {
            overflow-x: auto;
        }

        .equipment-grid {
            display: grid;
            gap: 20px;
            padding: 20px;
        }

        .equipment-card {
            border: 2px solid #e1e8ed;
            border-radius: 12px;
            overflow: hidden;
            transition: all 0.3s ease;
            background: white;
        }

        .equipment-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            border-color: #3498db;
        }

        .equipment-header {
            background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
            color: white;
            padding: 15px 20px;
            font-weight: 600;
            font-size: 1.1em;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .status-badge {
            padding: 4px 8px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: bold;
        }

        .status-activo {
            background: #27ae60;
            color: white;
        }

        .status-alerta {
            background: #f39c12;
            color: white;
        }

        .status-inactivo {
            background: #e74c3c;
            color: white;
        }

        .days-grid {
            display: grid;
            grid-template-columns: repeat(14, 1fr);
            gap: 1px;
            background: #ecf0f1;
            margin: 15px;
            border-radius: 8px;
            overflow: hidden;
        }

        .day-cell {
            aspect-ratio: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.7em;
            font-weight: bold;
            position: relative;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .day-header {
            background: #34495e;
            color: white;
            font-size: 0.6em;
        }

        .day-with-data {
            background: #27ae60;
            color: white;
        }

        .day-no-data {
            background: #e74c3c;
            color: white;
        }

        .day-partial {
            background: #f39c12;
            color: white;
        }

        .day-cell:hover {
            transform: scale(1.1);
            z-index: 10;
        }

        .equipment-info {
            padding: 15px 20px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 10px;
            border-top: 1px solid #e1e8ed;
        }

        .info-item {
            text-align: center;
        }

        .info-label {
            font-size: 0.8em;
            color: #7f8c8d;
            margin-bottom: 2px;
        }

        .info-value {
            font-weight: 600;
            color: #2c3e50;
        }

        .wells-summary {
            padding: 15px 20px;
            border-top: 1px solid #e1e8ed;
            background: #f8f9fa;
        }

        .wells-title {
            font-weight: 600;
            color: #2c3e50;
            margin-bottom: 8px;
            font-size: 0.9em;
        }

        .wells-list {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
        }

        .well-tag {
            background: #3498db;
            color: white;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.7em;
            font-weight: 500;
        }

        .loading {
            text-align: center;
            padding: 50px;
            color: #7f8c8d;
        }

        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .tooltip {
            position: absolute;
            background: rgba(0,0,0,0.8);
            color: white;
            padding: 5px 8px;
            border-radius: 4px;
            font-size: 0.7em;
            pointer-events: none;
            z-index: 1000;
            opacity: 0;
            transition: opacity 0.3s ease;
        }

        @media (max-width: 768px) {
            .filters-grid {
                grid-template-columns: 1fr;
            }
            
            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .days-grid {
                grid-template-columns: repeat(7, 1fr);
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-cogs"></i> Monitor Equipos Pulling</h1>
            <p style="text-align: center; color: #7f8c8d; margin-top: 10px;">
                <i class="fas fa-calendar-alt"></i> Monitor diario — Últimas 2 semanas (muestra SIEMPRE hasta ayer)
            </p>
        </div>

        <div class="filters-container">
            <div class="filters-grid">
                <div class="filter-group">
                    <label for="equipoFilter"><i class="fas fa-filter"></i> Filtrar por Equipo</label>
                    <input type="text" id="equipoFilter" class="filter-input" placeholder="Nombre del equipo..." list="equiposList">
                    <datalist id="equiposList"></datalist>
                </div>
                <div class="filter-group">
                    <label for="estadoFilter"><i class="fas fa-traffic-light"></i> Estado</label>
                    <select id="estadoFilter" class="filter-input">
                        <option value="">Todos los estados</option>
                        <option value="ACTIVO">Activos</option>
                        <option value="ALERTA">En Alerta</option>
                        <option value="INACTIVO">Inactivos</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label for="diasFilter"><i class="fas fa-calendar-check"></i> Mínimo Días Activos</label>
                    <input type="number" id="diasFilter" class="filter-input" placeholder="Días..." min="0" max="14">
                </div>
                <div class="filter-group">
                    <label>&nbsp;</label>
                    <button class="btn btn-primary" onclick="aplicarFiltros()">
                        <i class="fas fa-search"></i> Filtrar
                    </button>
                </div>
                <div class="filter-group">
                    <label>&nbsp;</label>
                    <button class="btn btn-success" onclick="exportarDatos()">
                        <i class="fas fa-download"></i> Exportar
                    </button>
                </div>
            </div>
        </div>

        <div class="stats-container">
            <div class="stats-grid">
                <div class="stat-card" style="background: linear-gradient(135deg, #27ae60 0%, #229954 100%);">
                    <h3 id="totalEquipos">-</h3>
                    <p><i class="fas fa-cogs"></i> Total Equipos</p>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);">
                    <h3 id="equiposActivos">-</h3>
                    <p><i class="fas fa-check-circle"></i> Activos</p>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, #f39c12 0%, #e67e22 100%);">
                    <h3 id="equiposAlerta">-</h3>
                    <p><i class="fas fa-exclamation-triangle"></i> En Alerta</p>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);">
                    <h3 id="equiposInactivos">-</h3>
                    <p><i class="fas fa-times-circle"></i> Inactivos</p>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, #9b59b6 0%, #8e44ad 100%);">
                    <h3 id="totalPozos">-</h3>
                    <p><i class="fas fa-oil-well"></i> Total Pozos</p>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, #1abc9c 0%, #16a085 100%);">
                    <h3 id="calidadPromedio">-</h3>
                    <p><i class="fas fa-chart-line"></i> Calidad Promedio</p>
                </div>
            </div>
        </div>

        <div class="grid-container">
            <div class="grid-header">
                <i class="fas fa-th-large"></i> Grid de Equipos - Vista por Días (corte diario)
                <span style="float: right; font-size: 0.9em;">
                    <i class="fas fa-sync-alt" id="refreshIcon"></i>
                    <span id="lastUpdate">Cargando...</span> · 
                    <span id="cutoffInfo"></span>
                </span>
            </div>
            <div class="data-grid">
                <div id="equipmentGrid" class="equipment-grid">
                    <div class="loading">
                        <div class="spinner"></div>
                        <h3>Cargando datos de equipos...</h3>
                        <p>Obteniendo información de las últimas 2 semanas</p>
                    </div>
                </div>
                <div style="display:flex; gap:15px; align-items:center; padding:10px 20px; background:#f8fafc; color:#34495e; border-top:1px solid #e1e8ed; font-size:0.9em;">
                    <span><span style="width:10px; height:10px; border-radius:50%; background:#27ae60; display:inline-block; margin-right:6px;"></span> OK (calidad ≥ 80% y sin alertas)</span>
                    <span><span style="width:10px; height:10px; border-radius:50%; background:#f39c12; display:inline-block; margin-right:6px;"></span> Alerta (variables con problema o calidad intermedia)</span>
                    <span><span style="width:10px; height:10px; border-radius:50%; background:#e74c3c; display:inline-block; margin-right:6px;"></span> Sin datos</span>
                    <span style="margin-left:auto; color:#7f8c8d;"><i class="fas fa-info-circle"></i> "Horas" = suma por variable×pozo; usar % y alertas para interpretar.</span>
                </div>
            </div>
        </div>
    </div>

    <div class="tooltip" id="tooltip"></div>

    <!-- Modal Detalle por Día -->
    <div id="modalBackdrop" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.5); z-index:2000; align-items:center; justify-content:center;">
        <div id="dayModal" style="width: min(960px, 95vw); max-height: 90vh; overflow:auto; background:#fff; border-radius:12px; box-shadow:0 20px 60px rgba(0,0,0,0.3);">
            <div style="display:flex; justify-content:space-between; align-items:center; padding:14px 18px; background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%); color:#fff;">
                <div id="modalTitle" style="font-weight:700;">Detalle del día</div>
                <button onclick="closeModal()" style="background:transparent; border:none; color:#fff; font-size:20px; cursor:pointer;">✕</button>
            </div>
            <div style="padding:16px;">
                <div id="modalFilters" style="display:flex; gap:10px; align-items:center; margin-bottom:10px;">
                    <label><input type="checkbox" id="onlyRequiredChk"> Solo requeridas</label>
                    <label>Presente ≥ <input type="number" id="presentMinInp" value="90" min="0" max="100" step="1" style="width:70px;"> %</label>
                    <label>En rango ≥ <input type="number" id="rangeMinInp" value="85" min="0" max="100" step="1" style="width:70px;"> %</label>
                    <button class="btn btn-primary" onclick="reloadDayDetails()"><i class="fas fa-sync"></i> Actualizar</button>
                </div>
                <div id="daySummary" style="margin-bottom:10px; color:#7f8c8d;"></div>
                <div style="overflow:auto;">
                    <table id="dayTable" style="width:100%; border-collapse:collapse;">
                        <thead>
                            <tr>
                                <th style="text-align:left; padding:8px; background:#f0f3f6;">Variable</th>
                                <th style="text-align:left; padding:8px; background:#f0f3f6;">Unidad</th>
                                <th style="text-align:left; padding:8px; background:#f0f3f6;">Tipo</th>
                                <th style="text-align:right; padding:8px; background:#f0f3f6;">Horas</th>
                                <th style="text-align:right; padding:8px; background:#f0f3f6;">% Presente</th>
                                <th style="text-align:right; padding:8px; background:#f0f3f6;">% En rango</th>
                                <th style="text-align:right; padding:8px; background:#f0f3f6;">% Nulos</th>
                                <th style="text-align:left; padding:8px; background:#f0f3f6;">Pozos</th>
                                <th style="text-align:center; padding:8px; background:#f0f3f6;">Alerta</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script>
    let equiposData = [];
    let equiposOriginal = [];
    let baseDate = new Date(); // se ajusta con el valor del API (max_date)
    let apiThresholds = { present_min: 90, range_min: 85 };

        // Cargar datos al iniciar
        document.addEventListener('DOMContentLoaded', function() {
            cargarDatos();
            
            // Auto-refresh cada 5 minutos
            setInterval(cargarDatos, 300000);
            
            // Eventos de filtros
            document.getElementById('equipoFilter').addEventListener('input', aplicarFiltros);
            document.getElementById('estadoFilter').addEventListener('change', aplicarFiltros);
            document.getElementById('diasFilter').addEventListener('input', aplicarFiltros);
        });

        async function cargarDatos() {
            try {
                document.getElementById('refreshIcon').style.animation = 'spin 1s linear infinite';
                
                // Corte diario: API devuelve SIEMPRE hasta ayer
                const response = await fetch('api_monitor_pulling.php');
                const data = await response.json();
                
                equiposOriginal = data.equipos;
                equiposData = [...equiposOriginal];
                apiThresholds.present_min = data.present_min ?? 90;
                apiThresholds.range_min = data.range_min ?? 85;
                // Ajustar fecha base con la fecha tope del API (si existe)
                if (data.max_date) {
                    baseDate = new Date(data.max_date);
                }
                
                actualizarEstadisticas(data.estadisticas);
                renderizarGrid();
                // autocomplete de equipos
                const dl = document.getElementById('equiposList');
                if (dl) {
                    dl.innerHTML = equiposOriginal.map(e => `<option value="${e.nombre}"></option>`).join('');
                }
                
                document.getElementById('lastUpdate').textContent = 
                    'Última actualización: ' + new Date().toLocaleTimeString();
                document.getElementById('cutoffInfo').textContent = 
                    `Corte: ${baseDate.toLocaleDateString()} · Umbrales: Presente ≥ ${apiThresholds.present_min}% · En rango ≥ ${apiThresholds.range_min}%`;
                
            } catch (error) {
                console.error('Error al cargar datos:', error);
                document.getElementById('equipmentGrid').innerHTML = `
                    <div class="loading">
                        <i class="fas fa-exclamation-triangle" style="font-size: 3em; color: #e74c3c; margin-bottom: 20px;"></i>
                        <h3>Error al cargar datos</h3>
                        <p>No se pudieron obtener los datos de equipos</p>
                        <button class="btn btn-primary" onclick="cargarDatos()">
                            <i class="fas fa-redo"></i> Reintentar
                        </button>
                    </div>
                `;
            } finally {
                document.getElementById('refreshIcon').style.animation = '';
            }
        }

        function actualizarEstadisticas(stats) {
            document.getElementById('totalEquipos').textContent = stats.total_equipos ?? '-';
            document.getElementById('equiposActivos').textContent = stats.activos ?? '-';
            document.getElementById('equiposAlerta').textContent = stats.alerta ?? '-';
            document.getElementById('equiposInactivos').textContent = stats.inactivos ?? '-';
            document.getElementById('totalPozos').textContent = stats.total_pozos ?? '-';
            const cp = (stats.calidad_promedio !== undefined) ? stats.calidad_promedio : '-';
            document.getElementById('calidadPromedio').textContent = (cp === '-') ? '-' : (cp + '%');
        }

        function renderizarGrid() {
            const container = document.getElementById('equipmentGrid');
            
            if (equiposData.length === 0) {
                container.innerHTML = `
                    <div class="loading">
                        <i class="fas fa-search" style="font-size: 3em; color: #7f8c8d; margin-bottom: 20px;"></i>
                        <h3>No se encontraron equipos</h3>
                        <p>Intenta ajustar los filtros de búsqueda</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = equiposData.map(equipo => `
                <div class="equipment-card">
                    <div class="equipment-header">
                        <span><i class="fas fa-cog"></i> ${equipo.nombre}</span>
                        <span class="status-badge status-${equipo.estado.toLowerCase()}">
                            ${equipo.estado} (${equipo.porcentaje_calidad}% calidad)
                        </span>
                    </div>
                    
                    <div class="days-grid">
                        ${generarHeaderDias()}
                        ${generarCeldasDias(equipo.actividad_diaria)}
                    </div>
                    
                    <div class="equipment-info">
                        <div class="info-item">
                            <div class="info-label">Pozos Trabajados</div>
                            <div class="info-value">${equipo.pozos_trabajados}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Variables Monitor.</div>
                            <div class="info-value">${equipo.variables_monitoreadas}</div>
                        </div>
                        <div class="info-item" title="Suma de horas por variable×pozo (puede superar 24)">
                            <div class="info-label">Horas (var×pozo)</div>
                            <div class="info-value">${Math.round(equipo.total_horas_monitoreadas || 0)}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Días con Eventos</div>
                            <div class="info-value">${(equipo.dias_con_eventos ?? 0)}/14</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Calidad de Datos</div>
                            <div class="info-value" style="color: ${equipo.porcentaje_calidad >= 80 ? '#27ae60' : equipo.porcentaje_calidad >= 60 ? '#f39c12' : '#e74c3c'}">${(equipo.porcentaje_calidad ?? 0)}%</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Última Actividad</div>
                            <div class="info-value">${(equipo.ultima_fecha ?? '-')}</div>
                        </div>
                    </div>
                    
                    <div class="wells-summary">
                        <div class="wells-title">
                            <i class="fas fa-oil-well"></i> 
                            Pozos Recientes (${equipo.pozos_detalle.length}) - Última Semana
                        </div>
                        <div style="max-height: 120px; overflow-y: auto;">
                            ${equipo.pozos_detalle.map(pozo => `
                                <div style="display: flex; justify-content: space-between; align-items: center; padding: 5px 0; border-bottom: 1px solid #eee;">
                                    <span style="font-weight: 600;">${pozo.pozo}</span>
                                    <div style="font-size: 0.8em; color: #7f8c8d;">
                                        ${pozo.variables} vars | ${Math.round(pozo.total_horas)}h | ${pozo.calidad}% calidad
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                    
                    ${equipo.variables_problematicas.length > 0 ? `
                    <div class="wells-summary" style="background: #fff5f5; border-top: 2px solid #e74c3c;">
                        <div class="wells-title" style="color: #e74c3c;">
                            <i class="fas fa-exclamation-triangle"></i> 
                            Variables con Problemas (${equipo.variables_problematicas.length})
                        </div>
                        <div style="max-height: 100px; overflow-y: auto;">
                            ${equipo.variables_problematicas.map(variable => `
                                <div style="display: flex; justify-content: space-between; padding: 3px 0; font-size: 0.8em;">
                                    <span>${variable.variable}</span>
                                    <span style="color: #e74c3c; font-weight: bold;">${variable.porcentaje_problemas}% problemas</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>` : ''}
                </div>
            `).join('');

            // Agregar eventos de tooltip
            agregarTooltips();
        }

        function generarHeaderDias() {
            const headers = [];
            for (let i = 13; i >= 0; i--) {
                const fecha = new Date(baseDate);
                fecha.setDate(fecha.getDate() - i);
                const dd = fecha.getDate().toString().padStart(2, '0');
                const mes = fecha.toLocaleDateString('es-AR', { month: 'short' }).replace('.', '');
                headers.push(`<div class="day-cell day-header"><span>${dd}</span><span style="opacity:0.85; font-size:0.9em;">${mes}</span></div>`);
            }
            return headers.join('');
        }

        function generarCeldasDias(actividad) {
            const celdas = [];
            for (let i = 13; i >= 0; i--) {
                const fecha = new Date(baseDate);
                fecha.setDate(fecha.getDate() - i);
                const fechaStr = fecha.toISOString().split('T')[0];
                
                const actividadDia = actividad[fechaStr];
                let clase = 'day-no-data';
                let contenido = '0';
                
                if (actividadDia) {
                    // Colorear por issues primero, luego por calidad
                    if (actividadDia.issues_count > 0) {
                        clase = 'day-partial';
                    } else if (actividadDia.calidad >= 80) {
                        clase = 'day-with-data';
                    } else if (actividadDia.calidad > 0) {
                        clase = 'day-partial';
                    }
                    contenido = actividadDia.pozos;
                }
                
                celdas.push(`
                    <div class="day-cell ${clase}" 
                         data-fecha="${fechaStr}" 
                         data-pozos="${actividadDia ? actividadDia.pozos : 0}"
                         data-variables="${actividadDia ? actividadDia.variables : 0}"
                         data-horas="${actividadDia ? Math.round(actividadDia.horas_monitoreadas) : 0}"
                         data-calidad="${actividadDia ? actividadDia.calidad : 0}"
                         data-issues="${actividadDia ? actividadDia.issues_count : 0}"
                         data-nr="${actividadDia ? (actividadDia.no_reg || 0) : 0}"
                         data-inc="${actividadDia ? (actividadDia.incomp || 0) : 0}"
                         data-fu="${actividadDia ? (actividadDia.fuera || 0) : 0}">
                        ${contenido}
                    </div>
                `);
            }
            return celdas.join('');
        }

        function agregarTooltips() {
            const celdas = document.querySelectorAll('.day-cell:not(.day-header)');
            const tooltip = document.getElementById('tooltip');
            
            celdas.forEach(celda => {
                // abrir modal con click
                celda.addEventListener('click', function() {
                    const fecha = this.dataset.fecha;
                    const equipo = this.closest('.equipment-card').querySelector('.equipment-header span').textContent.trim();
                    openDayModal(equipo, fecha);
                });
                celda.addEventListener('mouseenter', function(e) {
                    const fecha = this.dataset.fecha;
                    const pozos = this.dataset.pozos;
                    const variables = this.dataset.variables;
                    const horas = this.dataset.horas;
                    const calidad = this.dataset.calidad;
                    const issues = this.dataset.issues;
                    const nr = this.dataset.nr || 0;
                    const inc = this.dataset.inc || 0;
                    const fu = this.dataset.fu || 0;
                    
                    tooltip.innerHTML = `
                        <strong>${new Date(fecha).toLocaleDateString()}</strong><br>
                        Pozos trabajados: ${pozos}<br>
                        Variables monitoreadas: ${variables}<br>
                        Horas monitoreadas: ${horas}<br>
                        Calidad de datos: ${calidad}%<br>
                        Variables con alerta: ${issues} (no reg: ${nr}, incompleta: ${inc}, fuera: ${fu})
                    `;
                    
                    tooltip.style.opacity = '1';
                    posicionarTooltip(e, tooltip);
                });
                
                celda.addEventListener('mouseleave', function() {
                    tooltip.style.opacity = '0';
                });
                
                celda.addEventListener('mousemove', function(e) {
                    posicionarTooltip(e, tooltip);
                });
            });
        }

        function posicionarTooltip(e, tooltip) {
            const rect = tooltip.getBoundingClientRect();
            let left = e.pageX + 10;
            let top = e.pageY - rect.height - 10;
            
            if (left + rect.width > window.innerWidth) {
                left = e.pageX - rect.width - 10;
            }
            
            if (top < 0) {
                top = e.pageY + 10;
            }
            
            tooltip.style.left = left + 'px';
            tooltip.style.top = top + 'px';
        }

        function aplicarFiltros() {
            const equipoFilter = document.getElementById('equipoFilter').value.toLowerCase();
            const estadoFilter = document.getElementById('estadoFilter').value;
            const diasFilter = parseInt(document.getElementById('diasFilter').value) || 0;
            
            equiposData = equiposOriginal.filter(equipo => {
                const matchEquipo = equipo.nombre.toLowerCase().includes(equipoFilter);
                const matchEstado = !estadoFilter || equipo.estado === estadoFilter;
                const matchDias = equipo.dias_con_eventos >= diasFilter;
                
                return matchEquipo && matchEstado && matchDias;
            });
            
            renderizarGrid();
            
            // Actualizar estadísticas filtradas
            const statsFiltered = {
                total_equipos: equiposData.length,
                activos: equiposData.filter(e => e.estado === 'ACTIVO').length,
                alerta: equiposData.filter(e => e.estado === 'ALERTA').length,
                inactivos: equiposData.filter(e => e.estado === 'INACTIVO').length,
                total_pozos: equiposData.reduce((acc, e) => acc + (e.pozos_trabajados || 0), 0),
                calidad_promedio: equiposData.length ? 
                    Math.round((equiposData.reduce((acc, e) => acc + (e.porcentaje_calidad || 0), 0) / equiposData.length) * 10) / 10 : 
                    undefined
            };
            
            actualizarEstadisticas(statsFiltered);
        }

        function exportarDatos() {
            // Implementar exportación a CSV/Excel
            const csvData = equiposData.map(equipo => ({
                Equipo: equipo.nombre,
                Estado: equipo.estado,
                'Total Registros': equipo.total_registros,
                'Días Activos': equipo.dias_con_datos,
                'Última Fecha': equipo.ultima_fecha,
                'Días Inactivo': equipo.dias_inactivo,
                'Pozos': equipo.pozos_recientes.join('; ')
            }));
            
            console.log('Exportando datos:', csvData);
            alert('Función de exportación en desarrollo');
        }

        // ---------- Modal helpers ----------
        let currentModal = { rigId: null, date: null };

        async function openDayModal(equipoNombre, fecha) {
            // resolver rig_id desde equiposData
            const equipo = equiposOriginal.find(e => e.nombre === equipoNombre);
            if (!equipo) return;
            currentModal.rigId = equipo.rig_id || equipo.rigId || null;
            currentModal.date = fecha;

            document.getElementById('modalTitle').textContent = `Detalle del día — ${equipoNombre} — ${new Date(fecha).toLocaleDateString()}`;
            document.getElementById('modalBackdrop').style.display = 'flex';
            await reloadDayDetails();
        }

        function closeModal() {
            document.getElementById('modalBackdrop').style.display = 'none';
        }

        async function reloadDayDetails() {
            const onlyReq = document.getElementById('onlyRequiredChk').checked ? 1 : 0;
            const pmin = parseFloat(document.getElementById('presentMinInp').value) || 90;
            const rmin = parseFloat(document.getElementById('rangeMinInp').value) || 85;
            if (!currentModal.rigId || !currentModal.date) return;

            const url = `api_detalle_pulling_dia.php?rig_id=${currentModal.rigId}&date=${currentModal.date}&required_only=${onlyReq}&present_min=${pmin}&range_min=${rmin}`;
            const resp = await fetch(url);
            const data = await resp.json();

            renderDayTable(data);
        }

        function renderDayTable(data) {
            const tbody = document.querySelector('#dayTable tbody');
            tbody.innerHTML = '';
            document.getElementById('daySummary').textContent = `Variables con alerta: ${data.issues} — Umbrales: Presente ≥ ${data.present_min}% · En rango ≥ ${data.range_min}%`;

            const toRow = (d) => {
                const badge = d.alerta === 'OK' ? 'status-activo' : (d.alerta === 'INCOMPLETA' ? 'status-alerta' : (d.alerta === 'FUERA DE RANGO' ? 'status-inactivo' : 'status-alerta'));
                return `<tr>
                    <td style="padding:8px;"><strong>${d.variable}</strong></td>
                    <td style="padding:8px;">${d.unidad || '-'}</td>
                    <td style="padding:8px;">${d.tipo_variable || '-'}</td>
                    <td style="padding:8px; text-align:right;">${d.horas}</td>
                    <td style="padding:8px; text-align:right;">${d.pct_present}%</td>
                    <td style="padding:8px; text-align:right;">${d.pct_rango}%</td>
                    <td style="padding:8px; text-align:right;">${d.pct_nulas}%</td>
                    <td style="padding:8px;">${d.pozos || '-'}</td>
                    <td style="padding:8px; text-align:center;"><span class="status ${badge}">${d.alerta}</span></td>
                </tr>`;
            };

            tbody.innerHTML = data.detalles.map(toRow).join('');
            if (!data.detalles.length) {
                tbody.innerHTML = `<tr><td colspan="9" style="padding:16px; text-align:center; color:#7f8c8d;">Sin datos para el día seleccionado</td></tr>`;
            }
        }
    </script>
</body>
</html>
