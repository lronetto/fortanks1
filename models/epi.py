from datetime import datetime
from models.database import db
from models.colaborador import Colaborador
from models.material import Material
from decimal import Decimal


class EPI(db.Model):
    __tablename__ = 'epis'
    
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id'), nullable=False)
    material = db.relationship('Material', backref='epi_materiais')
    ca_numero = db.Column(db.String(20))  # Certificado de Aprovação
    data_validade = db.Column(db.Date)
    vida_util_meses = db.Column(db.Integer)
    estoque_atual = db.Column(db.Integer, default=0)
    estoque_minimo = db.Column(db.Integer, default=1)
    # Controle de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))

    entregas_epi = db.relationship('EntregaEPI', back_populates='epi')
    
    def to_dict(self):
        return {
            'id': self.id,
            'material_id': self.material_id,
            'material': self.material.to_dict(),
            'ca_numero': self.ca_numero,
            'data_validade': self.data_validade,
            'vida_util_meses': self.vida_util_meses,
            'estoque_atual': self.estoque_atual,
            'estoque_minimo': self.estoque_minimo,
            'usuario_id': self.usuario_id
        }
    def save(self):
        """
        Salva o EPI no banco de dados e sincroniza com o estoque principal
        """
        if not self.id:
            db.session.add(self)
            db.session.commit()
            # Ao criar um novo EPI, criar entrada no estoque principal
            self._criar_estoque_principal()
        else:
            # Atualizar dados básicos do EPI
            db.session.commit()
            # Atualizar estoque mínimo no estoque principal
            self._atualizar_estoque_minimo()
    
    def delete(self):
        """
        Remove o EPI do banco de dados e suas entradas no estoque principal
        """
        # Buscar e remover o item do estoque principal
        from models.estoque import Estoque
        estoque = Estoque.query.filter_by(material_id=self.material_id, tipo_item='material').first()
        if estoque:
            # Remover movimentações
            from models.estoque import MovimentacaoEstoque
            MovimentacaoEstoque.query.filter_by(estoque_id=estoque.id).delete()
            db.session.delete(estoque)
            
        db.session.delete(self)
        db.session.commit()
    
    def _criar_estoque_principal(self):
        """
        Cria um item no estoque principal para este EPI
        """
        from models.estoque import Estoque
        
        # Verificar se já existe estoque para este material
        estoque = Estoque.query.filter_by(material_id=self.material_id, tipo_item='material').first()
        if not estoque:
            estoque = Estoque(
                material_id=self.material_id,
                tipo_item='material',
                quantidade=0,
                quantidade_minima=self.estoque_minimo,
                localizacao='Estoque EPI',
                usuario_id=self.usuario_id
            )
            db.session.add(estoque)
            db.session.commit()
    
    def _atualizar_estoque_minimo(self):
        """
        Atualiza o estoque mínimo no estoque principal
        """
        from models.estoque import Estoque
        estoque = Estoque.query.filter_by(material_id=self.material_id, tipo_item='material').first()
        if estoque:
            estoque.quantidade_minima = self.estoque_minimo
            db.session.commit()
    
    def adicionar_estoque(self, quantidade, usuario_id,motivo=None):
        """
        Adiciona quantidade ao estoque
        """
        from models.estoque import Estoque, MovimentacaoEstoque
        estoque = Estoque.query.filter_by(material_id=self.material_id, tipo_item='material').first()
        if not estoque:
            raise ValueError("Não existe estoque para este material")
        
        # Criar movimentação de entrada
        print(f"Adicionando {quantidade} item(s) ao estoque2")
        mov = MovimentacaoEstoque()
        db.session.add(mov)
        mov.adicionar(quantidade,estoque.id,self.id,'EPI',usuario_id,motivo)
        mov.save()
        return True
    
    def remover_estoque(self, quantidade, usuario_id):
        """
        Remove quantidade do estoque
        """
        from models.estoque import Estoque, MovimentacaoEstoque
        
        if quantidade <= 0:
            raise ValueError("A quantidade deve ser maior que zero")
        
        # Buscar estoque
        estoque = Estoque.query.filter_by(material_id=self.material_id, tipo_item='material').first()
        if not estoque:
            raise ValueError("Não existe estoque para este material")
        
        mov = MovimentacaoEstoque.remover(quantidade,estoque.id,self.id,'EPI',usuario_id)
        mov.save()
        
        return True
    
    def ajustar_estoque(self,quantidade,usuario_id):
        """
        Ajusta o estoque do EPI
        """
        from models.estoque import Estoque,MovimentacaoEstoque
        estoque = Estoque.query.filter_by(material_id=self.material_id).first()
        movimentacao = MovimentacaoEstoque.query.filter_by(estoque_id=estoque.id).order_by(MovimentacaoEstoque.data_movimento.desc()).first()
        if not estoque:
            raise ValueError("Não existe estoque para este material")
        mov = MovimentacaoEstoque.Ajuste(quantidade,estoque.id,self.id,'EPI',usuario_id)
        mov.save()
        return mov
        
    def getEstoqueAtual(self):
        """
        Retorna o estoque atual do EPI no estoque principal
        """
        from models.estoque import Estoque
        estoque = Estoque.query.filter_by(material_id=self.material_id).first()
       # print(f"estoque: {estoque} {self.material_id}")
        if estoque:
            return estoque.get_estoque_atual()
        else:
            return 0
    
    def get_estoque_atual1(self):
        """
        Retorna o estoque atual do EPI no estoque principal
        """
        from models.estoque import Estoque
        estoque = Estoque.query.filter_by(material_id=self.material_id).first().quantidade
        #print(f"estoque: {estoque} {self.material_id}")
        return estoque
    
    
    def status_estoque(self):
        """
        Retorna o status do estoque atual
        """
        estoque_atual = self.get_estoque_atual()
        if estoque_atual <= 0:
            return "Esgotado"
        elif estoque_atual < self.estoque_minimo:
            return "Crítico"
        else:
            return "Adequado"
            
    @property
    def status_validade(self):
        if not self.data_validade:
            return None
        hoje = datetime.now().date()
        dias_restantes = (self.data_validade - hoje).days
        
        if dias_restantes < 0:
            return "Vencido"
        elif dias_restantes <= 30:
            return "Próximo ao vencimento"
        else:
            return "Válido"

class EntregaEPI(db.Model):
    __tablename__ = 'entregas_epi'
    
    id = db.Column(db.Integer, primary_key=True)
    colaborador_id = db.Column(db.Integer, db.ForeignKey('colaboradores.id'), nullable=False)
    colaborador = db.relationship('Colaborador', backref='entregas_epi')
    epi_id = db.Column(db.Integer, db.ForeignKey('epis.id'), nullable=False)
    epi = db.relationship('EPI', back_populates='entregas_epi',foreign_keys=[epi_id])
    data_entrega = db.Column(db.Date, nullable=False, default=datetime.now().date())
    data_devolucao = db.Column(db.Date)
    quantidade = db.Column(db.Integer, default=1)
    ca = db.Column(db.String(20), nullable=True)
    assinado = db.Column(db.Boolean, default=False)
    motivo = db.Column(db.String(100))  # Novo, Reposição, etc.
    observacoes = db.Column(db.Text)
    movimentacao_estoque_id = db.Column(db.Integer, db.ForeignKey('movimentacoes_estoque.id'), nullable=True)
    movimentacao_estoque = db.relationship('MovimentacaoEstoque', back_populates='entregas_epi',foreign_keys=[movimentacao_estoque_id])
    
    # Controle de auditoria
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'colaborador': self.colaborador.to_dict(),
            'epi': self.epi.to_dict(),
            'data_entrega': self.data_entrega,  
            'data_devolucao': self.data_devolucao,
            'quantidade': self.quantidade,
            'ca': self.ca,
            'assinado': self.assinado,
            'motivo': self.motivo,
            'observacoes': self.observacoes
        }
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        #print(f"kwargs: {kwargs}")
    def save(self):
        from models.estoque import Estoque,MovimentacaoEstoque
        print(f"EntregaEPI: {self.id}")
        print(f"self.epi: {self.epi}")
        print(f"self.epi.material_id: {self.epi.material_id}")
        print(f"self.usuario_id: {self.usuario_id}")
        print(f"self.colaborador_id: {self.colaborador_id}")
        print(f"self.data_entrega: {self.data_entrega}")
        print(f"self.data_devolucao: {self.data_devolucao}")
        print(f"self.quantidade: {self.quantidade}")
        print(f"self.ca: {self.ca}")
        print(f"self.assinado: {self.assinado}")
        print(f"self.motivo: {self.motivo}")

        print(f"self.id: {self.id}")
        # Diminuir estoque usando o método da classe EPI
        estoque = Estoque.query.filter_by(material_id=self.epi.material_id).first()
        print(f"estoque: {estoque}")
        print(f"estoque: {estoque.id}")
        if not estoque:
            raise ValueError("Estoque não encontrado para este material")
        mov=MovimentacaoEstoque()
        db.session.add(mov)
        observacao = f'Entrega de EPI para colaborador {self.colaborador.nome}'
        mov.remover(self.quantidade,estoque.id,self.id,'EntregaEPI',self.usuario_id,observacao)
        mov.save()
        self.movimentacao_estoque_id=mov.id
        db.session.add(self)
        db.session.commit()
        print(f"mov: {mov}")
           
            #self.epi.remover_estoque(self.quantidade, self.usuario_id)
            
        
    def delete(self):
        # Ao excluir uma entrega, restaura o estoque
        if not self.data_devolucao:
            # Garantir que o objeto EPI esteja carregado
            from models.epi import EPI
            if self.epi_id and not hasattr(self, '_epi') or self.epi is None:
                self.epi = EPI.query.get(self.epi_id)
            
            if self.epi is None:
                raise ValueError("EPI não encontrado ou não especificado")
            
            # Garantir que o objeto Colaborador esteja carregado
            from models.colaborador import Colaborador
            if self.colaborador_id and (not hasattr(self, '_colaborador') or self.colaborador is None):
                self.colaborador = Colaborador.query.get(self.colaborador_id)
                
            if self.colaborador is None:
                raise ValueError("Colaborador não encontrado ou não especificado")
            print(f"self.movimentacao_estoque: {self.movimentacao_estoque}")
            if self.movimentacao_estoque:
                # Adicionar estoque usando o método da classe EPI
                motivo = f"Cancelamento de entrega para {self.colaborador.nome}"
                self.epi.adicionar_estoque(self.quantidade, self.usuario_id,motivo)
            
        db.session.delete(self)
        db.session.commit()
        
    def registrar_devolucao(self, data_devolucao=None, observacoes=None):
        if not self.data_devolucao:
            if data_devolucao:
                self.data_devolucao = data_devolucao
            else:
                self.data_devolucao = datetime.now().date()
                
            if observacoes:
                if self.observacoes:
                    self.observacoes += f"\n\nDevolução: {observacoes}"
                else:
                    self.observacoes = f"Devolução: {observacoes}"
                    
            # Ao registrar uma devolução, aumenta o estoque
            # Garantir que o objeto EPI esteja carregado
            from models.epi import EPI
            if self.epi_id and not hasattr(self, '_epi') or self.epi is None:
                self.epi = EPI.query.get(self.epi_id)
            
            if self.epi is None:
                raise ValueError("EPI não encontrado ou não especificado")
            
            # Garantir que o objeto Colaborador esteja carregado
            from models.colaborador import Colaborador
            if self.colaborador_id and (not hasattr(self, '_colaborador') or self.colaborador is None):
                self.colaborador = Colaborador.query.get(self.colaborador_id)
                
            if self.colaborador is None:
                raise ValueError("Colaborador não encontrado ou não especificado")
            
            # Adicionar estoque usando o método da classe EPI
           # motivo = f"Devolução de {self.colaborador.nome}"
            #self.epi.adicionar_estoque(self.quantidade, self.usuario_id, motivo)
            
            db.session.commit()
            return True
        return False
        
    @property
    def status(self):
        if self.data_devolucao:
            return "Devolvido"
        
        # Garantir que o objeto EPI esteja carregado
        from models.epi import EPI
        if self.epi_id and (not hasattr(self, '_epi') or self.epi is None):
            self.epi = EPI.query.get(self.epi_id)
        
        if self.epi is None:
            return "Erro: EPI não encontrado"
        
        if not self.epi.data_validade:
            return "Em uso"
        
        hoje = datetime.now().date()
        if self.epi.data_validade < hoje:
            return "Vencido"
        
        dias_restantes = (self.epi.data_validade - hoje).days
        if dias_restantes <= 30:
            return "Próximo ao vencimento"
        
        return "Em uso"
        
    @property
    def dias_em_uso(self):
        if self.data_devolucao:
            return (self.data_devolucao - self.data_entrega).days
        
        hoje = datetime.now().date()
        return (hoje - self.data_entrega).days 