"""
Persistência de Protocolo e extração simples de número em PDF.
"""
import io
import logging
from datetime import datetime

from pypdf import PdfReader

from models.database import db
from models.protocolo import Protocolo

from scripts.email.texto import extrair_numero_protocolo_do_texto


def extrair_numero_protocolo_pdf(payload: bytes) -> str | None:
    """Extrai texto do PDF e tenta identificar o número do protocolo."""
    try:
        reader = PdfReader(io.BytesIO(payload))
        texto = []
        for page in reader.pages[:2]:
            try:
                texto.append(page.extract_text() or "")
            except Exception:
                continue
        joined = "\n".join(texto)
        return extrair_numero_protocolo_do_texto(joined)
    except Exception as e:
        logging.warning(f"Erro ao extrair número do protocolo do PDF: {e}")
        return None


def obter_ou_criar_protocolo_por_numero(numero: str, data: datetime | None = None) -> Protocolo:
    """Busca (ou cria) Protocolo pelo número."""
    numero = (numero or "").strip()
    if not numero:
        raise ValueError("Número do protocolo vazio")
    protocolo = Protocolo.query.filter(Protocolo.numero == numero).first()
    if protocolo:
        return protocolo
    data_prot = (data or datetime.now()).date()
    protocolo = Protocolo(data=data_prot, numero=numero)
    db.session.add(protocolo)
    db.session.commit()
    return protocolo
