import io
import os
import asyncio
import httpx
import base64
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from concurrent.futures import ThreadPoolExecutor

# ================= ADJUSTMENT SETTINGS =================

AVATAR_ZOOM = 1.26
AVATAR_SHIFT_Y = 0  
AVATAR_SHIFT_X = 0  

BANNER_START_X = 0.25
BANNER_START_Y = 0.29
BANNER_END_X = 0.81
BANNER_END_Y = 0.65

# ========================================================================

API_KEY = "STK"  # Sua chave da API
INFO_API_URL = "http://freefireapi.com.br/api/player"

# Nova URL base para imagens
IMAGE_BASE_URL = "https://dl.cdn.freefiremobile.com/live/ABHotUpdates/IconCDN/other"

# IDs padrão
DEFAULT_BANNER_ID = "900000014"
DEFAULT_AVATAR_ID = "900000014"

# Qualidade da imagem
TARGET_HEIGHT = 800  # Aumentado para melhor qualidade (era 400)
TARGET_QUALITY = 95  # Qualidade de salvamento

# ================= Lifespan =================
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await client.aclose()
    process_pool.shutdown()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE64 = "aHR0cHM6Ly9jZG4uanNkZWxpdnIubmV0L2doL1NoYWhHQ3JlYXRvci9pY29uQG1haW4vUE5H"
info_URL = base64.b64decode(BASE64).decode('utf-8')

FONT_FILE = "arial_unicode_bold.otf"
FONT_CHEROKEE = "NotoSansCherokee.ttf"

client = httpx.AsyncClient(
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=10.0,
    follow_redirects=True
)

process_pool = ThreadPoolExecutor(max_workers=4)

def load_unicode_font(size, font_file=FONT_FILE):
    try:
        font_path = os.path.join(os.path.dirname(__file__), font_file)
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    except:
        pass
    return ImageFont.load_default()

async def fetch_image_bytes(item_id, is_avatar=False):
    """Busca imagem da nova URL base com alta qualidade"""
    if not item_id or str(item_id) == "0":
        if is_avatar:
            item_id = DEFAULT_AVATAR_ID
        else:
            return None
    
    # Tenta buscar da nova URL primeiro
    url = f"{IMAGE_BASE_URL}/{item_id}.png"
    try:
        resp = await client.get(url)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except:
        pass
    
    # Se falhar, tenta da URL antiga como fallback
    try:
        url = f"{info_URL}/{item_id}.png"
        resp = await client.get(url)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except:
        pass
    
    return None

def bytes_to_image(img_bytes, high_quality=True):
    """Converte bytes para imagem com opção de alta qualidade"""
    if img_bytes:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
        # Aplicar filtro de suavização se necessário
        if high_quality and img.size[0] < 200:
            img = img.filter(ImageFilter.SMOOTH_MORE)
        return img
    return Image.new("RGBA", (100, 100), (0, 0, 0, 0))

def resize_image_high_quality(img, target_size, is_banner=False):
    """Redimensiona imagem com alta qualidade"""
    original_w, original_h = img.size
    
    # Calcular proporção
    ratio = target_size / original_h
    new_w = int(original_w * ratio)
    
    # Usar LANCZOS para melhor qualidade
    if is_banner:
        # Para banners, usar redimensionamento progressivo para melhor qualidade
        img = img.resize((new_w, target_size), Image.Resampling.LANCZOS)
    else:
        # Para avatares, redimensionar mantendo qualidade
        img = img.resize((new_w, target_size), Image.Resampling.LANCZOS)
    
    return img

# ================= IMAGE PROCESS =================
def process_banner_image(data, avatar_bytes, banner_bytes, pin_bytes):
    avatar_img = bytes_to_image(avatar_bytes, high_quality=True)
    banner_img = bytes_to_image(banner_bytes, high_quality=True)
    pin_img = bytes_to_image(pin_bytes, high_quality=True)

    level = str(data.get("AccountLevel", "0"))
    name = data.get("AccountName", "Unknown")
    guild = data.get("GuildName", "")

    global TARGET_HEIGHT

    # ================= AVATAR PROCESSING (ALTA QUALIDADE) =================
    
    # Redimensionar avatar com alta qualidade
    avatar_img = resize_image_high_quality(avatar_img, TARGET_HEIGHT, is_banner=False)
    av_w, av_h = avatar_img.size
    # ================================================================

    # Process Banner (alta qualidade)
    if banner_img.size == (100, 100) and banner_bytes is None:
        banner_img = bytes_to_image(banner_bytes)
    
    b_w, b_h = banner_img.size
    if b_w > 50 and b_h > 50:
        # Rotacionar com alta qualidade
        banner_img = banner_img.rotate(3, expand=True, resample=Image.Resampling.BICUBIC)
        b_w, b_h = banner_img.size
        
        # Crop com precisão
        crop_left = b_w * BANNER_START_X
        crop_top = b_h * BANNER_START_Y
        crop_right = b_w * BANNER_END_X
        crop_bottom = b_h * BANNER_END_Y

        banner_img = banner_img.crop((
            int(crop_left),
            int(crop_top),
            int(crop_right),
            int(crop_bottom)
        ))

    b_w, b_h = banner_img.size
    # Redimensionar banner com alta qualidade
    new_banner_w = int(TARGET_HEIGHT * (b_w / b_h) * 2) if b_h else TARGET_HEIGHT * 2
    banner_img = resize_image_high_quality(banner_img, TARGET_HEIGHT, is_banner=True)
    
    # Ajustar largura do banner se necessário
    if banner_img.size[0] < new_banner_w:
        banner_img = banner_img.resize((new_banner_w, TARGET_HEIGHT), Image.Resampling.LANCZOS)

    final_w = av_w + banner_img.size[0]
    combined = Image.new("RGBA", (final_w, TARGET_HEIGHT), (0, 0, 0, 0))
    
    # Colar imagens com máscara para transparência
    combined.paste(avatar_img, (0, 0), avatar_img if avatar_img.mode == 'RGBA' else None)
    combined.paste(banner_img, (av_w, 0), banner_img if banner_img.mode == 'RGBA' else None)

    draw = ImageDraw.Draw(combined)

    # Fontes maiores para melhor qualidade
    font_large = load_unicode_font(250)  # Aumentado (era 125)
    font_large_cherokee = load_unicode_font(250, FONT_CHEROKEE)
    font_small = load_unicode_font(190)  # Aumentado (era 95)
    font_small_cherokee = load_unicode_font(190, FONT_CHEROKEE)
    font_level = load_unicode_font(100)  # Aumentado (era 50)

    def is_cherokee(c):
        return 0x13A0 <= ord(c) <= 0x13FF or 0xAB70 <= ord(c) <= 0xABBF

    def draw_text(x, y, text, f_main, f_alt, stroke):
        cx = x
        for ch in text:
            f = f_alt if is_cherokee(ch) else f_main
            # Stroke mais suave para texto em alta qualidade
            for dx in range(-stroke, stroke + 1):
                for dy in range(-stroke, stroke + 1):
                    draw.text((cx + dx, y + dy), ch, font=f, fill="black")
            draw.text((cx, y), ch, font=f, fill="white")
            cx += f.getlength(ch)

    # Ajustar posições para a nova escala
    draw_text(av_w + 130, 80, name, font_large, font_large_cherokee, 8)  # Posições ajustadas
    draw_text(av_w + 130, 440, guild, font_small, font_small_cherokee, 6)

    # Processar PIN com alta qualidade
    if pin_img.size != (100, 100):
        pin_size = int(260 * (TARGET_HEIGHT / 400))  # Escalar proporcionalmente
        pin_img = pin_img.resize((pin_size, pin_size), Image.Resampling.LANCZOS)
        combined.paste(pin_img, (0, TARGET_HEIGHT - pin_size), pin_img)

    # Nível com melhor qualidade
    lvl_text = f"Lvl.{level}"
    w, h = draw.textbbox((0, 0), lvl_text, font=font_level)[2:]
    
    # Fundo mais suave para o texto do nível
    padding = 20
    draw.rectangle(
        [final_w - w - 120, TARGET_HEIGHT - h - 100, final_w + padding, TARGET_HEIGHT + padding],
        fill="black"
    )
    # Borda mais suave
    for i in range(3):
        draw.text(
            (final_w - w - 60 + i, TARGET_HEIGHT - h - 80 + i),
            lvl_text,
            font=font_level,
            fill="black"
        )
    draw.text(
        (final_w - w - 60, TARGET_HEIGHT - h - 80),
        lvl_text,
        font=font_level,
        fill="white"
    )

    # Aplicar filtro de nitidez final
    combined = combined.filter(ImageFilter.SHARPEN)

    img_io = io.BytesIO()
    # Salvar com alta qualidade
    combined.save(img_io, "PNG", optimize=True, quality=TARGET_QUALITY)
    img_io.seek(0)
    return img_io

@app.get("/")
async def home():
    return {"status": "Banner API Running (High Quality)", "endpoint": "/profile?uid=UID"}

@app.get("/profile")
async def get_banner(uid: str):
    if not uid:
        raise HTTPException(status_code=400, detail="UID required")

    # Buscar dados da nova API
    resp = await client.get(f"{INFO_API_URL}?id={uid}&region=BR&key={API_KEY}")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Info API Error")

    data = resp.json()
    
    if not data.get("success"):
        raise HTTPException(status_code=404, detail="Account not found")

    player_data = data.get("data", {})
    basic_info = player_data.get("basicInfo", {})
    clan_info = player_data.get("clanBasicInfo", {})

    # Extrair os IDs necessários
    avatar_id = basic_info.get("headPic", DEFAULT_AVATAR_ID)
    banner_id = basic_info.get("bannerId")
    pin_id = basic_info.get("badgeId", "0")

    # Se não tiver banner ID, usa o padrão
    if not banner_id or str(banner_id) == "0":
        banner_id = DEFAULT_BANNER_ID

    print(f"Avatar ID: {avatar_id}")  # Debug
    print(f"Banner ID: {banner_id}")  # Debug
    print(f"Pin ID: {pin_id}")  # Debug

    # Buscar imagens (marcando avatar para tratamento especial)
    avatar_task = fetch_image_bytes(avatar_id, is_avatar=True)
    banner_task = fetch_image_bytes(banner_id)
    pin_task = fetch_image_bytes(pin_id)

    avatar, banner, pin = await asyncio.gather(avatar_task, banner_task, pin_task)

    banner_data = {
        "AccountLevel": basic_info.get("level", "0"),
        "AccountName": basic_info.get("nickname", "Unknown"),
        "GuildName": clan_info.get("clanName", "")
    }

    loop = asyncio.get_event_loop()
    img_io = await loop.run_in_executor(process_pool, process_banner_image, banner_data, avatar, banner, pin)

    return Response(content=img_io.getvalue(), media_type="image/png", headers={"Cache-Control": "public, max-age=300"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)
