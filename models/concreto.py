from datetime import datetime

from flask_login import current_user
from sqlalchemy.event import attr
from sqlalchemy.sql import func
from sqlalchemy import JSON
from models.database import db
from sqlalchemy.orm import relationship
from decimal import Decimal
from models.produto_composto import ProdutoComposto
from models.unidade import Unidades
from models.material import Materiais
from models.estoque import EstoqueMovimentacoes
import traceback

class ConcretoConcretagens(db.Model):
    """
    Modelo para representar concretagens de peças de tanques
    """
    __tablename__ = 'ConcretoConcretagens'
    
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
    
    conc = db.Column(db.Integer, nullable=True)
    # Relacionamentos
    tanques_associados = db.relationship("ConcretoConcretagensTanques", back_populates="concretagem", cascade="all, delete-orphan")
   
    def get_volume_total(self):
        """
        Retorna o volume total da concretagem
        """ 
        pecas = self.get_pecas()
        #print(pecas)
        if not pecas:
            return 0
        volume_total = 0
        series = []
        from models.tanque import TanquesPecas
        for peca in pecas:
            peca = TanquesPecas.query.filter(TanquesPecas.nome == peca['nome'],TanquesPecas.tanque_id == peca['tanque_id']).first()
            if peca:
                seriesb = peca.get_series_de_pecas()
                if not seriesb:
                    continue
                for seriea in seriesb:
                    if isinstance(seriea, dict):
                        seriea = seriea['serie']
                    series.append(seriea)

        print(f'[_get_volume_total] Series: {series}')
        volume_total = db.session.query(func.sum(ConcretoUsinagens.volume)).\
            filter(ConcretoUsinagens.serie.in_(series)).scalar() or 0
        return volume_total

    def get_pecas(self):
        """
        Retorna as peças da concretagem
        """
        try:
            import json
            pecas_str = self.pecas
            if not pecas_str:
                return []
            pecas_json = json.loads(pecas_str) if isinstance(pecas_str, str) else pecas_str
            if isinstance(pecas_json, list):
                return pecas_json
            return []
        except (json.JSONDecodeError, TypeError, AttributeError):
            return []
    def get_tanques_ids(self):
        """
        Retorna os IDs dos tanques associados à concretagem
        """
        pecas = self.get_pecas()
        tanques_ids = []
        if pecas:
            for peca in pecas:
                if peca['tanque_id'] not in tanques_ids:
                    tanques_ids.append(peca['tanque_id'])
        return tanques_ids
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
    
    def adicionar_tanque(self, tanque: 'ConcretoConcretagensTanques'):
        """Adiciona um tanque à concretagem"""
        # Verificar se o tanque já existe
        for ct in self.tanques_associados:
            if ct.tanque_id == tanque.id:
                return
        
        # Adicionar nova associação
        associacao = ConcretoConcretagensTanques(tanque=tanque)
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
        return f'<ConcretoConcretagens {self.id} - Pista {self.pista} - {self.data_concretagem}>' 
        
# Nova tabela de associação entre concretagem e tanques
class ConcretoConcretagensTanques(db.Model):
    """
    Modelo para associação entre concretagem e tanques
    """
    __tablename__ = 'ConcretoConcretagensTanques'
    
    concretagem_id = db.Column(db.Integer, db.ForeignKey('ConcretoConcretagens.id', ondelete='CASCADE'), primary_key=True)
    tanque_id = db.Column(db.Integer, db.ForeignKey('Tanques.id', ondelete='CASCADE'), primary_key=True)
    
    # Relacionamentos
    concretagem = db.relationship("ConcretoConcretagens", back_populates="tanques_associados")
    tanque = db.relationship("Tanques")
    
    def __repr__(self):
        return f'<ConcretoConcretagensTanques {self.concretagem_id}-{self.tanque_id}>'


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
    
    # Relacionamentos
    itens = db.relationship('ConcretoTracosItens', backref='traco', cascade='all, delete-orphan')
    
    def adicionar_material(self, material, quantidade, unidade=None, influenciado_umidade=False):
        """Adiciona um material ao traço de concreto"""
        # Se não recebeu unidade, usa a do material
        if not unidade:
            unidade = material.unidade
            
        print(f"Chamada adicionar_material: material={material.id} ({material.nome}), quantidade={quantidade}, unidade={unidade}, influenciado_umidade={influenciado_umidade}")
        
        # Verificar se o material já existe neste traço
        item_existente = None
        for item in self.itens:
            if item.material_id == material.id:
                item_existente = item
                break
        
        if item_existente:
            print(f"Material {material.id} ({material.nome}) já existe no traço, atualizando")
            # Atualizar item existente
            item_existente.quantidade = quantidade
            item_existente.unidade = unidade
            item_existente.influenciado_umidade = influenciado_umidade
            return item_existente
        else:
            print(f"Adicionando novo material {material.id} ({material.nome}) ao traço")
            # Criar novo item
            # Certifique-se de que o traço já tenha um ID antes de criar o item
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
            
            # Adicionar ao banco de dados para obter um ID
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
            db.session.flush()  # Obter o ID do traço
            
        # Garantir que todos os itens estejam associados ao traço e tenham IDs
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
    conversao_unidade_id = db.Column(db.Integer, db.ForeignKey('UnidadesConversao.id'), nullable=True)  # Referência à tabela de conversão
    unidade_id = db.Column(db.Integer, db.ForeignKey('Unidades.id'), nullable=False)  # Chave estrangeira para Unidade
    influenciado_umidade = db.Column(db.Boolean, default=False)  # Indica se o material é influenciado pela umidade
    material_agrupado_id = db.Column(db.Integer, db.ForeignKey('ConcretoTracosItens.id'), nullable=True)  # Referência para materiais agrupados
    ordem_pesagem = db.Column(db.Integer, default=0)  # Ordem de pesagem dentro do grupo
    criado_em = db.Column(db.DateTime, default=datetime.now)
    
    
    # Relacionamento com material
    material = db.relationship('Materiais',foreign_keys=[material_id],backref=db.backref('itens_traco',lazy='dynamic')
                               )
    
    # Relacionamento com a unidade
    unidade = db.relationship('Unidades',foreign_keys=[unidade_id],backref=db.backref('itens_traco',lazy='dynamic'))
    
    # Relacionamento com o material agrupado
    material_agrupado = db.relationship('ConcretoTracosItens', remote_side=[id], backref=db.backref('materiais_associados', lazy='dynamic'))
    
    # Relacionamento com a tabela de conversão usando a chave estrangeira
    conversao_unidade = db.relationship('UnidadesConversao', 
                                       foreign_keys=[conversao_unidade_id],
                                       backref=db.backref('itens_traco', lazy='dynamic'))
   #traco = db.relationship('TracoConcreto',foreign_keys=[traco_id],backref=db.backref('itens',lazy='dynamic'))
    def __repr__(self):
        return f'<ItemTracoConcreto {self.id} - Material: {self.material_id}, Quantidade: {self.quantidade} {self.unidade.nome if self.unidade else "N/A"}>'

class ConcretoUsinagens(db.Model):
    """
    Modelo simplificado para representar usinagem de concreto
    """
    __tablename__ = 'ConcretoUsinagens'
    
    id = db.Column(db.Integer, primary_key=True)
    serie = db.Column(db.String(100), unique=True, nullable=False)  # Série única como referência
    data_usinagem = db.Column(db.DateTime, nullable=False)  # Data/hora da usinagem
    produtoCompostoId = db.Column(db.Integer, db.ForeignKey('ProdutoComposto.id'), nullable=True)  # Traço (ProdutoComposto onde traco=True)
    flow = db.Column(db.String(50), nullable=True)  # Fluidez
    volume = db.Column(db.Numeric(10, 2), nullable=False)  # Volume produzido em m³
    nota = db.Column(db.String(50), nullable=True)  # Nota fiscal
    dados_adicionais = db.Column(JSON, nullable=True)  # Campo JSON para dados futuros

    # Controle de datas
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    produto_composto = db.relationship('ProdutoComposto', foreign_keys=[produtoCompostoId])
    materiais = db.relationship('ConcretoUsinagensMateriais', backref='usinagem', cascade='all, delete-orphan')
    
    def adicionar_material(self, material, quantidade_executada=None, unidade=None, conversao_unidade_id=None):
        """Adiciona um material executado na usinagem"""
        # Verificar se o material já existe
        for item in self.materiais:
            if item.material_id == material.id:
                if quantidade_executada is not None:
                    item.quantidade_executada = quantidade_executada
                # Se a unidade foi passada e é diferente, atualiza (opcional)
                if unidade:
                    if hasattr(unidade, 'nome'): # Se for objeto Unidade
                        item.unidade = unidade.nome
                    else: # Se for string
                        item.unidade = unidade
                return item
        
        # Determinar o nome da unidade para salvar
        nome_unidade_para_salvar = 'N/A' # Default
        if unidade: # Se 'unidade' (parâmetro do método) foi passada
            if hasattr(unidade, 'nome'): # Se for um objeto Unidade com atributo nome
                nome_unidade_para_salvar = unidade.nome
            elif isinstance(unidade, str): # Se for uma string (já é o nome)
                nome_unidade_para_salvar = unidade
            # Adicione mais verificações se 'unidade' puder ser outros tipos
        elif material and material.unidade and hasattr(material.unidade, 'nome'): # Senão, tenta pegar do material.unidade (objeto)
            nome_unidade_para_salvar = material.unidade.nome
        elif material and isinstance(material.unidade, str): # Caso raro: material.unidade já é uma string
             nome_unidade_para_salvar = material.unidade

        # Criar nova associação
        item = ConcretoUsinagensMateriais(
            usinagem_id=self.id,
            material_id=material.id,
            quantidade_executada=quantidade_executada,
            unidade=nome_unidade_para_salvar, # Agora sempre passamos uma string aqui
            conversao_unidade_id=conversao_unidade_id
        )
        self.materiais.append(item)
        return item
    
    def remover_material(self, material_id):
        """Remove um material da usinagem"""
        for item in self.materiais:
            if item.material_id == material_id:
                self.materiais.remove(item)
                return True
        return False
    
    def calcular_materiais(self):
        """Calcula a quantidade de materiais necessários para o volume de concreto baseado no produto composto"""
        resultado = []
        if not self.produto_composto:
            return resultado
        
        # Calcular materiais baseado nos componentes do produto composto
        for componente in self.produto_composto.componentes:
            if componente.estoque and componente.estoque.tipo_item == 'material':
                quantidade_total = Decimal(str(componente.quantidade)) * self.volume
                
                resultado.append({
                    'material': componente.estoque.material,
                    'quantidade': quantidade_total,
                    'unidade': componente.estoque.material.unidade_obj.nome if componente.estoque.material and componente.estoque.material.unidade_obj else 'N/A',
                    'influenciado_umidade': False  # Produto composto não tem controle de umidade
                })
            
        return resultado
    
    def save(self):
        """Salva a usinagem no banco de dados"""
        if not self.id:
            db.session.add(self)
        db.session.commit()
        return self
    
    def delete(self):
        """Remove a usinagem do banco de dados"""
        # Verificar se há movimentações de estoque associadas
        materiais = ConcretoUsinagensMateriais.query.filter_by(usinagem_id=self.id).all()
        for material in materiais:
            if material.movimentacao_estoque_id:
                movimentacao = EstoqueMovimentacoes.query.filter_by(id=material.movimentacao_estoque_id).first()
                if movimentacao:
                    movimentacao.delete()
        db.session.delete(self)
        db.session.commit()
        return self
    
    def tem_redozagem(self):
        """Verifica se há redozagem na usinagem"""
        for item in self.materiais:
            if item.redozagem:
                return True
        return False
    
    def baixar_materiais_estoque(self, usuario_id=None):
        """
        Baixa os materiais utilizados na usinagem do estoque.
        
        Args:
            usuario_id: ID do usuário que está realizando a operação
        
        Returns:
            list: Lista de tuplas com (status_operacao, mensagem, material_id)
        """
        from models.estoque import Estoque, EstoqueMovimentacoes
        from models.database import db
        from decimal import Decimal
        import traceback
        
        resultados = []
        print(f"============ INÍCIO DA BAIXA DE MATERIAIS - USINAGEM ID: {self.id} ============")
        print(f"Total de materiais na usinagem: {len(self.materiais)}")
        
        # Iniciar uma transação para garantir consistência
        try:
            # Buscar os itens de estoque relacionados aos materiais da usinagem
            for i, item_material in enumerate(self.materiais):
                print(f"\nProcessando material {i+1}/{len(self.materiais)}: ID={item_material.material_id}, Material={item_material.material.nome if item_material.material else 'N/A'}")
                
                # Pular se não tem quantidade executada
                if not item_material.quantidade_executada or float(item_material.quantidade_executada) == 0:
                    print(f"Material sem quantidade executada. Pulando.")
                    resultados.append((False, f"Material {item_material.material.nome} sem quantidade executada", item_material.material_id))
                    continue
                
                print(f"Quantidade executada: {item_material.quantidade_executada}")
                
                # Buscar item no estoque
                item_estoque = Estoque.query.filter_by(
                    material_id=item_material.material_id,
                    tipo_item='material'
                ).first()

                # Se não existir no estoque, criar registro
                if not item_estoque:
                    print(f"Material não encontrado no estoque. Criando novo registro.")
                    item_estoque = Estoque(
                        material_id=item_material.material_id,
                        tipo_item='material',
                        quantidade=0,
                        usuario_id=usuario_id or 1
                    )
                    db.session.add(item_estoque)
                    db.session.flush()
                    print(f"Novo item de estoque criado com ID: {item_estoque.id}")
                else:
                    print(f"Material encontrado no estoque. ID: {item_estoque.id}, Quantidade atual: {item_estoque.quantidade}")
                
                # Usar quantidade executada diretamente (já deve estar na unidade correta)
                quantidade_a_baixar = Decimal(str(item_material.quantidade_executada))
                
                # Verificar se há quantidade suficiente em estoque
                if item_estoque.quantidade < quantidade_a_baixar:
                    print(f"Quantidade insuficiente em estoque. Necessário: {quantidade_a_baixar}, Disponível: {item_estoque.quantidade}")
                    resultados.append((False, 
                        f"Quantidade insuficiente de {item_material.material.nome} em estoque. Necessário: {quantidade_a_baixar}, Disponível: {item_estoque.quantidade}", 
                        item_material.material_id
                    ))
                    continue
                
                # Criar movimentação de estoque
                try:
                    if EstoqueMovimentacoes.query.filter_by(origem_id=self.id, origem_tipo='usinagem_concreto', estoque_id=item_estoque.id).count() == 0:
                        observacao = f"Consumo em usinagem de concreto #{self.id} - Série: {self.serie}"
                        movimentacao = EstoqueMovimentacoes.criar_baixa_usinagem(
                            estoque_id=item_estoque.id,
                            quantidade=quantidade_a_baixar,
                            data_movimento=self.data_usinagem,
                            origem_id=self.id,
                            usuario_id=usuario_id or 1,
                            observacao=observacao
                        )
                    elif item_material.redozagem:
                        observacao = f"Consumo em usinagem de concreto redozado material {item_material.material.id} #{self.id} - Série: {self.serie}"
                        movimentacao = EstoqueMovimentacoes.criar_baixa_usinagem(
                            estoque_id=item_estoque.id,
                            quantidade=quantidade_a_baixar,
                            data_movimento=self.data_usinagem,
                            origem_id=self.id,
                            usuario_id=usuario_id or 1,
                            observacao=observacao
                        )
                    else:
                        continue
                    
                    print(f"Movimentação criada com ID: {movimentacao.id if movimentacao else 'N/A'}")
                    item_material.movimentacao_estoque_id = movimentacao.id
                    item_material.save()
                    resultados.append((True, 
                        f"Baixado {quantidade_a_baixar} de {item_material.material.nome} do estoque", 
                        item_material.material_id
                    ))
                except Exception as e:
                    print(f"Erro ao criar movimentação: {str(e)}")
                    print(traceback.format_exc())
                    resultados.append((False, 
                        f"Erro ao realizar baixa de {item_material.material.nome}: {str(e)}", 
                        item_material.material_id
                    ))
            
            # Executar o commit para salvar todas as movimentações
            print(f"\nRealizando commit das alterações no banco de dados")
            db.session.commit()
            print(f"Commit concluído com sucesso")
            
        except Exception as e:
            db.session.rollback()
            print(f"ERRO GERAL ao baixar materiais: {str(e)}")
            print(traceback.format_exc())
            resultados.append((False, f"Erro ao processar baixa de materiais: {str(e)}", None))
        
        print(f"============ FIM DA BAIXA DE MATERIAIS ============")
        return resultados
    
    def __repr__(self):
        return f'<UsinagemConcreto {self.id} - Série: {self.serie}, Data: {self.data_usinagem}, Volume: {self.volume}m³>'

    def get_caminhao(self):
        """Retorna o caminhão baseado no número da série."""
        primeira_serie = ConcretoUsinagens.query.filter(func.date(ConcretoUsinagens.data_usinagem) == self.data_usinagem.date()).order_by(ConcretoUsinagens.data_usinagem.asc()).first().serie

        if primeira_serie == self.serie:
            return "01"
        else:
            return str(self.serie-primeira_serie+1)
    def produzir(self, usuario_id=None):
        """Produz a usinagem de concreto"""
        # Obter usuario_id do parâmetro ou do current_user
        if usuario_id is None:
            usuario_id = current_user.id if current_user and hasattr(current_user, 'id') else 1
        
        print(f"Produzindo usinagem de concreto #{self.id} - Série: {self.serie} - Data: {self.data_usinagem} - Volume: {self.volume} - Produto composto ID: {self.produtoCompostoId}")
        produto = ProdutoComposto.query.get(self.produtoCompostoId)
        if not produto:
            print(f"  AVISO: Usinagem de concreto #{self.id} - Série: {self.serie} - Data: {self.data_usinagem} - Volume: {self.volume} - Produto composto não encontrado. 1")
            return False
        _produtos_processados = set()
        _materiais_necessarios = {}
        produto.produzir(
                    quantidade=self.volume, 
                    data_movimento=self.data_usinagem, 
                    usuario_id=usuario_id, 
                    log=True,
                    produtos_processados=_produtos_processados,
                    materiais_necessarios=_materiais_necessarios,
                    traco=False
                )
        print(f"Materiais necessários: {len(_materiais_necessarios)}")
        if _materiais_necessarios:
            for info in _materiais_necessarios.values():
                estoque = info['estoque']
                quantidade_total = info['quantidade']
                produto_id = info['produto_id']
                print(f"  -> Componente material: {estoque.material.nome} - Quantidade total: {quantidade_total}")
                mov = EstoqueMovimentacoes()
                mov.remover(
                    quantidade=quantidade_total, 
                    estoque_id=estoque.id, 
                    origem_id=self.id, 
                    origem_tipo='usinagem_concreto', 
                    usuario_id=usuario_id,
                    motivo=f'Produção da usinagem de concreto #{self.id} - Série: {self.serie} - Quantidade: {quantidade_total}',
                    log=True)
                mov.data_movimento = self.data_usinagem
                mov.save()
        return True
class ConcretoUsinagensMateriais(db.Model):
    """
    Modelo para representar materiais utilizados em uma usinagem
    """
    __tablename__ = 'ConcretoUsinagensMateriais'
    
    id = db.Column(db.Integer, primary_key=True)
    usinagem_id = db.Column(db.Integer, db.ForeignKey('ConcretoUsinagens.id', ondelete='CASCADE'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('Materiais.id'), nullable=False)
    quantidade_executada = db.Column(db.Numeric(10, 2), nullable=True)
    unidade = db.Column(db.String(20), nullable=False)
    conversao_unidade_id = db.Column(db.Integer, nullable=True)
    movimentacao_estoque_id = db.Column(db.Integer, nullable=True)  # Referência para a tabela de movimentações de estoque
    # Relacionamento com o material
    material = db.relationship('Materiais')
    redozagem = db.Column(db.Boolean, default=False)
    
    # Relacionamento com a unidade de conversão
    #conversao_unidade = db.relationship('ConversaoUnidade')

    def save(self):
        """Salva o material da usinagem no banco de dados"""
        if not self.id:
            db.session.add(self)
        db.session.commit()
        return self
    
    def delete(self):
        """Remove o material da usinagem do banco de dados"""
        db.session.delete(self)
        db.session.commit()
        return self
    def __repr__(self):
        return f'<UsinagemMaterial {self.id} - Material: {self.material_id}, Qtd: {self.quantidade_executada} {self.unidade}>'

class ConcretoUsinagensRompimentos(db.Model):
    """
    Modelo para representar rompimentos de corpos de prova por usinagem
    """
    __tablename__ = 'ConcretoUsinagensRompimentos'
    
    id = db.Column(db.Integer, primary_key=True)
    usinagem_id = db.Column(db.Integer, db.ForeignKey('ConcretoUsinagens.id', ondelete='CASCADE'), nullable=True)
    numero_serie = db.Column(db.Integer, nullable=False)  # Número do CP (1 a 10)
    data_moldagem = db.Column(db.DateTime, nullable=True)  # Data e hora da moldagem do corpo de prova
    data_rompimento = db.Column(db.DateTime, nullable=False)
    resultado = db.Column(db.Numeric(10, 2), nullable=True)  # Resultado do rompimento em MPa
    fator_conversao = db.Column(db.Numeric(5, 2), nullable=True, default=1.2)  # Fator de conversão de kg para MPa
    idade_cp = db.Column(db.Integer, nullable=True)  # Idade do CP em dias
    tipo_rompimento = db.Column(db.String(50), nullable=True)  # Tipo de rompimento (cônica, cônica e bipartida, etc.)
    observacoes = db.Column(db.Text, nullable=True)
    
    # Controle de datas
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamento com usinagem
    usinagem = db.relationship('ConcretoUsinagens', backref=db.backref('rompimentos', lazy=True, cascade="all, delete-orphan"))
    
    def save(self):
        """Salva o rompimento no banco de dados"""
        if not self.id:
            db.session.add(self)
        db.session.commit()
        return self
    
    def delete(self):
        """Remove o rompimento do banco de dados"""
        db.session.delete(self)
        db.session.commit()
        return self
    def is_exist(self):
        """Verifica se o rompimento existe no banco de dados"""
        return ConcretoUsinagensRompimentos.query.filter_by( 
            numero_serie=self.numero_serie, 
            data_rompimento=self.data_rompimento, 
            tipo_rompimento=self.tipo_rompimento, 
            resultado=self.resultado, 
            data_moldagem=self.data_moldagem,
            usinagem_id=self.usinagem_id ).first() is not None
    def __repr__(self):
        return f'<RompimentoCorpoProva {self.id} - Usinagem: {self.usinagem_id}, Série: {self.numero_serie}, Idade: {self.idade_cp} dias>' 