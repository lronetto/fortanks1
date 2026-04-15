"""Utilitários de parsing de XML / data para NF-e."""
from datetime import datetime

from dateutil.parser import isoparse


def _parse_nfe_data_emissao_xml(data_emissao_text):
    """
    Converte dhEmi (ISO-8601, ex.: 2026-04-01T09:53:00-03:00) ou dEmi (YYYY-MM-DD)
    do XML da NF-e em datetime naive, preservando hora/minuto/segundo quando existirem.
    """
    t = (data_emissao_text or "").strip()
    if not t:
        raise ValueError("data de emissão vazia")
    if "T" in t:
        dt = isoparse(t)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    return datetime.strptime(t[:10], "%Y-%m-%d")


def get_xml_text(element, xpath, ns):
    """
    Obtém texto de um elemento XML; retorna None se o elemento não existir.
    """
    if element is None:
        return None

    try:
        found = element.find(xpath, ns)
        return found.text if found is not None else None
    except Exception:
        return None
