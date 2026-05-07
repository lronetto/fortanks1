"""ORM da tabela `documentos_sefaz`."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from models.database import db

from .constants import NOME_TABELA


class DocumentoSefaz(db.Model):
    """
    Documento fiscal (NFe/CTe/NFSe) baixado da SEFAZ Distribuição DF-e ou ADN.

    O XML em si fica armazenado como `Upload` (MinIO); o `id` do Upload
    fica em `dados_adicionais['upload_id']` para evitar coluna FK
    bidirecional.
    """

    __tablename__ = NOME_TABELA

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(10), nullable=False, index=True)  # 'nfe' | 'cte' | 'nfse'
    data = db.Column(db.DateTime, nullable=True, index=True)  # data de emissão
    fornecedor_id = db.Column(
        db.Integer, db.ForeignKey("fornecedores.id"), nullable=True, index=True
    )
    valor_total = db.Column(db.Numeric(15, 2), nullable=True)
    dados_adicionais = db.Column(db.Text, nullable=True)
    nsu = db.Column(db.String(20), nullable=True, index=True)
    chave_acesso = db.Column(db.String(50), unique=True, nullable=True, index=True)
    data_criacao = db.Column(
        db.DateTime, default=datetime.now, nullable=False, index=True
    )

    fornecedor = db.relationship("Fornecedor", lazy="joined")

    def save(self) -> "DocumentoSefaz":
        db.session.add(self)
        db.session.commit()
        return self

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tipo": self.tipo,
            "data": self.data.isoformat() if self.data else None,
            "fornecedor_id": self.fornecedor_id,
            "valor_total": float(self.valor_total) if self.valor_total else None,
            "dados_adicionais": self.dados_adicionais,
            "nsu": self.nsu,
            "chave_acesso": self.chave_acesso,
            "data_criacao": self.data_criacao.isoformat() if self.data_criacao else None,
        }

    def __repr__(self) -> str:
        return f"<DocumentoSefaz {self.id} {self.tipo} chave={self.chave_acesso} nsu={self.nsu}>"

    @classmethod
    def maior_nsu_por_tipo(cls, tipo: str) -> str:
        """Retorna o maior NSU já gravado para um tipo. '0' se não houver."""
        from sqlalchemy import func

        valor = (
            db.session.query(func.max(cls.nsu)).filter(cls.tipo == tipo).scalar()
        )
        return valor or "0"
