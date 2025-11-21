from datetime import datetime
from models.database import db
from sqlalchemy.orm import relationship

class MaterialTanque(db.Model):
    """
    Modelo para relacionar Material com dados básicos do tanque
    Armazena informações sobre materiais necessários para tanques específicos
    """
    __tablename__ = 'materiais_tanques'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Relacionamento com Material
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id'), nullable=False)
    material = relationship('Material', backref='tanques_relacionados')
    
    # Relacionamento com Tanque
    tanque_id = db.Column(db.Integer, db.ForeignKey('tanques.id'), nullable=False)
    tanque = relationship('Tanque', backref='materiais_relacionados')
    
    # Dados básicos do tanque no momento da criação do relacionamento
    quantidade_total = db.Column(db.Integer, nullable=False, default=1)
    placas_normais = db.Column(db.Integer, nullable=True, default=0)
    placas_fecho = db.Column(db.Integer, nullable=True, default=0)
    quantidade_bainhas = db.Column(db.Integer, nullable=True, default=0)
    altura_total = db.Column(db.Float, nullable=False)
    sistema = db.Column(db.String(10), nullable=False)  # SC-10, SC-14, SR-06
    
    # Quantidade do material necessária para este tanque
    quantidade_material = db.Column(db.Float, nullable=False, default=1.0)
    
    # Observações ou notas adicionais
    observacoes = db.Column(db.Text, nullable=True)
    
    # Campos de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __init__(self, material_id, tanque_id, quantidade_total=1, placas_normais=0, 
                 placas_fecho=0, quantidade_bainhas=0, altura_total=0, sistema='', 
                 quantidade_material=None, observacoes=None, calcular_automatico=True, material_obj=None):
        self.material_id = material_id
        self.tanque_id = tanque_id
        self.quantidade_total = quantidade_total
        self.placas_normais = placas_normais or 0
        self.placas_fecho = placas_fecho or 0
        self.quantidade_bainhas = quantidade_bainhas or 0
        self.altura_total = altura_total
        self.sistema = sistema
        
        # Se calcular_automatico for True e o material tiver fórmula universal, calcular automaticamente
        if calcular_automatico:
            # Usar material_obj se fornecido, senão tentar carregar
            material = material_obj
            if not material:
                from models.material import Material
                material = Material.query.get(material_id)
            
            if material and material.formula_calculo:
                # Usar a fórmula universal do material com os dados específicos deste tanque
                self.quantidade_material = material.calcular_quantidade(
                    quantidade_total, placas_normais, placas_fecho, quantidade_bainhas, altura_total, sistema
                )
            else:
                self.quantidade_material = quantidade_material if quantidade_material is not None else 1.0
        else:
            self.quantidade_material = quantidade_material if quantidade_material is not None else 1.0
        
        self.observacoes = observacoes
    
    def to_dict(self):
        """
        Retorna um dicionário com os campos do relacionamento
        """
        return {
            'id': self.id,
            'material_id': self.material_id,
            'material_nome': self.material.nome if self.material else None,
            'tanque_id': self.tanque_id,
            'tanque_nome': self.tanque.nome if self.tanque else None,
            'quantidade_total': self.quantidade_total,
            'placas_normais': self.placas_normais,
            'placas_fecho': self.placas_fecho,
            'quantidade_bainhas': self.quantidade_bainhas,
            'altura_total': self.altura_total,
            'sistema': self.sistema,
            'quantidade_material': self.quantidade_material,
            'observacoes': self.observacoes,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
            'atualizado_em': self.atualizado_em.isoformat() if self.atualizado_em else None
        }
    
    def save(self):
        """
        Salva o relacionamento no banco de dados
        """
        db.session.add(self)
        db.session.commit()
        return self
    
    def delete(self):
        """
        Remove o relacionamento do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
        return self
    
    def __repr__(self):
        """
        Representação em string do relacionamento
        """
        material_nome = self.material.nome if self.material else 'N/A'
        tanque_nome = self.tanque.nome if self.tanque else 'N/A'
        return f'<MaterialTanque {self.id} - Material: {material_nome}, Tanque: {tanque_nome}>'

