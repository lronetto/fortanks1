from datetime import datetime
from models.database import db

# Criando uma classe de associação entre concretagem e peças
class ConcretagemPeca(db.Model):
    """
    Modelo para associação entre concretagem e peças, incluindo a forma
    """
    __tablename__ = 'ConcPecas'
    
    concretagem_id = db.Column(db.Integer, db.ForeignKey('Conc.id', ondelete='CASCADE'), primary_key=True)
    peca_id = db.Column(db.Integer, db.ForeignKey('pecas.id', ondelete='CASCADE'), primary_key=True)
    
    # Adicionar campo para a forma
    forma = db.Column(db.String(100), nullable=True)
    
    # Adicionar campo para usinagem de concreto
    usinagem_id = db.Column(db.Integer, db.ForeignKey('Usinagem.id'), nullable=True)
    
    # Relacionamentos
    concretagem = db.relationship("Concretagem", back_populates="pecas_associadas")
    peca = db.relationship("Peca", back_populates="concretagens_associadas")
    usinagem = db.relationship("UsinagemConcreto")
    
    def __repr__(self):
        return f'<ConcretagemPeca {self.concretagem_id}-{self.peca_id}>'

# Nova tabela de associação entre concretagem e tanques
class ConcretagemTanque(db.Model):
    """
    Modelo para associação entre concretagem e tanques
    """
    __tablename__ = 'ConcTanq'
    
    concretagem_id = db.Column(db.Integer, db.ForeignKey('Conc.id', ondelete='CASCADE'), primary_key=True)
    tanque_id = db.Column(db.Integer, db.ForeignKey('tanques.id', ondelete='CASCADE'), primary_key=True)
    
    # Relacionamentos
    concretagem = db.relationship("Concretagem", back_populates="tanques_associados")
    tanque = db.relationship("Tanque")
    
    def __repr__(self):
        return f'<ConcretagemTanque {self.concretagem_id}-{self.tanque_id}>'

class Concretagem(db.Model):
    """
    Modelo para representar concretagens de peças de tanques
    """
    __tablename__ = 'Conc'
    
    id = db.Column(db.Integer, primary_key=True)
    data_concretagem = db.Column(db.Date, nullable=False)
    observacoes = db.Column(db.Text, nullable=True)
    
    # Novo campo para pista (1 ou 2)
    pista = db.Column(db.Integer, nullable=False)
    
    # Datas de controle
    data_cadastro = db.Column(db.DateTime, default=datetime.now)
    ultima_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Nova relação com tanques usando a classe de associação
    tanques_associados = db.relationship('ConcretagemTanque', back_populates="concretagem", cascade="all, delete-orphan")
    
    # Relação com peças usando a classe de associação
    pecas_associadas = db.relationship('ConcretagemPeca', back_populates="concretagem", cascade="all, delete-orphan")
    
    # Propriedade para acesso direto às peças (compatibilidade com código existente)
    @property
    def pecas(self):
        return [cp.peca for cp in self.pecas_associadas]
    
    # Propriedade para acesso direto aos tanques
    @property
    def tanques(self):
        return [ct.tanque for ct in self.tanques_associados]
    
    def adicionar_tanque(self, tanque):
        """Adiciona um tanque à concretagem"""
        # Verificar se o tanque já existe
        for ct in self.tanques_associados:
            if ct.tanque_id == tanque.id:
                return
        
        # Adicionar nova associação
        associacao = ConcretagemTanque(tanque=tanque)
        self.tanques_associados.append(associacao)
    
    def remover_tanque(self, tanque):
        """Remove um tanque da concretagem"""
        for ct in self.tanques_associados:
            if ct.tanque_id == tanque.id:
                self.tanques_associados.remove(ct)
                break
    
    def adicionar_peca(self, peca, forma=None, usinagem=None):
        """Adiciona uma peça à concretagem com a forma especificada"""
        # Verificar se a peça já existe
        for cp in self.pecas_associadas:
            if cp.peca_id == peca.id:
                # Atualizar a forma se fornecida
                if forma:
                    cp.forma = forma
                # Atualizar a usinagem se fornecida
                if usinagem:
                    cp.usinagem_id = usinagem.id
                return
        
        # Adicionar nova associação
        associacao = ConcretagemPeca(
            peca=peca,
            forma=forma,
            usinagem_id=usinagem.id if usinagem else None
        )
        self.pecas_associadas.append(associacao)
    
    def remover_peca(self, peca):
        """Remove uma peça da concretagem"""
        for cp in self.pecas_associadas:
            if cp.peca_id == peca.id:
                self.pecas_associadas.remove(cp)
                break
    
    def get_forma_peca(self, peca_id):
        """Retorna a forma de uma peça específica"""
        for cp in self.pecas_associadas:
            if cp.peca_id == peca_id:
                return cp.forma
        return None
    
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
        return f'<Concretagem {self.id} - Pista {self.pista} - {self.data_concretagem}>' 