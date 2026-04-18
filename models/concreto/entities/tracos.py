"""Traços de concreto e itens (materiais por m³)."""

from datetime import datetime

from models.database import db


class ConcretoTracos(db.Model):
    """
    Modelo para representar traços de concreto
    """
    __tablename__ = 'ConcretoTracos'

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    resistencia = db.Column(db.String(20), nullable=False)  # Exemplo: 30 MPa
    tipo_abatimento = db.Column(db.String(10), nullable=True)  # 'slump' ou 'flow'
    valor_abatimento = db.Column(db.String(20), nullable=True)  # Valor do abatimento
    relacao_agua_cimento = db.Column(db.Numeric(5, 2), nullable=True)
    status = db.Column(db.String(20), default='Ativo')  # Ativo, Inativo
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    itens = db.relationship('ConcretoTracosItens', backref='traco', cascade='all, delete-orphan')

    def adicionar_material(self, material, quantidade, unidade=None, influenciado_umidade=False):
        """Adiciona um material ao traço de concreto"""
        if not unidade:
            unidade = material.unidade

        print(f"Chamada adicionar_material: material={material.id} ({material.nome}), quantidade={quantidade}, unidade={unidade}, influenciado_umidade={influenciado_umidade}")

        item_existente = None
        for item in self.itens:
            if item.material_id == material.id:
                item_existente = item
                break

        if item_existente:
            print(f"Material {material.id} ({material.nome}) já existe no traço, atualizando")
            item_existente.quantidade = quantidade
            item_existente.unidade = unidade
            item_existente.influenciado_umidade = influenciado_umidade
            return item_existente
        else:
            print(f"Adicionando novo material {material.id} ({material.nome}) ao traço")
            if not self.id:
                db.session.add(self)
                db.session.flush()

            item = ConcretoTracosItens(
                traco_id=self.id,
                material=material,
                quantidade=quantidade,
                unidade=unidade,
                influenciado_umidade=influenciado_umidade,
                material_agrupado_id=None,
                ordem_pesagem=0
            )
            self.itens.append(item)

            db.session.add(item)
            db.session.flush()

            print(f"Material adicionado com ID={item.id}")
            return item

    def remover_material(self, material_id):
        """Remove um material do traço de concreto"""
        for item in self.itens:
            if item.material_id == material_id:
                self.itens.remove(item)
                return True
        return False

    def save(self):
        """Salva o traço de concreto no banco de dados"""
        if not self.id:
            db.session.add(self)
            db.session.flush()

        for item in self.itens:
            if not item.traco_id:
                item.traco_id = self.id
            db.session.add(item)

        db.session.commit()
        return self

    def delete(self):
        """Remove o traço de concreto do banco de dados"""
        db.session.delete(self)
        db.session.commit()
        return self

    def __repr__(self):
        return f'<TracoConcreto {self.codigo} - {self.nome}>'


class ConcretoTracosItens(db.Model):
    """
    Modelo para representar itens de um traço de concreto
    """
    __tablename__ = 'ConcretoTracosItens'

    id = db.Column(db.Integer, primary_key=True)
    traco_id = db.Column(db.Integer, db.ForeignKey('ConcretoTracos.id', ondelete='CASCADE'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('Materiais.id'), nullable=False)
    quantidade = db.Column(db.Numeric(10, 2), nullable=False)  # Quantidade por m³
    conversao_unidade_id = db.Column(db.Integer, db.ForeignKey('UnidadesConversao.id'), nullable=True)
    unidade_id = db.Column(db.Integer, db.ForeignKey('Unidades.id'), nullable=False)
    influenciado_umidade = db.Column(db.Boolean, default=False)
    material_agrupado_id = db.Column(db.Integer, db.ForeignKey('ConcretoTracosItens.id'), nullable=True)
    ordem_pesagem = db.Column(db.Integer, default=0)
    criado_em = db.Column(db.DateTime, default=datetime.now)

    material = db.relationship('Materiais', foreign_keys=[material_id], backref=db.backref('itens_traco', lazy='dynamic'))

    unidade = db.relationship('Unidades', foreign_keys=[unidade_id], backref=db.backref('itens_traco', lazy='dynamic'))

    material_agrupado = db.relationship('ConcretoTracosItens', remote_side=[id], backref=db.backref('materiais_associados', lazy='dynamic'))

    conversao_unidade = db.relationship(
        'UnidadesConversao',
        foreign_keys=[conversao_unidade_id],
        backref=db.backref('itens_traco', lazy='dynamic'))

    def __repr__(self):
        return f'<ItemTracoConcreto {self.id} - Material: {self.material_id}, Quantidade: {self.quantidade} {self.unidade.nome if self.unidade else "N/A"}>'
