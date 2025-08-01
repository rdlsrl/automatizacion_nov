import os
from PIL import Image, ImageDraw, ImageFont
import math
import random

# --- Configuración ---
IMG_SIZE = 64       # Tamaño en píxeles
OUTPUT_DIR = "final_relleno_denso_png" # Carpeta para los PNGs FINALES DENSOs
PATTERN_DRAW_COLOR = (0, 0, 0, 255) # Negro para dibujar los patrones
LINE_WIDTH = 1 # Forzar ancho de línea a 1 píxel para más finura
BACKGROUND_COLOR = (255, 255, 255, 0) # Transparente (se usa dentro de draw_pattern_on_bg)

# Colores de FONDO para cada tipo (iguales que antes)
BG_COLOR_INTRUSIVE = (255, 200, 200, 255) # Rojo pálido
BG_COLOR_EFFUSIVE = (255, 224, 200, 255)  # Naranja pálido
BG_COLOR_CONGLOMERATE = (200, 255, 200, 255) # Verde pálido
BG_COLOR_SANDSTONE = (240, 255, 200, 255)  # Verde amarillento pálido
BG_COLOR_PELITIC = (240, 240, 200, 255)   # Verde/Marrón pálido
BG_COLOR_LIMESTONE = (200, 255, 255, 255) # Cian pálido
BG_COLOR_MARL = (220, 255, 255, 255)      # Cian más pálido
BG_COLOR_DOLOMITE = (210, 240, 255, 255)  # Azul cielo pálido
BG_COLOR_SALT = (255, 220, 210, 255)      # Salmón pálido
BG_COLOR_GYPSUM = (255, 230, 235, 255)    # Rosa pálido claro
BG_COLOR_LOESS = (255, 248, 220, 255)     # Amarillo Loess (Cornsilk)
BG_COLOR_COAL = (100, 100, 100, 255)      # Gris oscuro (fondo para patrón negro)
BG_COLOR_TUFF = (255, 250, 230, 255)      # Crema/Beige
BG_COLOR_SERPENTINITE = (210, 240, 210, 255) # Verde grisáceo pálido
BG_COLOR_SCHIST = (230, 200, 230, 255)    # Púrpura pálido
BG_COLOR_GNEISS = (240, 210, 240, 255)    # Lavanda pálido
BG_COLOR_MIGMATITE = (235, 215, 235, 255) # Mezcla pálida
BG_COLOR_SLATE = (220, 220, 220, 255)     # Gris claro
BG_COLOR_MARBLE = (255, 225, 230, 255)    # Rosa muy pálido
BG_COLOR_QUARTZITE = (245, 235, 245, 255) # Thistle pálido
BG_COLOR_AMPHIBOLITE = (200, 220, 200, 255) # Verde oscuro pálido
BG_COLOR_MYLONITE = (210, 210, 210, 255)  # Gris medio

# --- Funciones Auxiliares ---
DEFAULT_FONT = ImageFont.load_default()
try:
    FONT_PATH = "arial.ttf"
    DEFAULT_FONT = ImageFont.truetype(FONT_PATH, 10)
    print(f"Usando fuente: {FONT_PATH}")
except IOError:
    try:
        FONT_PATH = "DejaVuSans.ttf"
        DEFAULT_FONT = ImageFont.truetype(FONT_PATH, 10)
        print(f"Usando fuente: {FONT_PATH}")
    except IOError:
        FONT_PATH = None
        print("Advertencia: No se encontraron Arial ni DejaVuSans. Usando fuente por defecto.")

def create_dir(path):
    os.makedirs(path, exist_ok=True)

def get_font(size):
    if FONT_PATH:
        try: return ImageFont.truetype(FONT_PATH, int(size))
        except IOError: return ImageFont.load_default()
    else: return ImageFont.load_default()

# --- Función Genérica para Dibujar ---
def draw_pattern_on_bg(filename, bg_color, draw_function, pattern_ref, *args, **kwargs):
    """Función genérica para dibujar un patrón (negro) sobre un fondo de color."""
    img = Image.new('RGBA', (IMG_SIZE, IMG_SIZE), bg_color)
    draw = ImageDraw.Draw(img)
    try:
        draw_function(draw, PATTERN_DRAW_COLOR, *args, **kwargs)
        img.save(filename)
        print(f"  -> Creado: {os.path.basename(filename)} ({pattern_ref})")
        return True
    except Exception as e:
        print(f"  ERROR al generar {os.path.basename(filename)}: {e}")
        return False

# --- Funciones de Dibujo Específicas (Densidad Aumentada, Línea Fina) ---

def _draw_crosses(draw, color, **kwargs): # Ígneas Intrusivas
    step = IMG_SIZE // 3 # Más denso
    line_len = IMG_SIZE * 0.12 # Un poco más pequeños quizás
    width = LINE_WIDTH
    for x in range(step // 2, IMG_SIZE, step):
        for y in range(step // 2, IMG_SIZE, step):
            cx, cy = x + (IMG_SIZE % 2) / 2, y + (IMG_SIZE % 2) / 2
            draw.line([(cx - line_len, cy), (cx + line_len, cy)], fill=color, width=width)
            draw.line([(cx, cy - line_len), (cx, cy + line_len)], fill=color, width=width)

def _draw_chevrons(draw, color, **kwargs): # Ígneas Efusivas
    step_x = IMG_SIZE // 4 # Más denso
    step_y = IMG_SIZE // 4 # Más denso
    sz_x = IMG_SIZE * 0.07
    sz_y = IMG_SIZE * 0.11
    width = LINE_WIDTH
    for x_base in range(step_x // 2, IMG_SIZE, step_x):
        for y_base in range(step_y // 2, IMG_SIZE, step_y):
            x = x_base + random.randint(-step_x//5, step_x//5) # Menos offset
            y = y_base + random.randint(-step_y//5, step_y//5)
            angle_rad = math.radians(random.uniform(-10, 10)) # Menos rotación
            p1 = (-sz_x, -sz_y * 0.5); p2 = (0, sz_y * 0.5); p3 = (sz_x, -sz_y * 0.5)
            cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
            rp1 = (p1[0]*cos_a - p1[1]*sin_a + x, p1[0]*sin_a + p1[1]*cos_a + y)
            rp2 = (p2[0]*cos_a - p2[1]*sin_a + x, p2[0]*sin_a + p2[1]*cos_a + y)
            rp3 = (p3[0]*cos_a - p3[1]*sin_a + x, p3[0]*sin_a + p3[1]*cos_a + y)
            draw.line([rp1, rp2], fill=color, width=width)
            draw.line([rp2, rp3], fill=color, width=width)

def _draw_conglomerate(draw, color, **kwargs): # Conglomerado
    num_clasts = max(8, IMG_SIZE // 6) # Más clastos
    width = LINE_WIDTH
    for i in range(num_clasts):
        cx = random.uniform(IMG_SIZE * 0.1, IMG_SIZE * 0.9); cy = random.uniform(IMG_SIZE * 0.1, IMG_SIZE * 0.9)
        base_radius = random.uniform(IMG_SIZE * 0.05, IMG_SIZE * 0.14); num_vertices = random.randint(5, 10)
        points = []; angle_offset = random.uniform(0, math.pi / num_vertices)
        for j in range(num_vertices):
            angle = angle_offset + 2 * math.pi * j / num_vertices
            radius = base_radius * random.uniform(0.6, 1.4)
            px = cx + radius * math.cos(angle); py = cy + radius * math.sin(angle)
            px = max(0, min(IMG_SIZE - 1, px)); py = max(0, min(IMG_SIZE - 1, py))
            points.append((px, py))
        points.append(points[0])
        draw.line(points, fill=color, width=width, joint='curve')

def _draw_sandstone_dots(draw, color, **kwargs): # Arenisca
    density_factor = 9 # Más denso
    step = max(2, IMG_SIZE // density_factor)
    radius = 1 # Puntos de 1px (o 2x2 elipse)
    start_offset = step // 2
    for x in range(start_offset, IMG_SIZE - start_offset // 2, step):
         for y in range(start_offset, IMG_SIZE - start_offset // 2, step):
             rx = x + random.randint(-step//6, step//6); ry = y + random.randint(-step//6, step//6)
             cx = max(radius, min(IMG_SIZE - radius, rx)); cy = max(radius, min(IMG_SIZE - radius, ry))
             # Usar point para 1px o ellipse para 2x2
             # draw.point((cx, cy), fill=color)
             draw.ellipse([(cx-radius, cy-radius), (cx+radius, cy+radius)], fill=color)

def _draw_pelitic_lines(draw, color, **kwargs): # Pelita/Lutita (Líneas Sólidas)
    step_y = max(3, IMG_SIZE // 9) # Más juntas
    width = LINE_WIDTH; start_offset_y = step_y // 3
    for y_base in range(start_offset_y, IMG_SIZE - start_offset_y // 2, step_y):
        y_draw = max(0, min(IMG_SIZE - 1, y_base))
        draw.line([(0, y_draw), (IMG_SIZE -1 , y_draw)], fill=color, width=width)

def _draw_fgdc_siltstone(draw, color, **kwargs): # Limolita
    step_y = max(4, IMG_SIZE // 8) # Más juntas
    dash_len = IMG_SIZE * 0.12 # Un poco más corto
    dot_radius = 1 # Punto de 1px
    gap = dash_len * 0.7
    width = LINE_WIDTH
    for y_base in range(step_y // 2, IMG_SIZE, step_y):
        x_start = ( (y_base // step_y) % 2 ) * (dash_len + gap + dot_radius*2 + gap) / 2
        while x_start < IMG_SIZE:
            x_end_dash = min(x_start + dash_len, IMG_SIZE -1)
            y_draw = max(0, min(IMG_SIZE -1, y_base))
            draw.line([(x_start, y_draw), (x_end_dash, y_draw)], fill=color, width=width)
            x_start = x_end_dash + gap
            if x_start + dot_radius < IMG_SIZE:
                 cx_dot = x_start + dot_radius
                 cy_dot = max(dot_radius, min(IMG_SIZE - dot_radius, y_base))
                 cx_dot = max(dot_radius, min(IMG_SIZE - dot_radius, cx_dot))
                 draw.ellipse([(cx_dot-dot_radius, cy_dot-dot_radius), (cx_dot+dot_radius, cy_dot+dot_radius)], fill=color)
            x_start += dot_radius*2 + gap

def _draw_limestone_bricks(draw, color, **kwargs): # Caliza/Marga
    h_step = max(3, IMG_SIZE // 6) # Más filas de ladrillos
    v_step = max(6, IMG_SIZE // 4) # Ladrillos más cortos
    width = LINE_WIDTH
    for y in range(0, IMG_SIZE + 1, h_step):
        y_draw = min(y, IMG_SIZE - 1) if y == IMG_SIZE else y
        draw.line([(0, y_draw), (IMG_SIZE, y_draw)], fill=color, width=width)
    for y_row_idx, y_bottom in enumerate(range(0, IMG_SIZE, h_step)):
        y_top = y_bottom + h_step; offset = (y_row_idx % 2) * (v_step // 2)
        for x in range(offset, IMG_SIZE + 1, v_step):
             if (x != 0 or offset != 0) and x < IMG_SIZE:
                 draw.line([(x, y_bottom), (x, min(y_top, IMG_SIZE))], fill=color, width=width)

def _draw_dolomite_slashed_bricks(draw, color, **kwargs): # Dolomita
    h_step = max(3, IMG_SIZE // 6); v_step = max(6, IMG_SIZE // 4); width = LINE_WIDTH
    slash_margin = width + 1 # Más margen para que slash no toque borde
    # 1. Ladrillos
    for y in range(0, IMG_SIZE + 1, h_step):
        y_draw = min(y, IMG_SIZE - 1) if y == IMG_SIZE else y
        draw.line([(0, y_draw), (IMG_SIZE, y_draw)], fill=color, width=width)
    for y_row_idx, y_bottom in enumerate(range(0, IMG_SIZE, h_step)):
        y_top = y_bottom + h_step; offset = (y_row_idx % 2) * (v_step // 2)
        for x in range(offset, IMG_SIZE + 1, v_step):
             if (x != 0 or offset != 0) and x < IMG_SIZE:
                 draw.line([(x, y_bottom), (x, min(y_top, IMG_SIZE))], fill=color, width=width)
    # 2. Slashes (\) más finos
    slash_width = max(1, width // 2)
    for y_row_idx, y_bottom in enumerate(range(0, IMG_SIZE, h_step)):
        y_top = min(y_bottom + h_step, IMG_SIZE); y_center = (y_bottom + y_top) / 2
        offset = (y_row_idx % 2) * (v_step // 2)
        for x_start in range(offset, IMG_SIZE, v_step):
             x_end = min(x_start + v_step, IMG_SIZE); x_center = (x_start + x_end) / 2
             current_v_step = x_end - x_start; current_h_step = y_top - y_bottom
             dx = max(1, (current_v_step / 2 - slash_margin) * 0.4) # Slashes más cortos
             dy = max(1, (current_h_step / 2 - slash_margin) * 0.4)
             if x_center < IMG_SIZE and y_center < IMG_SIZE:
                 draw.line([(x_center - dx, y_center + dy), (x_center + dx, y_center - dy)], fill=color, width=slash_width)

def _draw_salt_L(draw, color, **kwargs): # Sal
    step = IMG_SIZE // 4 # Más denso
    l_size = step * 0.4; width = LINE_WIDTH; start_offset = step // 3
    for x in range(start_offset, IMG_SIZE - start_offset, step):
        for y in range(start_offset, IMG_SIZE - start_offset, step):
             draw.line([(x - l_size/2, y - l_size/2), (x - l_size/2, y + l_size/2)], fill=color, width=width)
             draw.line([(x - l_size/2, y + l_size/2), (x + l_size/2, y + l_size/2)], fill=color, width=width)

def _draw_gypsum_Y(draw, color, **kwargs): # Yeso
    step = IMG_SIZE // 4 # Más denso
    char_size = step * 0.6; width = LINE_WIDTH; symbol_char = "Y"
    font = get_font(char_size)
    for x in range(step // 2, IMG_SIZE, step):
        for y in range(step // 2, IMG_SIZE, step):
             try:
                 if hasattr(draw, 'textbbox'):
                     bbox = draw.textbbox((0, 0), symbol_char, font=font); text_width = bbox[2] - bbox[0]
                     text_height = bbox[3] - bbox[1]; draw_x = x - text_width / 2; draw_y = y - text_height / 2 - bbox[1]
                 elif hasattr(draw, 'getsize'):
                     text_width, text_height = draw.getsize(symbol_char, font=font)
                     draw_x = x - text_width / 2; draw_y = y - text_height / 2
                 else: raise AttributeError("Ni textbbox ni getsize")
                 draw.text((draw_x, draw_y), symbol_char, fill=color, font=font)
             except AttributeError:
                 cy = y
                 draw.line([(x, cy - char_size*0.4), (x, cy + char_size*0.4)], fill=color, width=width)
                 draw.line([(x, cy - char_size*0.4), (x - char_size*0.3, cy - char_size*0.8)], fill=color, width=width)
                 draw.line([(x, cy - char_size*0.4), (x + char_size*0.3, cy - char_size*0.8)], fill=color, width=width)

def _draw_coal(draw, color, **kwargs): # Carbón
    draw.rectangle([(0,0), (IMG_SIZE, IMG_SIZE)], fill=color)

def _draw_loess(draw, color, **kwargs): # Loess
    density_factor = 9; step = max(3, IMG_SIZE // density_factor) # Más denso
    radius = max(1, IMG_SIZE // 32); start_offset = step // 3; width = 1 # Ancho fijo 1px
    for x in range(start_offset, IMG_SIZE - start_offset // 2, step):
         for y in range(start_offset, IMG_SIZE - start_offset // 2, step):
             rx = x + random.randint(-step//4, step//4); ry = y + random.randint(-step//4, step//4)
             cx = max(radius, min(IMG_SIZE - radius, rx)); cy = max(radius, min(IMG_SIZE - radius, ry))
             draw.ellipse([(cx-radius, cy-radius), (cx+radius, cy+radius)], outline=color, width=width)

def _draw_tuff(draw, color, **kwargs): # Toba
    width = LINE_WIDTH; dot_radius = 1; dash_len = IMG_SIZE * 0.08 # Más cortos
    num_elements = IMG_SIZE * IMG_SIZE // 15 # Más denso
    for _ in range(num_elements):
        x = random.uniform(dot_radius, IMG_SIZE - dot_radius)
        y = random.uniform(dot_radius, IMG_SIZE - dot_radius)
        if random.random() < 0.6: # Puntos
            draw.ellipse([(x-dot_radius, y-dot_radius), (x+dot_radius, y+dot_radius)], fill=color)
        else: # Trazos
            angle = random.uniform(0, math.pi)
            x1 = x - dash_len/2 * math.cos(angle); y1 = y - dash_len/2 * math.sin(angle)
            x2 = x + dash_len/2 * math.cos(angle); y2 = y + dash_len/2 * math.sin(angle)
            draw.line([(x1,y1), (x2,y2)], fill=color, width=width)

def _draw_serpentinite(draw, color, **kwargs): # Serpentinita
    step_x = IMG_SIZE // 5; step_y = IMG_SIZE // 6; amplitude = step_y * 0.35; width = LINE_WIDTH # Más denso
    for y_row in range(step_y // 2, IMG_SIZE, step_y):
        offset_x = (y_row // step_y % 2) * step_x / 2
        for x_base in range(int(offset_x) - step_x//2, IMG_SIZE + step_x//2, step_x): # Asegurar cobertura bordes
             p1 = (x_base - step_x * 0.4, y_row - amplitude)
             p2 = (x_base, y_row + amplitude)
             p3 = (x_base + step_x * 0.4, y_row - amplitude)
             draw.line([p1, p2, p3], fill=color, width=width, joint='curve')

def _draw_schist(draw, color, **kwargs): # Esquisto
    angle_degrees=30; frequency=2.8; amplitude_factor=0.05; step_y_factor = 8 # Más denso
    width = LINE_WIDTH; img_w, img_h = draw.im.size
    step_y = max(2, img_h // step_y_factor); amplitude = img_h * amplitude_factor
    rad_angle = math.radians(angle_degrees); cos_a, sin_a = math.cos(rad_angle), math.sin(rad_angle)
    diag = math.sqrt(img_w**2 + img_h**2)
    for i in range(int(-img_h / step_y * 1.5) , int(img_h / step_y * 1.5) + 1):
        y_base = i * step_y; points = []
        for x_local in range(int(-diag * 0.6), int(diag * 0.6)):
            y_wave = y_base + amplitude * math.sin(frequency * 2 * math.pi * x_local / img_w)
            rot_x = x_local * cos_a - y_wave * sin_a + img_w / 2
            rot_y = x_local * sin_a + y_wave * cos_a + img_h / 2
            points.append((rot_x, rot_y))
        if len(points) > 1: draw.line(points, fill=color, width=width)

def _draw_gneiss_bands(draw, color, **kwargs): # Gneis
    step_y = max(5, IMG_SIZE // 5); amplitude = IMG_SIZE * 0.09; frequency = 1.6 # Menos denso que esquisto
    width = max(LINE_WIDTH + 1 , IMG_SIZE // 35) # Más grueso
    for y_base in range(step_y // 2, IMG_SIZE, step_y):
        y_center = y_base + (IMG_SIZE % 2) / 2; points = []
        for x in range(IMG_SIZE + 1):
            y = y_center + amplitude * math.sin(frequency * 2 * math.pi * x / IMG_SIZE)
            points.append((x, min(max(0, y), IMG_SIZE-1)))
        draw.line(points, fill=color, width=width)

def _draw_marble_wavy_bricks(draw, color, **kwargs): # Mármol
    h_step = IMG_SIZE // 5; v_step = IMG_SIZE // 3; amplitude = IMG_SIZE * 0.06 # Más denso
    frequency = 2.0; width = LINE_WIDTH; horizontal_lines_y = {}
    for y_idx, y_base in enumerate(range(0, IMG_SIZE + 1, h_step)):
        points = []; current_line_y = []
        for x in range(IMG_SIZE + 1):
             y = y_base + amplitude * math.sin(frequency * 2 * math.pi * x / IMG_SIZE + (y_idx * 0.5))
             y_clamped = min(max(0, y), IMG_SIZE-1); points.append((x,y_clamped)); current_line_y.append(y_clamped)
        draw.line(points, fill=color, width=width); horizontal_lines_y[y_idx] = current_line_y
    num_rows = IMG_SIZE // h_step
    for y_row_idx in range(num_rows):
        y_bottom_idx, y_top_idx = y_row_idx, y_row_idx + 1
        if y_top_idx not in horizontal_lines_y or y_bottom_idx not in horizontal_lines_y : continue
        offset_x = (y_row_idx % 2) * (v_step // 2)
        for x in range(offset_x, IMG_SIZE + 1, v_step):
            if (x != 0 or offset_x != 0) and x < IMG_SIZE:
                 y_top_at_x = horizontal_lines_y[y_top_idx][x]; y_bot_at_x = horizontal_lines_y[y_bottom_idx][x]
                 draw.line([(x, y_bot_at_x), (x, y_top_at_x)], fill=color, width=width)

def _draw_quartzite_dots(draw, color, **kwargs): # Cuarcita
    num_dots = IMG_SIZE * IMG_SIZE // 5 # Más denso
    radius = 1 # Píxeles
    for _ in range(num_dots):
        x = random.randint(radius, IMG_SIZE - radius - 1)
        y = random.randint(radius, IMG_SIZE - radius - 1)
        draw.ellipse([(x-radius, y-radius),(x+radius, y+radius)], fill=color)

def _draw_slate(draw, color, **kwargs): # Pizarra/Filita
    step_y = max(1, IMG_SIZE // 16); width = 1; angle_degrees = 20 # Muy denso, líneas finas
    rad_angle = math.radians(angle_degrees); cos_a, sin_a = math.cos(rad_angle), math.sin(rad_angle)
    img_w, img_h = draw.im.size; diag = math.sqrt(img_w**2 + img_h**2)
    for i in range(int(-img_h / step_y * 1.5) , int(img_h / step_y * 1.5) + 1):
        y_base = i * step_y; cx, cy = img_w / 2, img_h / 2
        x0_local = -diag; x1_local = diag; y0_local = y_base; y1_local = y_base
        p0_x = (x0_local * cos_a - y0_local * sin_a) + cx; p0_y = (x0_local * sin_a + y0_local * cos_a) + cy
        p1_x = (x1_local * cos_a - y1_local * sin_a) + cx; p1_y = (x1_local * sin_a + y1_local * cos_a) + cy
        draw.line([(p0_x, p0_y), (p1_x, p1_y)], fill=color, width=width)

def _draw_amphibolite(draw, color, **kwargs): # Anfibolita
    step_x = IMG_SIZE // 4; step_y = IMG_SIZE // 4; sz_x = IMG_SIZE * 0.08 # Más denso
    sz_y = IMG_SIZE * 0.12; width = LINE_WIDTH
    for x_base in range(step_x // 2, IMG_SIZE, step_x):
        for y_base in range(step_y // 2, IMG_SIZE, step_y):
            x = x_base + random.randint(-step_x//5, step_x//5); y = y_base + random.randint(-step_y//5, step_y//5)
            angle_rad = math.radians(random.uniform(-10, 10))
            p1 = (-sz_x, -sz_y * 0.5); p2 = (0, sz_y * 0.5); p3 = (sz_x, -sz_y * 0.5)
            cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
            rp1 = (p1[0]*cos_a - p1[1]*sin_a + x, p1[0]*sin_a + p1[1]*cos_a + y)
            rp2 = (p2[0]*cos_a - p2[1]*sin_a + x, p2[0]*sin_a + p2[1]*cos_a + y)
            rp3 = (p3[0]*cos_a - p3[1]*sin_a + x, p3[0]*sin_a + p3[1]*cos_a + y)
            draw.line([rp1, rp2], fill=color, width=width)
            draw.line([rp2, rp3], fill=color, width=width)

def _draw_migmatite(draw, color, **kwargs): # Migmatita
    width_gneiss = max(LINE_WIDTH + 1, IMG_SIZE // 35); width_granite = LINE_WIDTH
    # 1. Gneis más denso
    step_y_g = max(5, IMG_SIZE // 4); amplitude_g = IMG_SIZE * 0.11; frequency_g = 1.3
    for y_base in range(step_y_g // 2, IMG_SIZE, step_y_g):
        y_center = y_base + (IMG_SIZE % 2) / 2; points = []
        for x in range(IMG_SIZE + 1):
            y = y_center + amplitude_g * math.sin(frequency_g * 2 * math.pi * x / IMG_SIZE)
            points.append((x, min(max(0, y), IMG_SIZE-1)))
        draw.line(points, fill=color, width=width_gneiss)
    # 2. Granito más denso
    step_gr = IMG_SIZE // 3; line_len_gr = IMG_SIZE * 0.08
    for x in range(step_gr // 2, IMG_SIZE, step_gr):
        y = (x // step_gr + 1) * step_y_g * 0.6 # Ajustar posición Y
        y = y % IMG_SIZE
        cx, cy = x + (IMG_SIZE % 2) / 2, y + (IMG_SIZE % 2) / 2
        draw.line([(cx - line_len_gr, cy), (cx + line_len_gr, cy)], fill=color, width=width_granite)
        draw.line([(cx, cy - line_len_gr), (cx, cy + line_len_gr)], fill=color, width=width_granite)

def _draw_mylonite(draw, color, **kwargs): # Milonita
    angle_degrees = 25; num_lenses = IMG_SIZE * IMG_SIZE // 18; width = LINE_WIDTH # Más denso
    rad_angle = math.radians(angle_degrees); cos_a, sin_a = math.cos(rad_angle), math.sin(rad_angle)
    for _ in range(num_lenses):
        cx = random.uniform(IMG_SIZE * 0.1, IMG_SIZE * 0.9); cy = random.uniform(IMG_SIZE * 0.1, IMG_SIZE * 0.9)
        len_l = random.uniform(IMG_SIZE * 0.08, IMG_SIZE * 0.22); wid_l = random.uniform(IMG_SIZE * 0.02, IMG_SIZE * 0.06)
        px1 = cx - len_l/2*cos_a; py1 = cy - len_l/2*sin_a
        px2 = cx + len_l/2*cos_a; py2 = cy + len_l/2*sin_a
        px1 = max(0, min(IMG_SIZE - 1, px1)); py1 = max(0, min(IMG_SIZE - 1, py1))
        px2 = max(0, min(IMG_SIZE - 1, px2)); py2 = max(0, min(IMG_SIZE - 1, py2))
        line_width_draw = max(1, int(wid_l))
        draw.line([(px1, py1),(px2,py2)], fill=color, width=line_width_draw)

# --- Script Principal ---
if __name__ == "__main__":
    print(f"--- Iniciando Generación de PNGs Densos (Color+Fondo, Híbrido PDF/FGDC) ---")
    print(f"Directorio de salida: '{os.path.abspath(OUTPUT_DIR)}'")
    create_dir(OUTPUT_DIR)

    symbols_to_generate = {
        # Clave -> (función_dibujo, color_fondo, nombre_archivo, ref_estándar)
        "ign_intrusive": (_draw_crosses, BG_COLOR_INTRUSIVE, "unr_ign_intrusive_denso.png", "UNR Intrusiva (Denso)"),
        "ign_effusive": (_draw_chevrons, BG_COLOR_EFFUSIVE, "unr_ign_effusive_denso.png", "UNR Efusiva (Denso)"),
        "ign_tuff": (_draw_tuff, BG_COLOR_TUFF, "fgdc_ign_tuff_denso.png", "FGDC Toba (Denso)"),
        "ign_serpentinite": (_draw_serpentinite, BG_COLOR_SERPENTINITE, "fgdc_ign_serpentinite_denso.png", "FGDC Serpentinita (Denso)"),
        "sed_conglomerate": (_draw_conglomerate, BG_COLOR_CONGLOMERATE, "fgdc_sed_conglomerate_denso.png", "FGDC Conglomerado (Denso)"),
        "sed_sandstone": (_draw_sandstone_dots, BG_COLOR_SANDSTONE, "fgdc_sed_sandstone_denso.png", "FGDC Arenisca (Denso)"),
        "sed_siltstone": (_draw_fgdc_siltstone, BG_COLOR_PELITIC, "fgdc_616_siltstone_denso.png", "FGDC Limolita (Denso)"),
        "sed_pelitic": (_draw_pelitic_lines, BG_COLOR_PELITIC, "unr_sed_pelitic_denso.png", "UNR Pelítica (Líneas, Denso)"),
        "sed_loess": (_draw_loess, BG_COLOR_LOESS, "fgdc_sed_loess_denso.png", "FGDC Loess (Denso)"),
        "sed_limestone": (_draw_limestone_bricks, BG_COLOR_LIMESTONE, "fgdc_sed_limestone_denso.png", "FGDC Caliza (Denso)"),
        "sed_marl": (_draw_limestone_bricks, BG_COLOR_MARL, "unr_sed_marl_denso.png", "UNR Marga (Denso)"),
        "sed_dolomite": (_draw_dolomite_slashed_bricks, BG_COLOR_DOLOMITE, "fgdc_sed_dolomite_denso.png", "FGDC Dolomita (Denso)"),
        "sed_salt": (_draw_salt_L, BG_COLOR_SALT, "fgdc_sed_salt_denso.png", "FGDC Sal (Denso)"),
        "sed_gypsum": (_draw_gypsum_Y, BG_COLOR_GYPSUM, "fgdc_sed_gypsum_denso.png", "FGDC Yeso (Denso)"),
        "sed_coal": (_draw_coal, BG_COLOR_COAL, "fgdc_sed_coal_denso.png", "FGDC Carbón"), # Densidad no aplica
        "meta_schist": (_draw_schist, BG_COLOR_SCHIST, "unr_meta_schist_denso.png", "UNR Esquisto (Denso)"),
        "meta_gneiss": (_draw_gneiss_bands, BG_COLOR_GNEISS, "unr_meta_gneiss_denso.png", "UNR Gneis (Denso)"),
        "meta_migmatite": (_draw_migmatite, BG_COLOR_MIGMATITE, "fgdc_meta_migmatite_denso.png", "FGDC Migmatita (Aprox, Denso)"),
        "meta_slate": (_draw_slate, BG_COLOR_SLATE, "fgdc_meta_slate_denso.png", "FGDC Pizarra (Denso)"),
        "meta_marble": (_draw_marble_wavy_bricks, BG_COLOR_MARBLE, "unr_meta_marble_denso.png", "UNR Mármol (Denso)"),
        "meta_quartzite": (_draw_quartzite_dots, BG_COLOR_QUARTZITE, "fgdc_meta_quartzite_denso.png", "FGDC Cuarcita (Denso)"),
        "meta_amphibolite": (_draw_amphibolite, BG_COLOR_AMPHIBOLITE, "unr_meta_amphibolite_denso.png", "UNR Anfibolita (Aprox, Denso)"),
        "meta_mylonite": (_draw_mylonite, BG_COLOR_MYLONITE, "fgdc_meta_mylonite_denso.png", "FGDC Milonita (Denso)"),
    }

    generated_count = 0
    error_count = 0
    generated_files = []

    for key, (draw_func, bg_color, filename_base, ref) in symbols_to_generate.items():
        filename = os.path.join(OUTPUT_DIR, filename_base)
        if draw_pattern_on_bg(filename, bg_color, draw_func, ref):
            generated_count += 1
            generated_files.append(filename_base)
        else:
            error_count += 1

    print(f"\n--- Proceso Finalizado ---")
    print(f"Se intentaron generar {len(symbols_to_generate)} símbolos.")
    print(f"Archivos PNG (Color+Fondo+Patrón Negro DENSO) creados exitosamente: {generated_count}")
    if error_count > 0: print(f"Errores durante la generación: {error_count}")
    else: print("¡Todos los símbolos solicitados se generaron correctamente!")
    print(f"Revisa los archivos en la carpeta: '{os.path.abspath(OUTPUT_DIR)}'")
    print("\nNOTA: Los patrones deberían ser más densos y las líneas finas (1px).")
    print("\nSiguiente paso: Confirma si esta versión DENSA te gusta más y proporciona la ruta base final para generar el SLD.")
