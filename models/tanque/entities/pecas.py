"""Peças de tanque."""

import json
from datetime import datetime

from models.concreto import qualidade_peca_remover_data_producao_de_dados_adicionais
from models.database import db


class TanquesPecas(db.Model):
    __tablename__ = 'TanquesPecas'

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(50), nullable=False)
    altura = db.Column(db.DECIMAL(10, 2), nullable=True)
    nome = db.Column(db.String(100), nullable=False)
    numero_sequencial = db.Column(db.Integer, nullable=False)
    numero_tanque = db.Column(db.Integer, nullable=True)
    volume = db.Column(db.DECIMAL(10, 2), nullable=True)
    data_prevista = db.Column(db.DateTime, nullable=True)
    data_concretagem = db.Column(db.DateTime, nullable=True)
    data_entrega = db.Column(db.DateTime, nullable=True)
    qualidade = db.Column(db.String(1000), nullable=True)

    # Relacionamento com tanque
    tanque_id = db.Column(db.Integer, db.ForeignKey('Tanques.id', ondelete='CASCADE'), nullable=False)
    tanque = db.relationship('Tanques', backref=db.backref('TanquesPecas', lazy=True, cascade='all, delete-orphan'))

    # Campos de auditoria
    data_cadastro = db.Column(db.DateTime, default=datetime.now)
    ultima_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.qualidade:
            self.qualidade = json.dumps({'data_producao': None,
                                         'acabamento': None,
                                         'transporte': {
                                            'data_transporte': None,
                                            'placas': None,
                                            'nota': None,
                                            'placa_carreta': None,
                                            'transportadora': None,
                                         },
                                         'series': [],
                                         'chapa': None,
                                         }, ensure_ascii=False)
    def save(self):
        # Se for uma nova peça, atribui o próximo número sequencial
        if not self.id and not self.numero_sequencial:
            # Encontra o maior número sequencial para o tanque atual
            maior_sequencial = db.session.query(db.func.max(TanquesPecas.numero_sequencial))\
                .filter(TanquesPecas.tanque_id == self.tanque_id).scalar() or 0
            # Incrementa para obter o próximo número
            self.numero_sequencial = maior_sequencial + 1

        # Nova peça: data_producao só na raiz do JSON (evita duplicar em dados_adicionais)
        if not self.id:
            if not self.qualidade:
                qualidade_dict = {'data_producao': None}
                self.qualidade = json.dumps(qualidade_dict, ensure_ascii=False)
            else:
                try:
                    qualidade_dict = json.loads(self.qualidade) if isinstance(self.qualidade, str) else self.qualidade
                    if not isinstance(qualidade_dict, dict):
                        qualidade_dict = {}
                    if 'data_producao' not in qualidade_dict:
                        qualidade_dict['data_producao'] = None
                    qualidade_peca_remover_data_producao_de_dados_adicionais(qualidade_dict)
                    self.qualidade = json.dumps(qualidade_dict, ensure_ascii=False)
                except (json.JSONDecodeError, TypeError):
                    qualidade_dict = {'data_producao': None}
                    self.qualidade = json.dumps(qualidade_dict, ensure_ascii=False)

        if not self.id:
            db.session.add(self)
        db.session.commit()
        return self

    def delete(self):
        db.session.delete(self)
        db.session.commit()
        return self

    def __repr__(self):
        return f'<Peca {self.nome} ({self.tipo}) - #{self.numero_sequencial}>'

    def produzir(self):
        """
        Produz a peça
        """
        if not self.qualidade:
            return False
        qualidade = json.loads(self.qualidade)
        if qualidade and 'data_producao' in qualidade:
            return True

    def get_series_de_pecas(self):
        """
        Retorna as séries de peças do tanque
        """
        try:
            qualidade = json.loads(self.qualidade)
            if qualidade and 'series' in qualidade:
                return qualidade['series']
            return []
        except (json.JSONDecodeError, TypeError, AttributeError):
            return []
    def set_acabamento(self, data_acabamento):
        from models.tanque.services.qualidade import peca_in_concretagem
        if not peca_in_concretagem(self):
            raise ValueError('Peça não está em alguma concretagem')
        qualidade = json.loads(self.qualidade)
        qualidade['acabamento'] = data_acabamento
        self.qualidade = json.dumps(qualidade)
        self.save()
    def set_transporte(self, data_transporte, nota_fiscal, placa_carreta, transportadora):
        from models.tanque.services.qualidade import peca_in_concretagem
        if not peca_in_concretagem(self) :
            raise ValueError('Peça não está em alguma concretagem')
        qualidade = json.loads(self.qualidade)
        if not qualidade['acabamento']:
            raise ValueError('Peça não tem acabamento')
        qualidade['transporte'] = {
            'data_transporte': data_transporte,
            'nota': nota_fiscal,
            'placa_carreta': placa_carreta,
            'transportadora': transportadora
        }
        self.qualidade = json.dumps(qualidade)
        self.save()
    def is_PF(self):
        return self.tipo == 'PF'

    def to_dict(self):
        """
        Retorna um dicionário com os campos da peça
        """
        return {
            'id': self.id,
            'nome': self.nome,
            'tipo': self.tipo,
            'numero_sequencial': self.numero_sequencial,
            'numero_tanque': self.numero_tanque,
            'volume': self.volume,
            'data_prevista': self.data_prevista,
            'data_concretagem': self.data_concretagem,
            'data_entrega': self.data_entrega,
            'qualidade': self.qualidade,
        }
