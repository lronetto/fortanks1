"""
Modelo para vincular Cargo com período (data de referência = 1º dia do mês) e salário.
"""
from datetime import datetime, date
from sqlalchemy import UniqueConstraint
from models.database import db


class CargoSalario(db.Model):
    """
    Vincula um cargo a um período (mês/ano) com o salário vigente no período.
    """
    __tablename__ = 'cargos_salarios'
    __table_args__ = (UniqueConstraint('cargo_id', 'data', name='uq_cargo_data'),)

    id = db.Column(db.Integer, primary_key=True)
    cargo_id = db.Column(db.Integer, db.ForeignKey('cargos.id', ondelete='CASCADE'), nullable=False)
    data = db.Column(db.Date, nullable=False)  # 1º dia do mês/ano de referência
    salario = db.Column(db.Numeric(12, 2), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cargo = db.relationship('Cargo', backref=db.backref('salarios_por_periodo', lazy='dynamic'))

    @property
    def mes(self) -> int | None:
        return self.data.month if self.data else None

    @property
    def ano(self) -> int | None:
        return self.data.year if self.data else None

    def __repr__(self):
        return f'<CargoSalario cargo_id={self.cargo_id} {self.mes}/{self.ano} R$ {self.salario}>'

    def to_dict(self):
        return {
            'id': self.id,
            'cargo_id': self.cargo_id,
            'cargo_nome': self.cargo.nome if self.cargo else None,
            'data': self.data.isoformat() if self.data else None,
            'mes': self.mes,
            'ano': self.ano,
            'salario': float(self.salario) if self.salario is not None else None,
        }
