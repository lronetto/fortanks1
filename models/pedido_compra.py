from datetime import datetime
from models.database import db
from models.upload import Upload
from sqlalchemy import func


class PedidoCompra(db.Model):
    """
    Modelo para representar Pedidos de Compra
    """
    __tablename__ = 'PedidosCompra'

    id = db.Column(db.Integer, primary_key=True)

    # Número do pedido (pode ser controlado externamente ou sequencial)
    numero = db.Column(db.String(50), unique=True, nullable=False)

    fornecedor_id = db.Column(db.Integer, db.ForeignKey('fornecedores.id'), nullable=False)
    fornecedor = db.relationship('Fornecedor', back_populates='pedidos_compra')

    centro_custo_id = db.Column(db.Integer, db.ForeignKey('centros_custo.id'), nullable=True)
    centro_custo = db.relationship('CentroCusto')

    data_liberacao = db.Column(db.DateTime, nullable=True)

    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Itens do pedido
    itens = db.relationship(
        'PedidoCompraItem',
        back_populates='pedido',
        cascade='all, delete-orphan',
        lazy='dynamic',
    )

    def save(self):
        """
        Salva o pedido de compra no banco de dados
        """
        db.session.add(self)
        db.session.commit()

    def delete(self):
        """
        Remove o pedido de compra do banco de dados
        """
        db.session.delete(self)
        db.session.commit()

    def to_dict(self, incluir_itens=True):
        """
        Converte o pedido de compra para dicionário
        """
        data = {
            'id': self.id,
            'numero': self.numero,
            'fornecedor_id': self.fornecedor_id,
            'fornecedor_nome': self.fornecedor.nome if self.fornecedor else None,
            'centro_custo_id': self.centro_custo_id,
            'centro_custo_nome': self.centro_custo.nome if getattr(self, 'centro_custo', None) else None,
            'data_liberacao': self.data_liberacao,
            'criado_em': self.criado_em,
            'atualizado_em': self.atualizado_em,
        }

        if incluir_itens:
            data['itens'] = [item.to_dict() for item in self.itens.all()]

        # Anexos relacionados no modelo Upload
        uploads = self.get_uploads()
        data['anexos'] = [
            {
                'id': up.id,
                'filename': up.filename,
                'mimetype': up.mimetype,
                'uploaded_at': up.uploaded_at,
            }
            for up in uploads
        ]

        return data

    def get_uploads(self, tipo=None):
        """
        Retorna os uploads associados a este pedido de compra
        usando o modelo Upload (pai='PedidoCompra').
        Se tipo for informado, filtra também pelo campo tipo.
        """
        query = Upload.query.filter_by(pai='PedidoCompra', pai_id=self.id)
        if tipo is not None:
            query = query.filter(Upload.tipo == tipo)
        return query.all()

    def __repr__(self):
        return f'<PedidoCompra {self.id} - {self.numero}>'


class PedidoCompraItem(db.Model):
    """
    Itens de um Pedido de Compra
    """
    __tablename__ = 'PedidosCompraItens'

    id = db.Column(db.Integer, primary_key=True)

    pedido_id = db.Column(db.Integer, db.ForeignKey('PedidosCompra.id'), nullable=False)
    pedido = db.relationship('PedidoCompra', back_populates='itens')

    material_id = db.Column(db.Integer, db.ForeignKey('Materiais.id'), nullable=False)

    # Valores de item
    valor_unitario = db.Column(db.Numeric(15, 4), nullable=False)
    quantidade = db.Column(db.Numeric(15, 4), nullable=False)
    unidade = db.Column(db.String(20), nullable=True)
    # Quantidade já entregue antes do controle por entradas (reduz o saldo disponível)
    quantidade_entregue_inicial = db.Column(db.Numeric(15, 4), default=0, nullable=False)

    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relacionamento com material
    material = db.relationship('Materiais')

    entradas = db.relationship(
        'PedidoCompraEntrada',
        back_populates='pedido_item',
        cascade='all, delete-orphan',
        lazy='dynamic',
        order_by='PedidoCompraEntrada.criado_em.desc()',
    )

    def get_quantidade_entradas_registradas(self):
        """Soma apenas das entradas registradas (NF), sem o valor inicial."""
        entradas_sum = (
            db.session.query(func.coalesce(func.sum(PedidoCompraEntrada.quantidade_entrada), 0))
            .filter(PedidoCompraEntrada.pedido_item_id == self.id)
            .scalar()
        )
        return float(entradas_sum or 0)

    def get_quantidade_entrada_total(self):
        """Soma das entradas registradas + quantidade já entregue inicial."""
        return self.get_quantidade_entradas_registradas() + float(self.quantidade_entregue_inicial or 0)

    def get_saldo(self):
        """Saldo = quantidade pedida - (entregue inicial + entradas)."""
        return float(self.quantidade or 0) - self.get_quantidade_entrada_total()

    def get_entradas_ordenadas(self):
        """Retorna entradas ordenadas por criado_em descendente."""
        return self.entradas.order_by(PedidoCompraEntrada.criado_em.desc()).all()

    def save(self):
        """
        Salva o item do pedido de compra
        """
        db.session.add(self)
        db.session.commit()

    def delete(self):
        """
        Remove o item do pedido de compra
        """
        db.session.delete(self)
        db.session.commit()

    def to_dict(self):
        """
        Converte o item para dicionário
        """
        return {
            'id': self.id,
            'pedido_id': self.pedido_id,
            'material_id': self.material_id,
            'material_nome': self.material.nome if self.material else None,
            'valor_unitario': float(self.valor_unitario) if self.valor_unitario is not None else None,
            'quantidade': float(self.quantidade) if self.quantidade is not None else None,
            'quantidade_entregue_inicial': float(self.quantidade_entregue_inicial or 0),
            'unidade': self.unidade,
            'criado_em': self.criado_em,
            'atualizado_em': self.atualizado_em,
        }

    def __repr__(self):
        return f'<PedidoCompraItem {self.id} - Pedido {self.pedido_id}>'


class PedidoCompraEntrada(db.Model):
    """
    Entradas (recebimento) de itens do Pedido de Compra.
    Vincula um item do pedido a uma Nota Fiscal e a quantidade recebida.
    """
    __tablename__ = 'PedidosCompraEntradas'

    id = db.Column(db.Integer, primary_key=True)

    pedido_item_id = db.Column(db.Integer, db.ForeignKey('PedidosCompraItens.id'), nullable=False)
    pedido_item = db.relationship('PedidoCompraItem', back_populates='entradas')

    nota_fiscal_id = db.Column(db.Integer, db.ForeignKey('NotaFiscal.id'), nullable=False)
    nota_fiscal = db.relationship('NotaFiscal')

    quantidade_entrada = db.Column(db.Numeric(15, 4), nullable=False)

    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'pedido_item_id': self.pedido_item_id,
            'nota_fiscal_id': self.nota_fiscal_id,
            'nota_fiscal_numero': self.nota_fiscal.numero_nf if self.nota_fiscal else None,
            'quantidade_entrada': float(self.quantidade_entrada) if self.quantidade_entrada is not None else None,
            'criado_em': self.criado_em,
        }

