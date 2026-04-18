"""Parsing de datas para estatísticas e filtros."""

from datetime import date, datetime


def parse_data_ate(value):
    """Converte valor para date para comparação; retorna None se inválido."""
    if value is None:
        return None
    if isinstance(value, date):
        return value if not isinstance(value, datetime) else value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value.strip() not in ('', 'null'):
        s = value.strip()
        s_date = s[:10] if len(s) >= 10 else s
        for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                d = datetime.strptime(s_date, fmt)
                return d.date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(s.replace('Z', '+00:00')).date()
        except (ValueError, AttributeError):
            pass
    return None
