"""Registros de transporte de peças (lote vinculado a NF / CT-e)."""

import json
from datetime import date, datetime

from models.database import db


class TanquesTransportes(db.Model):
    """
    Um registro por operação de transporte em lote (mesma NF, data, transportadora, etc.).
    `pecas` armazena JSON com a lista de ids de TanquesPecas.
    """

    __tablename__ = "TanquesTransportes"

    id = db.Column(db.Integer, primary_key=True)
    nota = db.Column(db.Integer, nullable=True, index=True)
    cte = db.Column(db.String(64), nullable=True)
    transportadora = db.Column(db.String(255), nullable=True)
    data_transporte = db.Column(db.Date, nullable=True)
    pecas = db.Column(db.Text, nullable=True)
    # JSON: placa_carreta, cte, observacao, enviar_whatsapp, foto_upload_id (Upload tipo 10), etc.
    dados_adicionais = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def pecas_ids(self):
        if not self.pecas:
            return []
        try:
            raw = json.loads(self.pecas) if isinstance(self.pecas, str) else self.pecas
            return [int(x) for x in raw] if isinstance(raw, list) else []
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

    def definir_pecas_ids(self, ids):
        limpo = [int(x) for x in ids if x is not None]
        self.pecas = json.dumps(sorted(set(limpo)), ensure_ascii=False)

    def dados_adicionais_dict(self):
        if not self.dados_adicionais:
            return {}
        try:
            return json.loads(self.dados_adicionais) if isinstance(self.dados_adicionais, str) else self.dados_adicionais
        except (json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    def parse_nota_int(valor):
        """Número da NF como inteiro (formulário/API enviam string)."""
        if valor is None:
            return None
        s = str(valor).strip()
        if not s or s.lower() == "null":
            return None
        try:
            return int(float(s.replace(",", ".")))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def parse_data_transporte(valor):
        if valor is None or valor == "":
            return None
        if isinstance(valor, date) and not isinstance(valor, datetime):
            return valor
        if isinstance(valor, datetime):
            return valor.date()
        s = str(valor).strip()
        if not s:
            return None
        if "T" in s:
            s = s.split("T", 1)[0]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(s[:10], fmt).date()
            except ValueError:
                continue
        return None
