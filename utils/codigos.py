"""Normalização de códigos numéricos digitados em formulários."""


def normalizar_codigo_inteiro(valor) -> str:
    txt = str(valor or "").strip()
    if not txt:
        return ""
    txt = txt.replace(",", ".")
    try:
        return str(int(float(txt)))
    except (TypeError, ValueError):
        if "." in txt:
            return txt.split(".", 1)[0]
        return txt
