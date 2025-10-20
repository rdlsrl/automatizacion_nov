<?php
// Obtener equipos pulling con datos de las últimas 2 semanas
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

// Parámetros de umbral (opcionales)
$present_min = isset($_GET['present_min']) ? floatval($_GET['present_min']) : 90.0; // %
$range_min = isset($_GET['range_min']) ? floatval($_GET['range_min']) : 85.0; // %

// Corte diario: SIEMPRE hasta ayer
$max_date = date('Y-m-d', strtotime('-1 day'));

// Configuración de base de datos
$host = '127.0.0.1';
$user = 'root';
$pass = 'Partediario20';
$db = 'rdl_import';

try {
    $pdo = new PDO("mysql:host=$host;dbname=$db;charset=utf8", $user, $pass);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch(PDOException $e) {
    http_response_code(500);
    echo json_encode(['error' => 'Error de conexión: ' . $e->getMessage()]);
    exit;
}

// Obtener resumen de equipos pulling con métricas de calidad de datos
$sql_equipos = "
    SELECT 
        r.name as nombre,
        r.id as rig_id,
        COUNT(DISTINCT e.date) as dias_con_eventos,
        COUNT(DISTINCT CONCAT(e.date, '_', e.well_id)) as pozos_dias_unicos,
        COUNT(DISTINCT e.well_id) as pozos_trabajados,
        COUNT(DISTINCT e.name_pae) as variables_monitoreadas,
        SUM(e.horas) as total_horas_monitoreadas,
        SUM(e.value_present) as horas_con_datos,
        SUM(e.value_null) as horas_sin_datos,
        ROUND((SUM(e.value_present) / NULLIF(SUM(e.horas),0)) * 100, 1) as porcentaje_calidad,
        MIN(e.date) as primera_fecha,
        MAX(e.date) as ultima_fecha,
        DATEDIFF(CURDATE(), MAX(e.date)) as dias_inactivo,
        CASE 
            WHEN DATEDIFF(CURDATE(), MAX(e.date)) <= 1 THEN 'ACTIVO'
            WHEN DATEDIFF(CURDATE(), MAX(e.date)) <= 3 THEN 'ALERTA'
            ELSE 'INACTIVO'
        END as estado
    FROM errors_report_pae e 
    JOIN rigs r ON e.rig_id = r.id 
    WHERE r.rig_type = 'PUL' 
        AND e.date >= DATE_SUB(:max_date, INTERVAL 14 DAY)
        AND e.date <= :max_date
    GROUP BY r.id, r.name 
    ORDER BY ultima_fecha DESC, total_horas_monitoreadas DESC
";
$stmt_equipos = $pdo->prepare($sql_equipos);
$stmt_equipos->execute(['max_date' => $max_date]);
$equipos = $stmt_equipos->fetchAll(PDO::FETCH_ASSOC);

// Obtener actividad diaria detallada para cada equipo
$equipos_con_actividad = [];
foreach ($equipos as $equipo) {
    
    // Reemplazo de la consulta para compatibilidad sin CTE (algunas versiones de MariaDB no soportan WITH)
    $sql_actividad_no_cte = "
        SELECT 
            d.fecha,
            d.pozos_trabajados,
            d.variables_monitoreadas,
            d.horas_monitoreadas,
            d.horas_con_datos,
            d.horas_sin_datos,
            ROUND((d.horas_con_datos/NULLIF(d.horas_monitoreadas,0))*100,1) AS calidad_porcentaje,
            i.vars_no_reg,
            i.vars_incomp,
            i.vars_fuera,
            (COALESCE(i.vars_no_reg,0) + COALESCE(i.vars_incomp,0) + COALESCE(i.vars_fuera,0)) AS issues_count
        FROM (
            SELECT 
                e.date AS fecha,
                COUNT(DISTINCT e.well_id) AS pozos_trabajados,
                COUNT(DISTINCT e.name_pae) AS variables_monitoreadas,
                SUM(e.horas) AS horas_monitoreadas,
                SUM(e.value_present) AS horas_con_datos,
                SUM(e.value_null) AS horas_sin_datos
            FROM errors_report_pae e
            WHERE e.rig_id = :rig_id1 
              AND e.date >= DATE_SUB(:max_date, INTERVAL 14 DAY)
              AND e.date <= :max_date
            GROUP BY e.date
        ) d
        LEFT JOIN (
            SELECT 
                a.fecha,
                SUM(CASE WHEN a.horas_presentes <= 0 THEN 1 ELSE 0 END) AS vars_no_reg,
                SUM(CASE WHEN a.horas_presentes > 0 AND (a.horas_presentes/NULLIF(a.horas_total,0))*100 < :present_min THEN 1 ELSE 0 END) AS vars_incomp,
                SUM(CASE WHEN a.horas_presentes > 0 AND (a.horas_en_rango/NULLIF(a.horas_total,0))*100 < :range_min THEN 1 ELSE 0 END) AS vars_fuera
            FROM (
                SELECT 
                    e.date AS fecha,
                    e.name_pae,
                    SUM(e.horas) AS horas_total,
                    SUM(e.value_present) AS horas_presentes,
                    SUM(e.value_range_in) AS horas_en_rango
                FROM errors_report_pae e
                WHERE e.rig_id = :rig_id2
                  AND e.date >= DATE_SUB(:max_date, INTERVAL 14 DAY)
                  AND e.date <= :max_date
                  AND e.requerido = 'SI'
                GROUP BY e.date, e.name_pae
            ) a
            GROUP BY a.fecha
        ) i ON i.fecha = d.fecha
        ORDER BY d.fecha DESC
    ";
    $stmt_actividad = $pdo->prepare($sql_actividad_no_cte);
    $stmt_actividad->execute([
        'rig_id1' => $equipo['rig_id'],
        'rig_id2' => $equipo['rig_id'],
        'max_date' => $max_date,
        'present_min' => $present_min,
        'range_min' => $range_min
    ]);
    $actividad_raw = $stmt_actividad->fetchAll(PDO::FETCH_ASSOC);
    
    // Convertir a array asociativo por fecha
    $actividad_diaria = [];
    foreach ($actividad_raw as $dia) {
        $actividad_diaria[$dia['fecha']] = [
            'pozos' => (int)$dia['pozos_trabajados'],
            'variables' => (int)$dia['variables_monitoreadas'],
            'horas_monitoreadas' => (float)$dia['horas_monitoreadas'],
            'horas_con_datos' => (float)$dia['horas_con_datos'],
            'horas_sin_datos' => (float)$dia['horas_sin_datos'],
            'calidad' => (float)$dia['calidad_porcentaje'],
            'issues_count' => (int)$dia['issues_count'],
            'no_reg' => isset($dia['vars_no_reg']) ? (int)$dia['vars_no_reg'] : 0,
            'incomp' => isset($dia['vars_incomp']) ? (int)$dia['vars_incomp'] : 0,
            'fuera' => isset($dia['vars_fuera']) ? (int)$dia['vars_fuera'] : 0,
            'has_issues' => ((int)$dia['issues_count']) > 0
        ];
    }
    
    // Obtener pozos recientes con detalles
    $sql_pozos = "
        SELECT 
            w.name as pozo,
            MAX(e.date) as ultima_fecha,
            COUNT(DISTINCT e.name_pae) as variables,
            SUM(e.horas) as total_horas,
            ROUND((SUM(e.value_present) / SUM(e.horas)) * 100, 1) as calidad
        FROM errors_report_pae e 
        JOIN wells w ON e.well_id = w.id
        WHERE e.rig_id = :rig_id 
            AND e.date >= DATE_SUB(:max_date, INTERVAL 7 DAY)
            AND e.date <= :max_date
        GROUP BY w.id, w.name
        ORDER BY MAX(e.date) DESC
        LIMIT 10
    ";
    
    $stmt_pozos = $pdo->prepare($sql_pozos);
    $stmt_pozos->execute(['rig_id' => $equipo['rig_id'], 'max_date' => $max_date]);
    $pozos_detalle = $stmt_pozos->fetchAll(PDO::FETCH_ASSOC);
    
    // Obtener variables más problemáticas (con más horas sin datos)
    $sql_variables = "
        SELECT 
            e.name_pae as variable,
            SUM(e.horas) as total_horas,
            SUM(e.value_null) as horas_sin_datos,
            ROUND((SUM(e.value_null) / SUM(e.horas)) * 100, 1) as porcentaje_problemas
        FROM errors_report_pae e 
        WHERE e.rig_id = :rig_id 
            AND e.date >= DATE_SUB(:max_date, INTERVAL 7 DAY)
            AND e.date <= :max_date
            AND e.requerido = 'SI'
        GROUP BY e.name_pae
        HAVING porcentaje_problemas > 0
        ORDER BY porcentaje_problemas DESC
        LIMIT 5
    ";
    
    $stmt_variables = $pdo->prepare($sql_variables);
    $stmt_variables->execute(['rig_id' => $equipo['rig_id'], 'max_date' => $max_date]);
    $variables_problematicas = $stmt_variables->fetchAll(PDO::FETCH_ASSOC);
    
    $equipos_con_actividad[] = [
        'rig_id' => (int)$equipo['rig_id'],
        'nombre' => $equipo['nombre'],
        'estado' => $equipo['estado'],
        'dias_con_eventos' => (int)$equipo['dias_con_eventos'],
        'pozos_trabajados' => (int)$equipo['pozos_trabajados'],
        'variables_monitoreadas' => (int)$equipo['variables_monitoreadas'],
        'total_horas_monitoreadas' => (float)$equipo['total_horas_monitoreadas'],
        'horas_con_datos' => (float)$equipo['horas_con_datos'],
        'horas_sin_datos' => (float)$equipo['horas_sin_datos'],
        'porcentaje_calidad' => (float)$equipo['porcentaje_calidad'],
        'primera_fecha' => date('d/m/Y', strtotime($equipo['primera_fecha'])),
        'ultima_fecha' => date('d/m/Y', strtotime($equipo['ultima_fecha'])),
        'dias_inactivo' => (int)$equipo['dias_inactivo'],
        'actividad_diaria' => $actividad_diaria,
        'pozos_detalle' => $pozos_detalle,
        'variables_problematicas' => $variables_problematicas
    ];
}

// Calcular estadísticas generales
$estadisticas = [
    'total_equipos' => count($equipos_con_actividad),
    'activos' => count(array_filter($equipos_con_actividad, function($e) { return $e['estado'] == 'ACTIVO'; })),
    'alerta' => count(array_filter($equipos_con_actividad, function($e) { return $e['estado'] == 'ALERTA'; })),
    'inactivos' => count(array_filter($equipos_con_actividad, function($e) { return $e['estado'] == 'INACTIVO'; })),
    'total_pozos' => array_sum(array_column($equipos_con_actividad, 'pozos_trabajados')),
    'calidad_promedio' => round(array_sum(array_column($equipos_con_actividad, 'porcentaje_calidad')) / max(count($equipos_con_actividad), 1), 1)
];

// Respuesta JSON
$response = [
    'success' => true,
    'timestamp' => date('Y-m-d H:i:s'),
    'present_min' => $present_min,
    'range_min' => $range_min,
    'max_date' => $max_date,
    'estadisticas' => $estadisticas,
    'equipos' => $equipos_con_actividad
];

echo json_encode($response, JSON_PRETTY_PRINT);
