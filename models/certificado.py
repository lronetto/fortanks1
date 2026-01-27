from datetime import datetime
from models.database import db
from sqlalchemy import Text, ForeignKey
from sqlalchemy.orm import relationship
import json

class Certificados(db.Model):
    """
    Modelo para representar certificados
    """
    __tablename__ = 'Certificados'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(255), nullable=False)
    tipo = db.Column(db.String(100), nullable=True)  # Mantido para compatibilidade
    tipo_id = db.Column(db.Integer, ForeignKey('CertificadosTipos.id'), nullable=True)
    data = db.Column(db.Date, nullable=True)
    data_vencimento = db.Column(db.Date, nullable=True)
    dados_adicionais = db.Column(Text, nullable=True)  # JSON como string
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    ativo = db.Column(db.Boolean, default=True)
    
    # Relacionamento com tipo de certificado
    tipo_certificado = relationship('CertificadosTipos', foreign_keys=[tipo_id], backref='certificados')
    
    def to_dict(self):
        """
        Converte o objeto certificado para um dicionário
        """
        dados_adicionais_dict = {}
        if self.dados_adicionais:
            try:
                dados_adicionais_dict = json.loads(self.dados_adicionais)
            except:
                dados_adicionais_dict = {}
        
        return {
            'id': self.id,
            'nome': self.nome,
            'tipo': self.tipo,
            'tipo_id': self.tipo_id,
            'tipo_nome': self.tipo_certificado.nome if self.tipo_certificado else None,
            'data': self.data.strftime('%Y-%m-%d') if self.data else None,
            'data_vencimento': self.data_vencimento.strftime('%Y-%m-%d') if self.data_vencimento else None,
            'dados_adicionais': dados_adicionais_dict,
            'criado_em': self.criado_em.strftime('%Y-%m-%d %H:%M:%S') if self.criado_em else None,
            'atualizado_em': self.atualizado_em.strftime('%Y-%m-%d %H:%M:%S') if self.atualizado_em else None,
            'ativo': self.ativo
        }
    
    def get_dados_adicionais(self):
        """
        Retorna os dados adicionais como dicionário Python
        """
        if self.dados_adicionais:
            try:
                return json.loads(self.dados_adicionais)
            except:
                return {}
        return {}
    
    def set_dados_adicionais(self, dados):
        """
        Define os dados adicionais a partir de um dicionário Python
        """
        if dados:
            self.dados_adicionais = json.dumps(dados, ensure_ascii=False)
        else:
            self.dados_adicionais = None
    
    def save(self):
        """
        Salva o certificado no banco de dados
        """
        if not self.id:
            db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o certificado do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    
    def __repr__(self):
        return f'<Certificado {self.id} - {self.nome}>'

class CertificadosTipos(db.Model):
    """
    Modelo para representar tipos de certificados
    """
    __tablename__ = 'CertificadosTipos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(255), nullable=False, unique=True)
    dados_adicionais = db.Column(Text, nullable=True)  # JSON como string - define os campos específicos
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    ativo = db.Column(db.Boolean, default=True)
    
    def to_dict(self):
        """
        Converte o objeto tipo certificado para um dicionário
        """
        dados_adicionais_dict = {}
        if self.dados_adicionais:
            try:
                dados_adicionais_dict = json.loads(self.dados_adicionais)
            except:
                dados_adicionais_dict = {}
        
        return {
            'id': self.id,
            'nome': self.nome,
            'dados_adicionais': dados_adicionais_dict,
            'criado_em': self.criado_em.strftime('%Y-%m-%d %H:%M:%S') if self.criado_em else None,
            'atualizado_em': self.atualizado_em.strftime('%Y-%m-%d %H:%M:%S') if self.atualizado_em else None,
            'ativo': self.ativo
        }
    
    def get_dados_adicionais(self):
        """
        Retorna os dados adicionais como dicionário Python
        """
        if self.dados_adicionais:
            try:
                return json.loads(self.dados_adicionais)
            except:
                return {}
        return {}
    
    def set_dados_adicionais(self, dados):
        """
        Define os dados adicionais a partir de um dicionário Python
        """
        if dados:
            self.dados_adicionais = json.dumps(dados, ensure_ascii=False)
        else:
            self.dados_adicionais = None
    
    def save(self):
        """
        Salva o tipo de certificado no banco de dados
        """
        if not self.id:
            db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o tipo de certificado do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    
    def __repr__(self):
        return f'<CertificadosTipos {self.id} - {self.nome}>'
