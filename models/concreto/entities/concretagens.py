"""Concretagens de peças e associação com tanques."""

from datetime import datetime

from flask import json
from flask_login import current_user
from sqlalchemy.sql import func

from models.database import db

from ..services.producao_pecas import processar_producao_por_pecas
from ..utils.qualidade import peca_obj_ja_produzida


class ConcretoConcretagens(db.Model):
    """
    Modelo para representar concretagens de peças de tanques
    """
    __tablename__ = 'ConcretoConcretagens'

    id = db.Column(db.Integer, primary_key=True)
    data_concretagem = db.Column(db.Date, nullable=False)
    observacoes = db.Column(db.Text, nullable=True)

    # Novo campo para pista (1 ou 2)
    pista = db.Column(db.String(11), nullable=False)
    cordoalhas = db.Column(db.String(1000), nullable=True)
    pecas = db.Column(db.String(1000), nullable=True)
    # Datas de controle
    data_cadastro = db.Column(db.DateTime, default=datetime.now)
    ultima_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    conc = db.Column(db.Integer, nullable=True)
    # Relacionamentos
    tanques_associados = db.relationship("ConcretoConcretagensTanques", back_populates="concretagem", cascade="all, delete-orphan")

    def get_volume_total(self):
        """
        Retorna o volume total da concretagem
        """
        from .usinagens import ConcretoUsinagens

        pecas = self.get_pecas()
        if not pecas:
            return 0
        series = []
        from models.tanque import TanquesPecas
        for peca in pecas:
            peca = TanquesPecas.query.filter(TanquesPecas.nome == peca['nome'], TanquesPecas.tanque_id == peca['tanque_id']).first()
            if peca:
                seriesb = peca.get_series_de_pecas()
                if not seriesb:
                    continue
                for seriea in seriesb:
                    if isinstance(seriea, dict):
                        seriea = seriea['serie']
                    series.append(seriea)

        print(f'[_get_volume_total] Series: {series}')
        volume_total = db.session.query(func.sum(ConcretoUsinagens.volume)).\
            filter(ConcretoUsinagens.serie.in_(series)).scalar() or 0
        return volume_total

    def get_pecas(self):
        """
        Retorna as peças da concretagem
        """
        try:
            import json
            pecas_str = self.pecas
            if not pecas_str:
                return []
            pecas_json = json.loads(pecas_str) if isinstance(pecas_str, str) else pecas_str
            if isinstance(pecas_json, list):
                return pecas_json
            return []
        except (json.JSONDecodeError, TypeError, AttributeError):
            return []

    def get_tanques_ids(self):
        """
        Retorna os IDs dos tanques associados à concretagem
        """
        pecas = self.get_pecas()
        tanques_ids = []
        if pecas:
            for peca in pecas:
                if peca['tanque_id'] not in tanques_ids:
                    tanques_ids.append(peca['tanque_id'])
        return tanques_ids

    def get_quantidade_pecas_json(self):
        """
        Retorna a quantidade de peças armazenadas no campo JSON 'pecas'
        """
        try:
            import json
            pecas_str = self.pecas
            if not pecas_str:
                return 0
            pecas_json = json.loads(pecas_str) if isinstance(pecas_str, str) else pecas_str
            if isinstance(pecas_json, list):
                return len(pecas_json)
            return 0
        except (json.JSONDecodeError, TypeError, AttributeError):
            return 0

    def adicionar_tanque(self, tanque: 'ConcretoConcretagensTanques'):
        """Adiciona um tanque à concretagem"""
        for ct in self.tanques_associados:
            if ct.tanque_id == tanque.id:
                return

        associacao = ConcretoConcretagensTanques(tanque=tanque)
        self.tanques_associados.append(associacao)

    def remover_tanque(self, tanque):
        """Remove um tanque da concretagem"""
        for ct in self.tanques_associados:
            if ct.tanque_id == tanque.id:
                self.tanques_associados.remove(ct)
                break

    def save(self):
        """Salva a concretagem no banco de dados"""
        if not self.id:
            db.session.add(self)
        db.session.commit()
        return self

    def delete(self):
        """Remove a concretagem do banco de dados"""
        db.session.delete(self)
        db.session.commit()
        return self

    def __repr__(self):
        return f'<ConcretoConcretagens {self.id} - Pista {self.pista} - {self.data_concretagem}>'

    def produzir(self):
        """
        Produz a concretagem
        """

        pecas_str = self.pecas
        if not pecas_str:
            return False
        pecas = json.loads(pecas_str) if isinstance(pecas_str, str) else pecas_str
        if not pecas:
            return False
        print(f"[_produzir] Pecas: {pecas}")
        from models.tanque import TanquesPecas
        pecas_concretadas = []
        for peca in pecas:
            if peca.get('peca_id'):
                peca_obj = TanquesPecas.query.filter_by(id=peca['peca_id']).first()
            else:
                peca_obj = TanquesPecas.query.filter_by(nome=peca['nome'], tanque_id=int(peca['tanque_id'])).first()
            if not peca_obj:
                continue
            pecas_concretadas.append(peca_obj)
        pecas_pendentes = [p for p in pecas_concretadas if not peca_obj_ja_produzida(p)]
        if not pecas_pendentes:
            if not pecas_concretadas:
                return False
            return None
        ok = processar_producao_por_pecas(
            pecas_list=pecas_pendentes,
            usuario_id=current_user.id or None,
            log=False,
            _usinagem=True)
        return bool(ok)


class ConcretoConcretagensTanques(db.Model):
    """
    Modelo para associação entre concretagem e tanques
    """
    __tablename__ = 'ConcretoConcretagensTanques'

    concretagem_id = db.Column(db.Integer, db.ForeignKey('ConcretoConcretagens.id', ondelete='CASCADE'), primary_key=True)
    tanque_id = db.Column(db.Integer, db.ForeignKey('Tanques.id', ondelete='CASCADE'), primary_key=True)

    concretagem = db.relationship("ConcretoConcretagens", back_populates="tanques_associados")
    tanque = db.relationship("Tanques")

    def __repr__(self):
        return f'<ConcretoConcretagensTanques {self.concretagem_id}-{self.tanque_id}>'
