<?php
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

$host = '127.0.0.1';
$user = 'root';
$pass = 'Partediario20';
$db = 'rdl_import';

$rig_id = isset($_GET['rig_id']) ? intval($_GET['rig_id']) : 0;
$date = isset($_GET['date']) ? $_GET['date'] : date('Y-m-d');
$required_only = isset($_GET['required_only']) ? ($_GET['required_only'] === '1') : false;
$present_min = isset($_GET['present_min']) ? floatval($_GET['present_min']) : 90.0; // %
$range_min = isset($_GET['range_min']) ? floatval($_GET['range_min']) : 85.0; // %

if ($rig_id <= 0 || !preg_match('/^\d{4}-\d{2}-\d{2}$/', $date)) {
    http_response_code(400);
    echo json_encode(['error' => 'Parámetros inválidos: rig_id y date (YYYY-MM-DD) son requeridos']);
    exit;
}

try {
    $pdo = new PDO("mysql:host=$host;dbname=$db;charset=utf8", $user, $pass);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['error' => 'Error de conexión: '.$e->getMessage()]);
    exit;
}

$whereReq = $required_only ? " AND e.requerido='SI'" : '';

$sql = "SELECT 
            e.name_pae AS variable,
            COALESCE(NULLIF(e.unidad_pae,''), NULLIF(e.unidad_nov,'')) AS unidad,
            e.tipo_variable,
            SUM(e.horas) AS horas_total,
            SUM(e.value_present) AS horas_presentes,
            SUM(e.value_range_in) AS horas_en_rango,
            SUM(e.value_null) AS horas_nulas,
            SUM(e.value_under_min) AS horas_bajo_min,
            SUM(e.value_above_out) AS horas_sobre_max,
            MAX(CASE WHEN e.requerido='SI' THEN 1 ELSE 0 END) AS requerido,
            GROUP_CONCAT(DISTINCT w.name ORDER BY w.name SEPARATOR ', ') AS pozos
        FROM errors_report_pae e
        LEFT JOIN wells w ON w.id = e.well_id
        WHERE e.rig_id = :rig_id AND e.date = :fecha {$whereReq}
        GROUP BY e.name_pae, e.tipo_variable, unidad
        ORDER BY e.name_pae";

$stmt = $pdo->prepare($sql);
$stmt->execute(['rig_id' => $rig_id, 'fecha' => $date]);
$rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

$detalles = [];
$issues = 0;
foreach ($rows as $r) {
    $horas = floatval($r['horas_total']);
    $present = floatval($r['horas_presentes']);
    $en_rango = floatval($r['horas_en_rango']);
    $nulas = floatval($r['horas_nulas']);
    $bajo = floatval($r['horas_bajo_min']);
    $sobre = floatval($r['horas_sobre_max']);

    $pct_present = $horas>0 ? round($present/$horas*100,1) : 0.0;
    $pct_rango = $horas>0 ? round($en_rango/$horas*100,1) : 0.0;
    $pct_nulas = $horas>0 ? round($nulas/$horas*100,1) : 0.0;
    $pct_bajo = $horas>0 ? round($bajo/$horas*100,1) : 0.0;
    $pct_sobre = $horas>0 ? round($sobre/$horas*100,1) : 0.0;

    $alerta = 'OK';
    $severidad = 0;
    if ($present <= 0) { $alerta = 'NO REGISTRADA'; $severidad = 3; }
    else if ($pct_rango < $range_min) { $alerta = 'FUERA DE RANGO'; $severidad = 2; }
    else if ($pct_present < $present_min) { $alerta = 'INCOMPLETA'; $severidad = 1; }

    if ($severidad>0) { $issues++; }

    $detalles[] = [
        'variable' => $r['variable'],
        'unidad' => $r['unidad'],
        'tipo_variable' => $r['tipo_variable'],
        'horas' => round($horas,1),
        'pct_present' => $pct_present,
        'pct_rango' => $pct_rango,
        'pct_nulas' => $pct_nulas,
        'pct_bajo' => $pct_bajo,
        'pct_sobre' => $pct_sobre,
        'requerido' => $r['requerido'] ? 'SI' : 'NO',
        'pozos' => $r['pozos'],
        'alerta' => $alerta,
        'severidad' => $severidad
    ];
}

// Ordenar por severidad desc, luego por menor % dentro de rango
usort($detalles, function($a,$b){
    if ($a['severidad'] === $b['severidad']) {
        return $a['pct_rango'] <=> $b['pct_rango'];
    }
    return $b['severidad'] <=> $a['severidad'];
});

echo json_encode([
    'success' => true,
    'rig_id' => $rig_id,
    'date' => $date,
    'issues' => $issues,
    'present_min' => $present_min,
    'range_min' => $range_min,
    'required_only' => $required_only,
    'detalles' => $detalles
], JSON_PRETTY_PRINT);
