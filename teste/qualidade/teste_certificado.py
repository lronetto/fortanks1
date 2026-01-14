import cv2
import pytesseract
import pandas as pd
import numpy as np
from pdf2image import convert_from_path

PDF_PATH = "CERT. CORDOALHA  - 1061132969 NUA 12,70mm.pdf"

# Caso esteja no Windows, ajuste o caminho:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# --- 1. Converter SOMENTE a página 2 ---
pages = convert_from_path(PDF_PATH, dpi=300, first_page=2, last_page=2)
image = np.array(pages[0])

# --- 2. Pré-processamento ---
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
thresh = cv2.adaptiveThreshold(
    gray, 255,
    cv2.ADAPTIVE_THRESH_MEAN_C,
    cv2.THRESH_BINARY_INV,
    15, 5
)

# --- 3. Detectar linhas da tabela ---
kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))

horizontal = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_h)
vertical = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_v)

table_mask = cv2.add(horizontal, vertical)

# --- 4. Encontrar células ---
contours, _ = cv2.findContours(
    table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
)

cells = []
for cnt in contours:
    x, y, w, h = cv2.boundingRect(cnt)
    if w > 80 and h > 25:  # filtros para ignorar ruído
        cells.append((x, y, w, h))

# Ordenar por linhas (y) e colunas (x)
cells = sorted(cells, key=lambda b: (b[1], b[0]))

# --- 5. OCR célula por célula ---
rows = []
current_row = []
last_y = -1

for x, y, w, h in cells:
    roi = gray[y:y+h, x:x+w]
    text = pytesseract.image_to_string(
        roi,
        lang="por",
        config="--psm 6"
    ).strip()

    if last_y == -1 or abs(y - last_y) < 15:
        current_row.append(text)
    else:
        rows.append(current_row)
        current_row = [text]

    last_y = y

if current_row:
    rows.append(current_row)

# --- 6. Criar DataFrame ---
df = pd.DataFrame(rows)
df.to_csv("tabela_pagina2_ocr.csv", index=False)

print(df)
