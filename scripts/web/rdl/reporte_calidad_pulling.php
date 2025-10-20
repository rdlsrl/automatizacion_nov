<?php
// ==========================================
// REPORTE CALIDAD DE DATOS - PULLING (MD TOTCO style)
// ==========================================

// DB config
$host = '127.0.0.1';
$user = 'root';
$pass = 'Partediario20';
$db = 'rdl_import';

// Params
$rig_id = isset($_GET['rig_id']) ? intval($_GET['rig_id']) : 0;
$desde = isset($_GET['desde']) ? $_GET['desde'] : date('Y-m-d', strtotime('-7 days'));
$hasta = isset($_GET['hasta']) ? $_GET['hasta'] : date('Y-m-d');
$show_only_issues = isset($_GET['issues']) ? ($_GET['issues'] === '1') : false;

// Thresholds (can be overridden by GET)
$pct_presente_min = isset($_GET['pct_present_min']) ? floatval($_GET['pct_present_min']) : 90.0; // under this -> incompleto
$pct_rango_min = isset($_GET['pct_range_min']) ? floatval($_GET['pct_range_min']) : 85.0; // under this -> fuera de rango

// Export csv flag
$export = isset($_GET['export']) ? $_GET['export'] : '';

// Connect
try { $pdo = new PDO("mysql:host=$host;dbname=$db;charset=utf8", $user, $pass, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]); }
catch (PDOException $e) { die('DB error: '.$e->getMessage()); }

// Load rigs (PUL)
$rigs = $pdo->query("SELECT id, name FROM rigs WHERE rig_type='PUL' ORDER BY name")->fetchAll(PDO::FETCH_ASSOC);
if (!$rig_id && !empty($rigs)) { $rig_id = intval($rigs[0]['id']); }

// Summary for header
$sumStmt = $pdo->prepare("SELECT 
    MIN(e.date) as fecha_min,
    MAX(e.date) as fecha_max,
    COALESCE(SUM(e.horas),0) as horas_total,
    GROUP_CONCAT(DISTINCT w.name ORDER BY w.name SEPARATOR ', ') as intervenciones
FROM errors_report_pae e
LEFT JOIN wells w ON e.well_id=w.id
WHERE e.rig_id=:rig_id AND e.date BETWEEN :desde AND :hasta");
$sumStmt->execute(['rig_id'=>$rig_id, 'desde'=>$desde, 'hasta'=>$hasta]);
$summary = $sumStmt->fetch(PDO::FETCH_ASSOC) ?: ['fecha_min'=>null,'fecha_max'=>null,'horas_total'=>0,'intervenciones'=>''];

// Variables aggregated
$varsSql = "SELECT 
    e.name_pae as variable,
    COALESCE(NULLIF(e.unidad_pae,''), NULLIF(e.unidad_nov,'')) as unidad,
    e.tipo_variable,
    ROUND(SUM(e.horas), 2) as horas_total,
    ROUND(SUM(e.value_present), 2) as horas_presentes,
    ROUND(SUM(e.value_range_in), 2) as horas_en_rango,
    ROUND(SUM(e.value_under_min+e.value_above_out), 2) as horas_fuera_rango,
    SUM(CASE WHEN e.requerido='SI' THEN 1 ELSE 0 END) as requerido_rows
FROM errors_report_pae e
WHERE e.rig_id=:rig_id AND e.date BETWEEN :desde AND :hasta
GROUP BY e.name_pae, e.tipo_variable, unidad
ORDER BY e.name_pae";
$varsStmt = $pdo->prepare($varsSql);
$varsStmt->execute(['rig_id'=>$rig_id,'desde'=>$desde,'hasta'=>$hasta]);
$variables = $varsStmt->fetchAll(PDO::FETCH_ASSOC);

// Compute metrics row by row
$rows = [];
foreach ($variables as $v) {
    $horas = floatval($v['horas_total']);
    $present = floatval($v['horas_presentes']);
    $en_rango = floatval($v['horas_en_rango']);
    $fuera = floatval($v['horas_fuera_rango']);

    $pct_present = $horas > 0 ? round(($present / $horas) * 100, 2) : 0.0;
    $pct_rango = $horas > 0 ? round(($en_rango / $horas) * 100, 2) : 0.0;

    // Classify alert
    $alerta = 'OK'; $alerta_tipo = 'ok';
    if ($horas <= 0 || $present <= 0) { $alerta='NO REGISTRADA'; $alerta_tipo='no-reg'; }
    else if ($pct_rango < $pct_rango_min) { $alerta='FUERA DE RANGO'; $alerta_tipo='fr'; }
    else if ($pct_present < $pct_presente_min) { $alerta='INCOMPLETA'; $alerta_tipo='inc'; }

    $row = [
        'variable' => $v['variable'],
        'unidad' => $v['unidad'],
        'tipo_variable' => $v['tipo_variable'],
        'horas' => $horas,
        'pct_present' => $pct_present,
        'pct_rango' => $pct_rango,
        'alerta' => $alerta,
        'alerta_tipo' => $alerta_tipo
    ];
    $rows[] = $row;
}

// Filter only issues if requested
if ($show_only_issues) {
    $rows = array_values(array_filter($rows, function($r){ return $r['alerta'] !== 'OK'; }));
}

// Export CSV
if ($export === 'csv') {
    header('Content-Type: text/csv; charset=utf-8');
    header('Content-Disposition: attachment; filename=reporte_calidad_'.$rig_id.'_'.$desde.'_'.$hasta.'.csv');
    $out = fopen('php://output', 'w');
    fputcsv($out, ['EQUIPO','VARIABLE/UNIDAD','TIPO VARIABLE','REGISTRO (HS)','VALOR PRESENTE (%)','DENTRO RANGO (%)','ALERTA']);
    // Fetch rig name
    $rigName = '';
    foreach ($rigs as $r) { if (intval($r['id']) === $rig_id) { $rigName = $r['name']; break; } }
    foreach ($rows as $r) {
        fputcsv($out, [
            $rigName,
            $r['variable'].($r['unidad']?" (".$r['unidad'].")":''),
            $r['tipo_variable'],
            number_format($r['horas'],1,'.',''),
            number_format($r['pct_present'],1,'.',''),
            number_format($r['pct_rango'],1,'.',''),
            $r['alerta'],
        ]);
    }
    fclose($out); exit;
}

// Helper to get rig name
$rigName = '';
foreach ($rigs as $r) { if (intval($r['id']) === $rig_id) { $rigName = $r['name']; break; } }
?>
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reporte Calidad de Datos - Pulling</title>
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
<style>
    body { font-family: Segoe UI, Roboto, Arial, sans-serif; background:#f3f6fa; padding: 20px; }
    .card { background:#fff; border-radius:12px; box-shadow:0 8px 24px rgba(0,0,0,.08); margin-bottom:20px; overflow:hidden; }
    .header { background:#6b8e23; color:#fff; padding:14px 20px; font-weight:700; font-size:18px; letter-spacing:.5px; }
    .grid { display:grid; grid-template-columns: 280px 1fr; }
    .grid .left, .grid .right { padding: 18px 20px; }
    .label { color:#4a5b6b; font-weight:700; letter-spacing:.4px; font-size:13px; margin-bottom:6px; }
    .pill { background:#e7efd4; padding:6px 10px; border-radius:8px; display:inline-block; font-weight:700; color:#3d4b2b; }
    .muted { color:#6c7a89; }

    .filters { display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end; }
    .filters .group { display:flex; flex-direction:column; }
    .filters input, .filters select { padding:8px 10px; border:1px solid #cfd9e3; border-radius:8px; }
    .btn { background:linear-gradient(135deg,#3b82f6,#2563eb); color:#fff; border:none; padding:9px 14px; border-radius:8px; cursor:pointer; font-weight:700; }
    .btn.secondary { background:linear-gradient(135deg,#10b981,#059669); }

    table { width:100%; border-collapse:collapse; }
    th, td { padding:10px 12px; border-bottom:1px solid #eef2f7; font-size:14px; }
    th { background:#8fad35; color:#fff; text-align:left; position:sticky; top:0; z-index:1; }
    .tbox { max-height: 560px; overflow:auto; }

    .badge { padding:6px 9px; border-radius:12px; font-weight:700; font-size:12px; }
    .ok { background:#e8f7ee; color:#1b7f3d; }
    .inc { background:#fff4e5; color:#b45b00; }
    .fr { background:#fde8e7; color:#b91c1c; }
    .no-reg { background:#dfe7f7; color:#1f3b7a; }

    .kpi { display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; }
    .kpi .tile { background:#f7f9fc; border:1px solid #eef2f7; border-radius:10px; padding:12px; text-align:center; }
    .kpi .tile h3 { margin:0; font-size:22px; color:#2b3640; }
    .kpi .tile p { margin:6px 0 0; color:#6b7c8a; font-size:12px; letter-spacing:.3px; }

    .actions { display:flex; gap:10px; }
    .link { color:#2563eb; text-decoration:none; font-weight:700; }
</style>
</head>
<body>

<div class="card">
  <div class="header">REPORTE CALIDAD DE DATOS - PULLING</div>
  <div class="grid">
    <div class="left">
      <div class="label">EQUIPO</div>
      <div class="pill"><?php echo htmlspecialchars($rigName); ?></div>
      <div style="margin-top:14px" class="label">INTERVENCIONES REALIZADAS</div>
      <div class="muted" style="max-height:60px; overflow:auto;">
        <?php echo htmlspecialchars($summary['intervenciones'] ?: '-'); ?>
      </div>
    </div>
    <div class="right">
      <form class="filters" method="get">
        <div class="group">
          <label class="label">Equipo</label>
          <select name="rig_id">
            <?php foreach ($rigs as $opt): ?>
              <option value="<?php echo intval($opt['id']); ?>" <?php echo intval($opt['id'])===$rig_id?'selected':''; ?>><?php echo htmlspecialchars($opt['name']); ?></option>
            <?php endforeach; ?>
          </select>
        </div>
        <div class="group">
          <label class="label">Desde</label>
          <input type="date" name="desde" value="<?php echo htmlspecialchars($desde); ?>">
        </div>
        <div class="group">
          <label class="label">Hasta</label>
          <input type="date" name="hasta" value="<?php echo htmlspecialchars($hasta); ?>">
        </div>
        <div class="group">
          <label class="label">Solo con problemas</label>
          <select name="issues">
            <option value="0" <?php echo !$show_only_issues?'selected':''; ?>>No</option>
            <option value="1" <?php echo $show_only_issues?'selected':''; ?>>Sí</option>
          </select>
        </div>
        <div class="group">
          <label class="label">Umbral Presentes (%)</label>
          <input type="number" step="0.1" min="0" max="100" name="pct_present_min" value="<?php echo htmlspecialchars($pct_presente_min); ?>">
        </div>
        <div class="group">
          <label class="label">Umbral Dentro Rango (%)</label>
          <input type="number" step="0.1" min="0" max="100" name="pct_range_min" value="<?php echo htmlspecialchars($pct_rango_min); ?>">
        </div>
        <div class="group actions">
          <button class="btn" type="submit"><i class="fa fa-search"></i> Aplicar</button>
          <a class="btn secondary" href="?rig_id=<?php echo $rig_id; ?>&desde=<?php echo $desde; ?>&hasta=<?php echo $hasta; ?>&issues=<?php echo $show_only_issues?'1':'0'; ?>&pct_present_min=<?php echo $pct_presente_min; ?>&pct_range_min=<?php echo $pct_rango_min; ?>&export=csv">
            <i class="fa fa-file-csv"></i> Exportar CSV
          </a>
          <a class="link" href="/rdl/monitor_pulling_grid.php">Ver Monitor</a>
        </div>
      </form>

      <div class="kpi" style="margin-top:14px;">
        <div class="tile">
          <h3><?php echo $summary['fecha_min']?date('d/m/Y', strtotime($summary['fecha_min'])):'-'; ?> — <?php echo $summary['fecha_max']?date('d/m/Y', strtotime($summary['fecha_max'])):'-'; ?></h3>
          <p>Rango Fechas Reportadas</p>
        </div>
        <div class="tile">
          <h3><?php echo number_format(floatval($summary['horas_total']), 1, ',', '.'); ?></h3>
          <p>Registro Total (Hs)</p>
        </div>
        <div class="tile">
          <h3><?php echo number_format(count($rows), 0, ',', '.'); ?></h3>
          <p>Variables Evaluadas</p>
        </div>
        <?php 
        $issuesCount = count(array_filter($rows, fn($r)=>$r['alerta']!=='OK'));
        ?>
        <div class="tile">
          <h3><?php echo $issuesCount; ?></h3>
          <p>Variables con Alerta</p>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="card">
  <div class="header">DETALLE POR VARIABLE</div>
  <div class="tbox">
    <table>
      <thead>
        <tr>
          <th style="width:160px;">Equipo</th>
          <th>Variable / Unidad</th>
          <th style="width:140px;">Tipo Variable</th>
          <th style="width:120px;">Registro (Hs)</th>
          <th style="width:150px;">Valor Presente (%)</th>
          <th style="width:170px;">Valor Dentro del Rango (%)</th>
          <th style="width:140px;">Alerta</th>
        </tr>
      </thead>
      <tbody>
        <?php foreach ($rows as $row): ?>
          <?php 
            $badgeClass = $row['alerta_tipo'];
            $pctP = number_format($row['pct_present'], 1, ',', '.');
            $pctR = number_format($row['pct_rango'], 1, ',', '.');
            $hor = number_format($row['horas'], 1, ',', '.');
          ?>
          <tr>
            <td><?php echo htmlspecialchars($rigName); ?></td>
            <td>
              <strong><?php echo htmlspecialchars($row['variable']); ?></strong>
              <?php if ($row['unidad']): ?>
                <span class="muted">(<?php echo htmlspecialchars($row['unidad']); ?>)</span>
              <?php endif; ?>
            </td>
            <td><?php echo htmlspecialchars($row['tipo_variable'] ?: '-'); ?></td>
            <td><?php echo $hor; ?></td>
            <td><?php echo $pctP; ?>%</td>
            <td><?php echo $pctR; ?>%</td>
            <td><span class="badge <?php echo $badgeClass; ?>"><?php echo $row['alerta']; ?></span></td>
          </tr>
        <?php endforeach; ?>
        <?php if (empty($rows)): ?>
          <tr><td colspan="7" class="muted" style="text-align:center; padding:20px;">Sin datos para los filtros seleccionados</td></tr>
        <?php endif; ?>
      </tbody>
    </table>
  </div>
</div>

</body>
</html>
