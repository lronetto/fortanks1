from datetime import datetime
import json
from models import db

class TipoPeca(db.Model):
    """
    Modelo para representar tipos de peças
    """
    __tablename__ = 'tipos_peca'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    volume = db.Column(db.DECIMAL(10, 2), nullable=True)
    abertura = db.Column(db.Text, nullable=True)  # Armazena JSON como texto
    
    # Campos de auditoria
    data_cadastro = db.Column(db.DateTime, default=datetime.now)
    ultima_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def get_abertura(self):
        """
        Retorna o campo abertura como dicionário Python
        """
        if self.abertura:
            try:
                return json.loads(self.abertura)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    
    def set_abertura(self, data):
        """
        Define o campo abertura a partir de um dicionário Python
        """
        if data is not None:
            self.abertura = json.dumps(data, ensure_ascii=False)
        else:
            self.abertura = None
    
    def save(self):
        """
        Salva o tipo de peça no banco de dados
        """
        if not self.id:
            db.session.add(self)
        db.session.commit()
        return self
    
    def delete(self):
        """
        Remove o tipo de peça do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
        return self
    
    def __repr__(self):
        return f'<TipoPeca {self.nome} (ID: {self.id})>'
    
    def to_dict(self):
        """
        Converte o tipo de peça para um dicionário
        """
        return {
            'id': self.id,
            'nome': self.nome,
            'volume': float(self.volume) if self.volume else None,
            'abertura': self.get_abertura(),
            'data_cadastro': self.data_cadastro.isoformat() if self.data_cadastro else None,
            'ultima_atualizacao': self.ultima_atualizacao.isoformat() if self.ultima_atualizacao else None
        }

