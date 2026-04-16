import logging
from datetime import datetime
from flask import json
from sqlalchemy import JSON
from models.database import db
from decimal import Decimal
from models.estoque import Estoque
from utils.utils import normalizar_para_data

logger = logging.getLogger(__name__)
class ProdutoComposto(db.Model):
    """
    Modelo para representar produtos compostos para produção de peças concretadas
    """
    __tablename__ = 'ProdutoComposto'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    tempo_producao = db.Column(db.Numeric(10, 2), nullable=True)  # Tempo estimado de produção em horas
    status = db.Column(db.String(20), default='Ativo')  # Ativo, Inativo
    traco = db.Column(db.Integer, default=False)
    dados_adicionais = db.Column(JSON, nullable=True)  # Campo JSON para dados adicionais (datas de início/término)
    
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
        logger.debug(
            "Adicionando item ao produto composto %s - quantidade=%s tipo=%s",
            self.id,
            quantidade,
            type(quantidade),
        )
            
        # Verificar se o material já existe neste produto
        componente_existente = None
        for componente in self.componentes:
            if componente.estoque_id == estoque.id:
                componente_existente = componente
                break
        
        if componente_existente:
            # Atualizar componente existente
            logger.debug(
                "Atualizando componente existente id=%s quantidade_anterior=%s nova_quantidade=%s",
                componente_existente.id,
                componente_existente.quantidade,
                quantidade,
            )
            componente_existente.quantidade = quantidade
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
            logger.debug("Novo componente criado com quantidade=%s", componente.quantidade)
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

        estoque_ids = list(itens_necessarios.keys())
        estoques = Estoque.query.filter(Estoque.id.in_(estoque_ids)).all() if estoque_ids else []
        quantidade_por_estoque_id = {
            item.id: Decimal(str(item.quantidade or 0))
            for item in estoques
        }

        for estoque_id, info in itens_necessarios.items():
            quantidade_total_estoque = quantidade_por_estoque_id.get(estoque_id, Decimal('0'))
            
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
    
    def get_valor_total(self):
        """Retorna o valor unitário do produto composto"""
        return sum(componente.get_valor_total() for componente in self.componentes)
    
    def produzir(self, quantidade=1, data_movimento=None, usuario_id=1, log=None, produtos_processados=None, materiais_necessarios=None,traco=False):
        """
        Produz um item do produto composto.
        
        Args:
            quantidade: Quantidade de itens a produzir
            data_movimento: Data da movimentação
            usuario_id: ID do usuário que está produzindo
            log: Se True, imprime logs de debug
            produtos_processados: Conjunto de IDs de produtos compostos já processados (para evitar loops infinitos)
        """
        if log:
            logger.info(
                "Produzindo produto composto %s (ID: %s) - Quantidade: %s",
                self.nome,
                self.id,
                quantidade,
            )
        # Inicializar conjunto de produtos processados se não foi fornecido
        if produtos_processados is None:
            produtos_processados = set()
        
        # Normalizar quantidade para Decimal para evitar float * Decimal
        if not isinstance(quantidade, Decimal):
            quantidade = Decimal(str(quantidade))
        
        # Verificar se este produto já foi processado (evita loops infinitos)
        if self.id in produtos_processados:
            if log:
                print(f"AVISO: Produto composto {self.nome} (ID: {self.id}) já foi processado. Pulando para evitar loop infinito.")
            return
        
        # Adicionar este produto ao conjunto de processados
        produtos_processados.add(self.id)
        
        #        if log:
        #            print(f"Produzindo produto composto {self.nome} (ID: {self.id}) - Quantidade: {quantidade}")
        
        
        produtos_compostos = []
        materiais_agrupados = {}  # chave: estoque_id -> info agrupada
        # acumulador compartilhado entre recursões
        if materiais_necessarios is None:
            materiais_necessarios = {}
        
        
        data_movimento = normalizar_para_data(
            data_movimento,
            default=datetime.now().date(),
        )
        
        for componente in self.componentes:
            if componente.dados_adicionais:
                try:
                    dados_adicionais = json.loads(componente.dados_adicionais)
                    datainicio = normalizar_para_data(dados_adicionais.get('data_inicio'))
                    if datainicio and data_movimento and datainicio > data_movimento:
                        continue

                    datatermino = normalizar_para_data(dados_adicionais.get('data_termino'))
                    if datatermino and data_movimento and datatermino <= data_movimento:
                        continue
                except (ValueError, TypeError) as e:
                    # Se houver erro no parse, logar e continuar processando o componente
                    if log:
                        logger.warning(
                            "Erro ao processar datas do componente %s: %s",
                            componente.id,
                            str(e),
                        )
                    # Continuar processando o componente mesmo com erro nas datas
            if componente.estoque.tipo_item == 'material':
                estoque_id = componente.estoque.id
                quantidade_total = quantidade * componente.quantidade
                if log:
                    print(f"  -> Componente material: {componente.estoque.material.nome} - Quantidade: {quantidade_total}")
                # Agrupa no dicionário local
                if estoque_id in materiais_agrupados:
                    materiais_agrupados[estoque_id]['quantidade'] += quantidade_total
                    materiais_agrupados[estoque_id]['componentes'].append(componente)
                else:
                    materiais_agrupados[estoque_id] = {
                        'estoque': componente.estoque,
                        'quantidade': quantidade_total,
                        'componentes': [componente],
                        'produto_id': componente.produto_id,
                    }
                # Propaga para o acumulador compartilhado (dict) somando
                if estoque_id in materiais_necessarios:
                    materiais_necessarios[estoque_id]['quantidade'] += quantidade_total
                    materiais_necessarios[estoque_id]['componentes'].append(componente)
                else:
                    materiais_necessarios[estoque_id] = {
                        'estoque': componente.estoque,
                        'quantidade': quantidade_total,
                        'componentes': [componente],
                        'produto_id': componente.produto_id,
                    }
            
            elif componente.estoque.tipo_item == 'produto_composto':
                if log:
                    print(f"  -> Componente composto: {componente.estoque.produto_composto.nome} (ID: {componente.estoque.produto_composto.id}) - Quantidade: {quantidade*componente.quantidade}")
                if traco:
                    if not componente.estoque.produto_composto.traco:
                        if log:
                            print(f" AVISO: Produto composto {componente.estoque.produto_composto.nome} (ID: {componente.estoque.produto_composto.id}) nao é um traço. adicionando ao processamento.")
                        produtos_compostos.append(componente)
                    else:
                        if log:
                            print(f" AVISO: Produto composto {componente.estoque.produto_composto.nome} (ID: {componente.estoque.produto_composto.id}) é um traço. Pulando para evitar loop infinito.")
                else:
                    produtos_compostos.append(componente)
            else:
                if log:
                    print(f"  AVISO: Tipo de item {componente.estoque.tipo_item} não suportado")
        
       
        
        # Processar produtos compostos
        for componente in produtos_compostos:
            # Buscar produto composto aninhado através do estoque
            if not componente.estoque or not componente.estoque.ProdComp_id:
                if log:
                    print(f"  ERRO: Estoque sem ProdComp_id para componente composto")
                continue
            
            comp = componente.estoque.produto_composto
            if not comp:
                # Tentar buscar diretamente pelo ID
                comp = ProdutoComposto.query.get(componente.estoque.ProdComp_id)
                if not comp:
                    if log:
                        print(f"  ERRO: Produto composto {componente.estoque.ProdComp_id} não encontrado")
                    continue
            
            if log:
                print(f"  -> Componente composto: {comp.nome} (ID: {comp.id}) - Quantidade: {quantidade*componente.quantidade}")
            
            # Verificar se já foi processado antes de chamar recursivamente (evita loops infinitos)
            if comp.id in produtos_processados:
                if log:
                    print(f"  AVISO: Produto composto {comp.nome} (ID: {comp.id}) já foi processado. Pulando para evitar loop infinito.")
                continue
            #print(f"produzido")
            # Chamar recursivamente passando o conjunto de produtos processados
            comp.produzir(
                quantidade=quantidade*componente.quantidade, 
                data_movimento=data_movimento, 
                usuario_id=usuario_id, 
                log=log,
                produtos_processados=produtos_processados,
                materiais_necessarios=materiais_necessarios,  # Passar o mesmo conjunto para evitar loops
                traco=traco
            )
        
class ProdutoCompostoItem(db.Model):
    """
    Modelo para representar componentes de um produto composto
    """
    __tablename__ = 'ProdutoCompostoItem'
    
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('ProdutoComposto.id', ondelete='CASCADE'), nullable=False)
    estoque_id = db.Column(db.Integer, db.ForeignKey('Estoque.id'), nullable=False)
    quantidade = db.Column(db.Numeric(15, 8), nullable=False)  # Aumentado para 8 casas decimais
    observacao = db.Column(db.Text, nullable=True)
    dados_adicionais = db.Column(db.Text, nullable=True)  # Campo JSON para dados adicionais (datas de início/término)
    
    # Relacionamento com material
    estoque = db.relationship('Estoque')
    
    # Relacionamento com produto composto
    produto = db.relationship('ProdutoComposto', back_populates='componentes')
    
    def __repr__(self):
        # Representação segura para logs/debug sem depender de atributos inexistentes
        material_nome = None
        try:
            material_nome = self.estoque.material.nome if self.estoque and self.estoque.material else None
        except Exception:
            material_nome = None
        return f'<ComponenteProduto {self.id} - Produto: {self.produto_id}, Estoque: {self.estoque_id}, Material: {material_nome}, Quantidade: {self.quantidade}>'

    def get_valor_unitario(self):
        """Retorna o valor unitário do item"""
        return self.estoque.get_valor_unitario()
    def get_valor_total(self):
        """Retorna o valor total do item"""
        return self.get_valor_unitario() * self.quantidade
    def salvar(self):
        """Salva o item no banco de dados"""
        db.session.add(self)
        db.session.commit()
        return self
    
    
