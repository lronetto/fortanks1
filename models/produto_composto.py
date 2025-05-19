from datetime import datetime
from models.database import db
from models.peca import Peca
from models.material import Material
from decimal import Decimal

class ProdutoComposto(db.Model):
    """
    Modelo para representar produtos compostos para produção de peças concretadas
    """
    __tablename__ = 'ProdComp'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    tipo_peca = db.Column(db.String(50), nullable=False)
    tempo_producao = db.Column(db.Numeric(10, 2), nullable=True)  # Tempo estimado de produção em horas
    status = db.Column(db.String(20), default='Ativo')  # Ativo, Inativo
    
    # Controle de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    componentes = db.relationship('ComponenteProduto', back_populates="produto", cascade="all, delete-orphan")
    
    def adicionar_material(self, material, quantidade, unidade=None):
        """Adiciona um material ao produto composto"""
        # Se não recebeu unidade, usa a do material
        if not unidade:
            unidade = material.get_unidade_nome()
            
        # Verificar se o material já existe neste produto
        componente_existente = None
        for componente in self.componentes:
            if componente.material_id == material.id:
                componente_existente = componente
                break
        
        if componente_existente:
            # Atualizar componente existente
            componente_existente.quantidade = quantidade
            componente_existente.unidade = unidade
            return componente_existente
        else:
            # Criar novo componente
            # Certifique-se de que o produto já tenha um ID antes de criar o componente
            if not self.id:
                db.session.add(self)
                db.session.flush()
            
            componente = ComponenteProduto(
                produto_id=self.id,
                material=material,
                quantidade=quantidade,
                unidade=unidade
            )
            self.componentes.append(componente)
            
            # Adicionar ao banco de dados para obter um ID
            db.session.add(componente)
            db.session.flush()
            
            return componente
    
    def remover_material(self, material_id):
        """Remove um material do produto composto"""
        for componente in self.componentes:
            if componente.material_id == material_id:
                self.componentes.remove(componente)
                return True
        return False
    
    def calcular_materiais_necessarios(self, quantidade=1):
        """Calcula os materiais necessários para produzir um número específico de peças"""
        materiais = {}
        
        for componente in self.componentes:
            material_id = componente.material_id
            quantidade_necessaria = Decimal(str(componente.quantidade)) * Decimal(str(quantidade))
            
            if material_id in materiais:
                materiais[material_id]['quantidade'] += quantidade_necessaria
            else:
                materiais[material_id] = {
                    'material': componente.material,
                    'quantidade': quantidade_necessaria,
                    'unidade': componente.unidade
                }
        
        return materiais
    
    def verificar_disponibilidade_estoque(self, quantidade=1):
        """Verifica se há estoque suficiente para produzir um número específico de peças"""
        from models.estoque import Estoque
        
        materiais_necessarios = self.calcular_materiais_necessarios(quantidade)
        disponibilidade = []
        
        for material_id, info in materiais_necessarios.items():
            estoque_items = Estoque.query.filter_by(material_id=material_id, tipo_item='material').all()
            quantidade_total_estoque = sum(item.quantidade for item in estoque_items)
            
            disponibilidade.append({
                'material': info['material'],
                'quantidade_necessaria': info['quantidade'],
                'quantidade_estoque': quantidade_total_estoque,
                'unidade': info['unidade'],
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
    
    @classmethod
    def get_by_tipo_peca(cls, tipo_peca):
        """Busca um produto composto pelo tipo de peça"""
        return cls.query.filter_by(tipo_peca=tipo_peca, status='Ativo').first()
    
    def __repr__(self):
        return f'<ProdutoComposto {self.id} - {self.nome} ({self.tipo_peca})>'


class ComponenteProduto(db.Model):
    """
    Modelo para representar componentes de um produto composto
    """
    __tablename__ = 'ProdComp_Item'
    
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('ProdComp.id', ondelete='CASCADE'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id'), nullable=False)
    quantidade = db.Column(db.Numeric(10, 2), nullable=False)
    unidade = db.Column(db.String(20), nullable=False)
    observacao = db.Column(db.Text, nullable=True)
    
    # Relacionamento com material
    material = db.relationship('Material')
    
    # Relacionamento com produto composto
    produto = db.relationship('ProdutoComposto', back_populates='componentes')
    
    def __repr__(self):
        return f'<ComponenteProduto {self.id} - Produto: {self.produto_id}, Material: {self.material.nome}, Quantidade: {self.quantidade} {self.unidade}>'


class ProducaoPeca(db.Model):
    """
    Modelo para registrar a produção de peças usando produtos compostos
    """
    __tablename__ = 'ProdComp_Producao'
    
    id = db.Column(db.Integer, primary_key=True)
    peca_id = db.Column(db.Integer, db.ForeignKey('pecas.id'), nullable=False)
    produto_composto_id = db.Column(db.Integer, db.ForeignKey('ProdComp.id'), nullable=False)
    data_producao = db.Column(db.DateTime, default=datetime.now, nullable=False)
    quantidade = db.Column(db.Integer, default=1, nullable=False)
    status = db.Column(db.String(20), default='Concluída')  # Programada, Em andamento, Concluída, Cancelada
    observacoes = db.Column(db.Text, nullable=True)
    
    # Controle de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    peca = db.relationship('Peca')
    produto_composto = db.relationship('ProdutoComposto')
    materiais = db.relationship('ProducaoPecaMaterial', back_populates='producao', cascade='all, delete-orphan')
    
    def produzir(self, usuario_id):
         # Buscar produto composto e adicionar materiais
        produto = ProdutoComposto.query.get(self.produto_composto_id)
        if produto:
            materiais_necessarios = produto.calcular_materiais_necessarios(self.quantidade)
            
            for material_id, info in materiais_necessarios.items():
                material = info['material']
                quantidade_necessaria = info['quantidade']
                unidade = info['unidade']
                self.adicionar_material(material, quantidade_necessaria, unidade)
        
        # Salvar produção
        self.save()
        if self.status == 'Concluída':
            self.baixar_materiais_estoque(usuario_id)
       
        
    def adicionar_material(self, material, quantidade_utilizada, unidade=None):
        """Adiciona um material utilizado na produção da peça"""
        # Se não recebeu unidade, usa a do material
        if not unidade:
            unidade = material.get_unidade_nome()
            
        # Criar o item de material usado
        item = ProducaoPecaMaterial(
            material=material,
            quantidade_utilizada=quantidade_utilizada,
            unidade=unidade
        )
        self.materiais.append(item)
        return item
    
    def baixar_materiais_estoque(self, usuario_id):
        """Realiza a baixa dos materiais do estoque"""
        from models.estoque import Estoque, MovimentacaoEstoque
        from decimal import Decimal
        
        resultados = []
        
        for item in self.materiais:
            # Buscar o estoque disponível
            estoque_items = Estoque.query.filter_by(
                material_id=item.material_id,
                tipo_item='material'
            ).order_by(Estoque.data_validade).all()
            
            quantidade_pendente = Decimal(str(item.quantidade_utilizada))
            
            for estoque in estoque_items:
                if quantidade_pendente <= 0:
                    break
                    
                quantidade_disponivel = estoque.quantidade
                quantidade_baixa = min(quantidade_disponivel, quantidade_pendente)
                
                if quantidade_baixa > 0:
                    try:
                        # Criar movimentação de saída
                        movimentacao = MovimentacaoEstoque(
                            estoque_id=estoque.id,
                            tipo_movimento='saida',
                            quantidade=quantidade_baixa,
                            data_movimento=datetime.now(),
                            origem_id=self.id,
                            origem_tipo='producao_peca',
                            observacao=f"Produção de peça #{self.peca.numero_sequencial} - {self.peca.tipo}",
                            usuario_id=usuario_id
                        )
                        
                        # Atualizar estoque
                        estoque.quantidade -= quantidade_baixa
                        quantidade_pendente -= quantidade_baixa
                        
                        # Salvar movimentação
                        db.session.add(movimentacao)
                        resultados.append({
                            'material': item.material.nome, 
                            'baixado': float(quantidade_baixa),
                            'unidade': item.unidade,
                            'estoque': estoque.id
                        })
                    except Exception as e:
                        resultados.append({
                            'material': item.material.nome,
                            'erro': str(e)
                        })
            
            # Se ainda tem quantidade pendente, registre um erro
            if quantidade_pendente > 0:
                resultados.append({
                    'material': item.material.nome,
                    'erro': f'Estoque insuficiente. Faltam {quantidade_pendente} {item.unidade}'
                })
                
        # Commit das alterações
        db.session.commit()
        return resultados
    
    def save(self):
        """Salva a produção de peça no banco de dados"""
        if not self.id:
            db.session.add(self)
            db.session.flush()
            
        # Salvar os materiais associados
        for material in self.materiais:
            if not material.producao_id:
                material.producao_id = self.id
            db.session.add(material)
            
        db.session.commit()
        return self
    
    def delete(self):
        """Remove a produção de peça do banco de dados"""
        db.session.delete(self)
        db.session.commit()
        return self
    
    def __repr__(self):
        return f'<ProducaoPeca {self.id} - Peça: {self.peca.tipo} #{self.peca.numero_sequencial}, Data: {self.data_producao}>'


class ProducaoPecaMaterial(db.Model):
    """
    Modelo para representar materiais utilizados na produção de uma peça
    """
    __tablename__ = 'ProdComp_Producao_Material'
    
    id = db.Column(db.Integer, primary_key=True)
    producao_id = db.Column(db.Integer, db.ForeignKey('ProdComp_Producao.id', ondelete='CASCADE'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id'), nullable=False)
    quantidade_utilizada = db.Column(db.Numeric(10, 2), nullable=False)
    unidade = db.Column(db.String(20), nullable=False)
    
    # Relacionamentos
    material = db.relationship('Material')
    producao = db.relationship('ProducaoPeca', back_populates='materiais')
    
    def __repr__(self):
        return f'<ProducaoPecaMaterial {self.id} - Material: {self.material.nome}, Quantidade: {self.quantidade_utilizada} {self.unidade}>' 