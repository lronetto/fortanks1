from datetime import datetime
from models.database import db
from sqlalchemy.orm import relationship
from decimal import Decimal
from models.unidade import Unidade
from models.material import Material
from models.estoque import MovimentacaoEstoque
import traceback

class TracoConcreto(db.Model):
    """
    Modelo para representar traços de concreto
    """
    __tablename__ = 'Traco'
    
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
    itens = db.relationship('ItemTracoConcreto', backref='traco', cascade='all, delete-orphan')
    usinagens = db.relationship('UsinagemConcreto', backref='traco', lazy=True)
    
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
            
            item = ItemTracoConcreto(
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

class ItemTracoConcreto(db.Model):
    """
    Modelo para representar itens de um traço de concreto
    """
    __tablename__ = 'TracoItem'
    
    id = db.Column(db.Integer, primary_key=True)
    traco_id = db.Column(db.Integer, db.ForeignKey('Traco.id', ondelete='CASCADE'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id'), nullable=False)
    quantidade = db.Column(db.Numeric(10, 2), nullable=False)  # Quantidade por m³
    conversao_unidade_id = db.Column(db.Integer, db.ForeignKey('conversoes_unidades.id'), nullable=True)  # Referência à tabela de conversão
    unidade_id = db.Column(db.Integer, db.ForeignKey('unidades.id'), nullable=False)  # Chave estrangeira para Unidade
    influenciado_umidade = db.Column(db.Boolean, default=False)  # Indica se o material é influenciado pela umidade
    material_agrupado_id = db.Column(db.Integer, db.ForeignKey('TracoItem.id'), nullable=True)  # Referência para materiais agrupados
    ordem_pesagem = db.Column(db.Integer, default=0)  # Ordem de pesagem dentro do grupo
    criado_em = db.Column(db.DateTime, default=datetime.now)
    
    
    # Relacionamento com material
    material = db.relationship('Material',foreign_keys=[material_id],backref=db.backref('itens_traco',lazy='dynamic')
                               )
    
    # Relacionamento com a unidade
    unidade = db.relationship('Unidade',foreign_keys=[unidade_id],backref=db.backref('itens_traco',lazy='dynamic'))
    
    # Relacionamento com o material agrupado
    material_agrupado = db.relationship('ItemTracoConcreto', remote_side=[id], backref=db.backref('materiais_associados', lazy='dynamic'))
    
    # Relacionamento com a tabela de conversão usando a chave estrangeira
    conversao_unidade = db.relationship('ConversaoUnidade', 
                                       foreign_keys=[conversao_unidade_id],
                                       backref=db.backref('itens_traco', lazy='dynamic'))
   #traco = db.relationship('TracoConcreto',foreign_keys=[traco_id],backref=db.backref('itens',lazy='dynamic'))
    def __repr__(self):
        return f'<ItemTracoConcreto {self.id} - Material: {self.material_id}, Quantidade: {self.quantidade} {self.unidade.nome if self.unidade else "N/A"}>'

class UsinagemConcreto(db.Model):
    """
    Modelo para representar usinagem de concreto
    """
    __tablename__ = 'Usinagem'
    
    id = db.Column(db.Integer, primary_key=True)
    data_usinagem = db.Column(db.DateTime, nullable=False)
    volume_produzido = db.Column(db.Numeric(10, 2), nullable=False)  # em m³
    traco_id = db.Column(db.Integer, db.ForeignKey('Traco.id'), nullable=False)
    local_aplicacao = db.Column(db.String(100), nullable=True)
    responsavel_id = db.Column(db.Integer, db.ForeignKey('colaboradores.id'), nullable=False)
    umidade = db.Column(db.Numeric(5, 2), default=0)  # Umidade em porcentagem
    status = db.Column(db.String(20), default='Concluído')  # Programada, Em andamento, Concluído, Cancelada
    observacoes = db.Column(db.Text, nullable=True)
    quantidade_cps = db.Column(db.Integer, default=0)  # Quantidade de corpos de prova a serem moldados
    status_baixa_estoque = db.Column(db.String(20), default='NAO_EXECUTAR')  # PENDENTE, REALIZADA, ERRO, NAO_EXECUTAR
    nota = db.Column(db.String(10), nullable=True)
    fluidez = db.Column(db.String(15), nullable=True)
    nbt = db.Column(db.String(15), nullable=True)

    # Controle de datas
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    equipamentos = db.relationship('UsinagemEquipamento', backref='usinagem', cascade='all, delete-orphan')
    materiais = db.relationship('UsinagemMaterial', backref='usinagem', cascade='all, delete-orphan')
    concretagem_id = db.Column(db.Integer, db.ForeignKey('Conc.id'), nullable=True)
    #traco = db.relationship('TracoConcreto')
    concretagem = db.relationship('Concretagem')
    responsavel = db.relationship('Colaborador')
    
    def adicionar_equipamento(self, equipamento, funcao=None, horas_trabalhadas=None):
        """Adiciona um equipamento à usinagem"""
        # Verificar se o equipamento já existe
        for item in self.equipamentos:
            if item.equipamento_id == equipamento.id:
                if funcao:
                    item.funcao = funcao
                if horas_trabalhadas is not None:
                    item.horas_trabalhadas = horas_trabalhadas
                return item
        
        # Criar nova associação
        item = UsinagemEquipamento(
            equipamento=equipamento,
            funcao=funcao,
            horas_trabalhadas=horas_trabalhadas
        )
        self.equipamentos.append(item)
        return item

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
        item = UsinagemMaterial(
            material=material,
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
    
    def remover_equipamento(self, equipamento_id):
        """Remove um equipamento da usinagem"""
        for item in self.equipamentos:
            if item.equipamento_id == equipamento_id:
                self.equipamentos.remove(item)
                return True
        return False
    
    def get_unidade_material(self, material_id):
        item_traco = ItemTracoConcreto.query.filter_by(traco_id=self.traco_id, material_id=material_id).first()
        return item_traco.unidade.nome if item_traco and item_traco.unidade else None
    
    def calcular_materiais(self):
        """Calcula a quantidade de materiais necessários para o volume de concreto, considerando a umidade"""
        resultado = []
        if not self.traco:
            return resultado
            
        for item in self.traco.itens:
            quantidade_total = item.quantidade * self.volume_produzido
            
            # Aplicar o fator de correção baseado na umidade quando o material é influenciado
            if item.influenciado_umidade and self.umidade:
                # A umidade afeta a quantidade em uma proporção de 1:1
                # Por exemplo, se umidade = 5%, então quantidade aumenta 5%
                fator_correcao = 1 + (self.umidade / 100)
                quantidade_total = quantidade_total * fator_correcao
            
            resultado.append({
                'material': item.material,
                'quantidade': quantidade_total,
                'unidade': item.unidade.nome if item.unidade else 'N/A', # Usar o nome da unidade
                'influenciado_umidade': item.influenciado_umidade
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
        if self.status_baixa_estoque == 'REALIZADA':
            materiais = UsinagemMaterial.query.filter_by(usinagem_id=self.id).all()
            for material in materiais:
                print(f"Material: {material.material_id} - Movimentação: {material.movimentacao_estoque_id}")
                movimentacao = MovimentacaoEstoque.query.filter_by(id=material.movimentacao_estoque_id).first()
                if movimentacao:
                    movimentacao.delete()
        db.session.delete(self)
        db.session.commit()
        return self
    
    def tem_redozagem(self):
        for item in self.materiais:
            if item.redozagem:
                return True
        return False
    
    def baixar_materiais_estoque(self, usuario_id=None):
        """
        Baixa os materiais utilizados na usinagem do estoque, considerando a conversão de unidades.
        
        Args:
            usuario_id: ID do usuário que está realizando a operação
        
        Returns:
            list: Lista de tuplas com (status_operacao, mensagem, material_id)
        """
        from models.estoque import Estoque, MovimentacaoEstoque
        from models.conversao_unidade import ConversaoUnidade
        from models.database import db
        from decimal import Decimal
        import traceback
        
        resultados = []
        print(f"============ INÍCIO DA BAIXA DE MATERIAIS - USINAGEM ID: {self.id} ============")
        
        # Verificar se a usinagem já está concluída
        if self.status != 'Concluído':
            print(f"Usinagem não está concluída. Status atual: {self.status}")
            return [(False, "A usinagem não está concluída. Materiais não foram baixados do estoque.", None)]
        
        print(f"Usinagem concluída. Prosseguindo com a baixa de materiais.")
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
                        usuario_id=usuario_id or 1  # Default para o primeiro usuário se não especificado
                    )
                    db.session.add(item_estoque)
                    db.session.flush()  # Obter ID do item
                    print(f"Novo item de estoque criado com ID: {item_estoque.id}")
                else:
                    print(f"Material encontrado no estoque. ID: {item_estoque.id}, Quantidade atual: {item_estoque.quantidade}")
                
                # Verificar se precisa de conversão de unidades
                quantidade_a_baixar = Decimal(str(item_material.quantidade_executada))
                materialTraco = ItemTracoConcreto.query.join(Unidade, Unidade.id == ItemTracoConcreto.unidade_id).filter(ItemTracoConcreto.traco_id==self.traco_id, ItemTracoConcreto.material_id==item_material.material_id).first()
                print(f"Unidade do material na usinagem: {materialTraco.unidade.nome}")
                print(f"Unidade do material no estoque: {item_estoque.material.unidade_obj.nome}")
                
                if materialTraco.unidade.nome != item_estoque.material.unidade_obj.nome:
                    print(f"Unidades diferentes. Buscando conversão.")
                    # Buscar conversão entre as unidades
                    #print(f"fator direto: {item_material.traco.itens.conversao_unidade.fator}")
                    conversao = ConversaoUnidade.query.filter_by(id=materialTraco.conversao_unidade_id).first()
                    #conversao = ConversaoUnidade.obter_por_unidades(
                    #    unidade_entrada=item_material.unidade,
                    #    unidade_saida=item_estoque.material.unidade,
                    #    material_id=item_material.material_id
                    #)
                    
                    if conversao:
                        print(f"Conversão encontrada. Fator: {conversao.fator}")
                        # Aplicar a conversão
                        if conversao.unidade_entrada == materialTraco.unidade.nome:
                            f=conversao.fator
                        else:
                            f=1/conversao.fator
                        quantidade_original = quantidade_a_baixar
                        quantidade_a_baixar = quantidade_a_baixar * Decimal(str(f))
                        print(f"Conversão aplicada: {quantidade_original} {materialTraco.unidade.nome} = {quantidade_a_baixar} {item_estoque.material.unidade_obj.nome}")
                    else:
                        print(f"Nenhuma conversão encontrada.")
                        # Sem conversão disponível
                        resultados.append((False, 
                            f"Não foi possível encontrar conversão de {materialTraco.unidade.nome} para {item_estoque.material.unidade_obj.nome} para o material {item_material.material.nome}", 
                            item_material.material_id
                        ))
                        continue
                
                # Verificar se há quantidade suficiente em estoque
                if item_estoque.quantidade < quantidade_a_baixar:
                    print(f"Quantidade insuficiente em estoque. Necessário: {quantidade_a_baixar}, Disponível: {item_estoque.quantidade}")
                    resultados.append((False, 
                        f"Quantidade insuficiente de {item_material.material.nome} em estoque. Necessário: {quantidade_a_baixar} {item_estoque.material.unidade.nome}, Disponível: {item_estoque.quantidade} {item_estoque.material.unidade.nome}", 
                        item_material.material_id
                    ))
                    continue
                
                # Criar movimentação de estoque
                try:
                    
                    
                    if MovimentacaoEstoque.query.filter_by(origem_id=self.id, origem_tipo='usinagem_concreto', estoque_id=item_estoque.id).count() == 0:
                        # Criar movimentação de estoque para usinagem nova

                        print(f"Criando movimentação de estoque com os seguintes dados:")
                        print(f"  - estoque_id: {item_estoque.id}")
                        print(f"  - tipo_movimento: saida")
                        print(f"  - quantidade: {quantidade_a_baixar}")
                        print(f"  - origem_id: {self.id}")
                        print(f"  - origem_tipo: usinagem_concreto")
                        print(f"  - usuario_id: {usuario_id or 1}")
                        # Usar o método de classe para criar a movimentação
                        observacao = f"Consumo em usinagem de concreto #{self.id} - Traço: {self.traco.nome if self.traco else 'N/A'}"
                        movimentacao = MovimentacaoEstoque.criar_baixa_usinagem(
                            estoque_id=item_estoque.id,
                            quantidade=quantidade_a_baixar,
                            data_movimento=self.data_usinagem,
                            origem_id=self.id,
                            usuario_id=usuario_id or 1,
                            observacao=observacao
                        )
                    else:
                        #movimentação de redozação
                        if item_material.redozagem==True:

                            print(f"Criando movimentação de estoque com os seguintes dados:")
                            print(f"  - estoque_id: {item_estoque.id}")
                            print(f"  - tipo_movimento: saida")
                            print(f"  - quantidade: {quantidade_a_baixar}")
                            print(f"  - origem_id: {self.id}")
                            print(f"  - origem_tipo: usinagem_concreto")
                            print(f"  - usuario_id: {usuario_id or 1}")
                            observacao = f"Consumo em usinagem de concreto redozado material {item_material.material.id} #{self.id} - Traço: {self.traco.nome if self.traco else 'N/A'}"
                            movimentacao = MovimentacaoEstoque.criar_baixa_usinagem(
                                estoque_id=item_estoque.id,
                                quantidade=quantidade_a_baixar,
                                data_movimento=self.data_usinagem,
                                origem_id=self.id,
                                usuario_id=usuario_id or 1,
                                observacao=observacao
                            )
                    print(f"Movimentação criada com ID: {movimentacao.id if movimentacao else 'N/A'}")
                    item_material.movimentacao_estoque_id = movimentacao.id
                    item_material.save()
                    resultados.append((True, 
                        f"Baixado {quantidade_a_baixar} {item_estoque.material.unidade_obj.nome} de {item_material.material.nome} do estoque", 
                        item_material.material_id
                    ))
                except Exception as e:
                    print(f"Erro ao criar movimentação: {str(e)}")
                    print(traceback.format_exc())
                    resultados.append((False, 
                        f"Erro ao realizar baixa de {item_material.material.nome}: {str(e)}", 
                        item_material.material_id
                    ))
                    # Não damos rollback aqui para permitir que outras movimentações funcionem
            
            # Executar o commit para salvar todas as movimentações
            print(f"\nRealizando commit das alterações no banco de dados")
            db.session.commit()
            print(f"Commit concluído com sucesso")
            
        except Exception as e:
            # Se ocorrer erro geral, fazemos rollback de tudo
            db.session.rollback()
            print(f"ERRO GERAL ao baixar materiais: {str(e)}")
            print(traceback.format_exc())
            resultados.append((False, f"Erro ao processar baixa de materiais: {str(e)}", None))
        
        print(f"============ FIM DA BAIXA DE MATERIAIS ============")
        return resultados
    
    def __repr__(self):
        return f'<UsinagemConcreto {self.id} - Data: {self.data_usinagem}, Volume: {self.volume_produzido}m³>'

class UsinagemEquipamento(db.Model):
    """
    Modelo para representar equipamentos utilizados em uma usinagem
    """
    __tablename__ = 'UsinEquip'
    
    id = db.Column(db.Integer, primary_key=True)
    usinagem_id = db.Column(db.Integer, db.ForeignKey('Usinagem.id', ondelete='CASCADE'), nullable=False)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('equipamentos.id'), nullable=False)
    funcao = db.Column(db.String(100), nullable=True)
    horas_trabalhadas = db.Column(db.Numeric(10, 2), nullable=True)
    
    # Relacionamento com o equipamento
    equipamento = db.relationship('Equipamento')
    
    def __repr__(self):
        return f'<UsinagemEquipamento {self.id} - Usinagem: {self.usinagem_id}, Equipamento: {self.equipamento_id}>'

class UsinagemMaterial(db.Model):
    """
    Modelo para representar materiais utilizados em uma usinagem
    """
    __tablename__ = 'UsinMat'
    
    id = db.Column(db.Integer, primary_key=True)
    usinagem_id = db.Column(db.Integer, db.ForeignKey('Usinagem.id', ondelete='CASCADE'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id'), nullable=False)
    quantidade_executada = db.Column(db.Numeric(10, 2), nullable=True)
    unidade = db.Column(db.String(20), nullable=False)
    conversao_unidade_id = db.Column(db.Integer, nullable=True)
    movimentacao_estoque_id = db.Column(db.Integer, nullable=True)  # Referência para a tabela de movimentações de estoque
    # Relacionamento com o material
    material = db.relationship('Material')
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

class RompimentoCorpoProva(db.Model):
    """
    Modelo para representar rompimentos de corpos de prova por usinagem
    """
    __tablename__ = 'RompCorpProva'
    
    id = db.Column(db.Integer, primary_key=True)
    usinagem_id = db.Column(db.Integer, db.ForeignKey('Usinagem.id', ondelete='CASCADE'), nullable=False)
    numero_cp = db.Column(db.Integer, nullable=False)  # Número do CP (1 a 10)
    data_rompimento = db.Column(db.DateTime, nullable=False)
    resultado = db.Column(db.Numeric(10, 2), nullable=True)  # Resultado do rompimento em MPa
    idade_cp = db.Column(db.Integer, nullable=False)  # Idade do CP em dias
    tipo_rompimento = db.Column(db.String(50), nullable=True)  # Tipo de rompimento (cônica, cônica e bipartida, etc.)
    observacoes = db.Column(db.Text, nullable=True)
    
    # Controle de datas
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamento com usinagem
    usinagem = db.relationship('UsinagemConcreto', backref=db.backref('rompimentos', lazy=True, cascade="all, delete-orphan"))
    
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
    
    def __repr__(self):
        return f'<RompimentoCorpoProva {self.id} - Usinagem: {self.usinagem_id}, CP: {self.numero_cp}, Idade: {self.idade_cp} dias>' 