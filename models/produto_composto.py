from datetime import datetime
from sqlalchemy import Text
from models.database import db
from models.peca import Peca
from models.material import Material
from decimal import Decimal
from models.estoque import Estoque

class ProdutoComposto(db.Model):
    """
    Modelo para representar produtos compostos para produção de peças concretadas
    """
    __tablename__ = 'ProdComp'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    tempo_producao = db.Column(db.Numeric(10, 2), nullable=True)  # Tempo estimado de produção em horas
    status = db.Column(db.String(20), default='Ativo')  # Ativo, Inativo
   
    
    # Campos para armazenar a imagem
    imagem = db.Column(db.Text(length=4294967295), nullable=True)
    imagem_mime_type = db.Column(db.String(50), nullable=True) # Ex: 'image/png', 'image/jpeg'
    
    # Controle de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    componentes = db.relationship('ProdutoCompostoItem', back_populates="produto", cascade="all, delete-orphan")
    
    def adicionar_item(self, estoque, quantidade):
        """Adiciona um material ao produto composto"""
        
        # Log para debug
        print(f"Adicionando item - Quantidade recebida: {quantidade} (tipo: {type(quantidade)})")
            
        # Verificar se o material já existe neste produto
        componente_existente = None
        for componente in self.componentes:
            if componente.estoque_id == estoque.id:
                componente_existente = componente
                break
        
        if componente_existente:
            # Atualizar componente existente
            print(f"Atualizando componente existente - Quantidade anterior: {componente_existente.quantidade}")
            componente_existente.quantidade = quantidade
            print(f"Quantidade atualizada: {componente_existente.quantidade}")
            return componente_existente
        else:
            # Criar novo componente
            # Certifique-se de que o produto já tenha um ID antes de criar o componente
            if not self.id:
                db.session.add(self)
                db.session.flush()
            
            componente = ProdutoCompostoItem(
                produto_id=self.id,
                estoque_id=estoque.id,
                quantidade=quantidade
            )
            print(f"Novo componente criado - Quantidade: {componente.quantidade}")
            self.componentes.append(componente)
            
            # Adicionar ao banco de dados para obter um ID
            db.session.add(componente)
            db.session.flush()
            
            return componente
    
    def remover_item(self, estoque_id):
        """Remove um item do produto composto"""
        for componente in self.componentes:
            if componente.estoque_id == estoque_id:
                self.componentes.remove(componente)
                return True
        return False
    
    def calcular_itens_necessarios(self, quantidade=1):
        """Calcula os itens necessários para produzir um número específico de peças"""
        itens = {}
        for componente in self.componentes:
            estoque_id = componente.estoque_id
            quantidade_necessaria = Decimal(str(componente.quantidade)) * Decimal(str(quantidade))
            
            if estoque_id in itens:
                itens[estoque_id]['quantidade'] += quantidade_necessaria
            else:
                itens[estoque_id] = {
                    'estoque': componente.estoque,
                    'quantidade': quantidade_necessaria
                }
        
        return itens
    
    def verificar_disponibilidade_estoque(self, quantidade=1):
        """Verifica se há estoque suficiente para produzir um número específico de peças"""        
        itens_necessarios = self.calcular_itens_necessarios(quantidade)
        disponibilidade = []
        
        for estoque_id, info in itens_necessarios.items():
            estoque_items = Estoque.query.filter_by(id=estoque_id).all()
            quantidade_total_estoque = sum(item.quantidade for item in estoque_items)
            
            disponibilidade.append({
                'estoque': info['estoque'],
                'quantidade_necessaria': info['quantidade'],
                'quantidade_estoque': quantidade_total_estoque,
                'disponivel': quantidade_total_estoque >= info['quantidade']
            })
        
        return disponibilidade
    
    def save(self):
        """Salva o produto composto no banco de dados"""
        if not self.id:
            db.session.add(self)
            db.session.flush()  # Obter o ID do produto
            
        # Garantir que todos os componentes estejam associados ao produto e tenham IDs
        for componente in self.componentes:
            if not componente.produto_id:
                componente.produto_id = self.id
            db.session.add(componente)
            
        db.session.commit()
        return self
    
    def delete(self):
        """Remove o produto composto do banco de dados"""
        db.session.delete(self)
        db.session.commit()
        return self
    
    def __repr__(self):
        return f'<ProdutoComposto {self.id} - {self.nome}>'


class ProdutoCompostoItem(db.Model):
    """
    Modelo para representar componentes de um produto composto
    """
    __tablename__ = 'ProdComp_Item'
    
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('ProdComp.id', ondelete='CASCADE'), nullable=False)
    estoque_id = db.Column(db.Integer, db.ForeignKey('estoque.id'), nullable=False)
    quantidade = db.Column(db.Numeric(15, 8), nullable=False)  # Aumentado para 8 casas decimais
    observacao = db.Column(db.Text, nullable=True)
    
    # Relacionamento com material
    estoque = db.relationship('Estoque')
    
    # Relacionamento com produto composto
    produto = db.relationship('ProdutoComposto', back_populates='componentes')
    
    def __repr__(self):
        return f'<ComponenteProduto {self.id} - Produto: {self.produto_id}, Material: {self.material.nome}, Quantidade: {self.quantidade} {self.unidade}>'

    def salvar(self):
        """Salva o item no banco de dados"""
        db.session.add(self)
        db.session.commit()
        return self
    
