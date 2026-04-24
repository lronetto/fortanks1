"""
Funções auxiliares compartilhadas entre usinagens e rompimentos
"""
from typing import Dict
import pandas as pd
from datetime import datetime, timedelta
from pypdf import PdfReader, PdfWriter
import io
import logging
import json
from decimal import Decimal
from pdf2image import convert_from_bytes
from pyzbar.pyzbar import decode
import sys
from typing import Any, Optional

def IntToStr(valor, default=None):
    """
    Converte valor (ex.: lido do Excel) para string, sem .0 no final para inteiros.
    Evita que 12345678901.0 vire "12345678901.0" ou que float inteiro vire string com .0.
    """
    if valor is None:
        return default
    if isinstance(valor, float) and pd.isna(valor):
        return default
    if isinstance(valor, float) and valor == int(valor):
        return str(int(valor))
    s = str(valor).strip()
    return s if s else default
def StrToDate(valor, default=None):
    """
    Converte valor (ex.: lido do Excel) para date.
    """
    if valor is None:
        return default
    return datetime.strptime(valor, "%d/%m/%Y").date()
def ToInt(valor, default=None):
    if valor in (None, ""):
        return default
    try:
        return int(float(valor))
    except Exception:
        return default
def ToDecimal(valor, default=Decimal("0.00")):
    if valor in (None, ""):
        return default
    try:
        return Decimal(str(valor))
    except Exception:
        return default