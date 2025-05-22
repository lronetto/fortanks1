from PIL import Image, ImageDraw
import os
import zipfile

# Criar diretório para imagens
image_dir = "icones"
os.makedirs(image_dir, exist_ok=True)

# Função para gerar ícone vetorial simples
def create_vector_icon(draw_func, filename, size=(64, 64), bgcolor=(30, 30, 30)):
    img = Image.new("RGB", size, bgcolor)
    draw = ImageDraw.Draw(img)
    draw_func(draw, size)
    img.save(os.path.join(image_dir, filename))

# Desenho de lâmpada
def draw_lamp(draw, size):
    w, h = size
    draw.ellipse([(w*0.25, h*0.1), (w*0.75, h*0.6)], fill=(255, 255, 100))
    draw.rectangle([(w*0.4, h*0.6), (w*0.6, h*0.8)], fill=(180, 180, 180))
    draw.line([(w*0.45, h*0.8), (w*0.55, h*0.9)], fill=(200, 200, 200), width=3)

# Desenho de sensor
def draw_sensor(draw, size):
    w, h = size
    draw.ellipse([(w*0.3, h*0.3), (w*0.7, h*0.7)], outline=(100, 200, 255), width=3)
    draw.arc([(w*0.15, h*0.15), (w*0.85, h*0.85)], start=0, end=360, fill=(100, 200, 255), width=2)
    draw.arc([(w*0.05, h*0.05), (w*0.95, h*0.95)], start=0, end=360, fill=(100, 200, 255), width=1)

# Desenho de cena (estrela)
def draw_scene(draw, size):
    w, h = size
    draw.polygon([(w*0.5, h*0.1), (w*0.6, h*0.4), (w*0.9, h*0.4),
                  (w*0.65, h*0.6), (w*0.75, h*0.9),
                  (w*0.5, h*0.7), (w*0.25, h*0.9),
                  (w*0.35, h*0.6), (w*0.1, h*0.4),
                  (w*0.4, h*0.4)], fill=(255, 180, 50))

# Desenho de casa
def draw_home(draw, size):
    w, h = size
    draw.polygon([(w*0.2, h*0.5), (w*0.5, h*0.2), (w*0.8, h*0.5)], fill=(150, 200, 255))
    draw.rectangle([(w*0.25, h*0.5), (w*0.75, h*0.85)], fill=(100, 150, 255))
    draw.rectangle([(w*0.45, h*0.65), (w*0.55, h*0.85)], fill=(255, 255, 255))

# Gerar os ícones
create_vector_icon(draw_lamp, "lamp.bmp")
create_vector_icon(draw_sensor, "sensor.bmp")
create_vector_icon(draw_scene, "scene.bmp")
create_vector_icon(draw_home, "home.bmp")

# Compactar os arquivos em um .zip
zip_path = "icones_esphome.zip"
with zipfile.ZipFile(zip_path, 'w') as zipf:
    for file in os.listdir(image_dir):
        zipf.write(os.path.join(image_dir, file), arcname=file)

print(f"Ícones gerados e compactados em: {zip_path}")
