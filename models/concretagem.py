from datetime import datetime
from models.database import db

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
    pista = db.Column(db.String(11), nullable=False)
    cordoalhas = db.Column(db.String(1000), nullable=True)
    pecas = db.Column(db.String(1000), nullable=True)
    # Datas de controle
    data_cadastro = db.Column(db.DateTime, default=datetime.now)
    ultima_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    tanques_associados = db.relationship("ConcretagemTanque", back_populates="concretagem", cascade="all, delete-orphan")
   
    def get_quantidade_pecas_json(self):
        """
        Retorna a quantidade de peças armazenadas no campo JSON 'pecas'
        """
        try:
            import json
            # Acessa o campo da coluna diretamente via __dict__ para evitar conflito com a propriedade @property
            pecas_str = self.pecas
            if not pecas_str:
                return 0
            pecas_json = json.loads(pecas_str) if isinstance(pecas_str, str) else pecas_str
            if isinstance(pecas_json, list):
                return len(pecas_json)
            return 0
        except (json.JSONDecodeError, TypeError, AttributeError):
            return 0
    
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