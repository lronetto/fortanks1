from models.database import db
from models.unidade import Unidade
from datetime import datetime
from flask import render_template, current_app
from io import BytesIO
import tempfile
##from .unidade import Unidade
##from .conversao_unidade import ConversaoUnidade

class NotaFiscal(db.Model):
    """
    Modelo para representar Notas Fiscais
    """
    __tablename__ = 'nf_notas'
    
    id = db.Column(db.Integer, primary_key=True)
    numero_nf = db.Column(db.String(20), nullable=False)
    chave_acesso = db.Column(db.String(44), unique=True, nullable=False)
    data_emissao = db.Column(db.DateTime, nullable=False)
    valor_total = db.Column(db.Numeric(15, 2), nullable=False)
    
    # Dados do emitente e destinatário
    cnpj_emitente = db.Column(db.String(14), nullable=False)
    nome_emitente = db.Column(db.String(100), nullable=False)
    cnpj_destinatario = db.Column(db.String(14), nullable=False)
    nome_destinatario = db.Column(db.String(100), nullable=False)
    
    # Dados de processamento
    xml_data = db.Column(db.Text, nullable=True)
    status_processamento = db.Column(db.String(20), default='Importada', nullable=False)
    #solicitacao_id = db.Column(db.Integer, db.ForeignKey('solicitacoes.id'), nullable=True)
    
    # Datas de controle
    data_importacao = db.Column(db.DateTime, default=datetime.now, nullable=False)
    #data_cadastro = db.Column(db.DateTime, default=datetime.now)
    data_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    itens = db.relationship('NotaFiscalItem', backref='nota_fiscal', cascade='all, delete-orphan')
    
    def save(self):
        """
        Salva a nota fiscal no banco de dados
        """
        db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove a nota fiscal do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    
    def todos_itens_importados(self):
        """
        Verifica se todos os itens da nota fiscal foram importados para o estoque
        
        Returns:
            bool: True se todos os itens foram importados, False caso contrário
        """
        if not self.itens:
            return False
            
        for item in self.itens:
            if not item.importado_estoque:
                return False
                
        return True
    
    def percentual_importacao(self):
        """
        Calcula o percentual de itens da nota fiscal que foram importados para o estoque
        
        Returns:
            float: Percentual de itens importados (0 a 100)
        """
        if not self.itens:
            return 0
            
        total_itens = len(self.itens)
        itens_importados = sum(1 for item in self.itens if item.importado_estoque)
        
        return (itens_importados / total_itens) * 100
    
    def gerar_pdf(self):
        """
        Gera um PDF da nota fiscal
        """
        try:
            # Verificar se a biblioteca WeasyPrint está disponível
            from weasyprint import HTML, CSS
            from weasyprint.text.fonts import FontConfiguration
            
            # Renderizar o template com os dados da nota fiscal
            html_content = render_template(
                'notas_fiscais/pdf_template.html',
                nota_fiscal=self,
                data_geracao=datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            )
            
            # Configuração de fontes
            font_config = FontConfiguration()
            
            # Criar arquivo temporário para salvar o HTML
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
                f.write(html_content.encode('utf-8'))
                html_file = f.name
            
            # Gerar PDF a partir do HTML
            html = HTML(filename=html_file)
            css = CSS(string='''
                @page { 
                    size: A4; 
                    margin: 1cm;
                    @top-center {
                        content: "Nota Fiscal";
                        font-weight: bold;
                    }
                    @bottom-center {
                        content: "Página " counter(page) " de " counter(pages);
                    }
                }
                body { font-family: Arial, sans-serif; }
                .header { text-align: center; margin-bottom: 20px; }
                .logo { text-align: right; }
                .info-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
                .info-table th, .info-table td { border: 1px solid #ddd; padding: 8px; }
                .info-table th { background-color: #f2f2f2; width: 40%; text-align: right; }
            ''', font_config=font_config)
            
            # Criar buffer para o PDF
            pdf_buffer = BytesIO()
            html.write_pdf(pdf_buffer, stylesheets=[css])
            pdf_buffer.seek(0)
            
            return pdf_buffer
            
        except ImportError:
            # Caso WeasyPrint não esteja disponível
            return None
    
    def __repr__(self):
        """
        Representação em string da nota fiscal
        """
        return f'<NotaFiscal {self.numero_nf} - {self.chave_acesso}>'


class NotaFiscalItem(db.Model):
    """
    Modelo para representar itens de Nota Fiscal
    """
    __tablename__ = 'nf_itens'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(60), nullable=True)
    descricao = db.Column(db.String(255), nullable=False)
    quantidade = db.Column(db.Numeric(15, 4), nullable=False)
    valor_unitario = db.Column(db.Numeric(15, 4), nullable=False)
    valor_total = db.Column(db.Numeric(15, 2), nullable=False)
    
    # Dados fiscais
    ncm = db.Column(db.String(8), nullable=True)
    cfop = db.Column(db.String(4), nullable=True)
    unidade = db.Column(db.String(6), nullable=True)
    
    # Campos para conversão de unidades
    unidade_id = db.Column(db.Integer, db.ForeignKey('unidades.id'), nullable=True)
    unidade_rel = db.relationship('Unidade', backref='nf_itens', lazy=True)
    unidade_original = db.Column(db.String(6), nullable=True)
    quantidade_original = db.Column(db.Numeric(15, 4), nullable=True)
    fator_conversao_aplicado = db.Column(db.Numeric(15, 4), nullable=True)
    
    # Vinculação com material do sistema
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id'), nullable=True)
    material = db.relationship('Material', backref='itens_nota_fiscal')
    
    # Status de importação para estoque
    importado_estoque = db.Column(db.Boolean, default=False)
    data_importacao_estoque = db.Column(db.DateTime, nullable=True)
    usuario_importacao_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    usuario_importacao = db.relationship('Usuario', foreign_keys=[usuario_importacao_id])
    
    # Campos para tracking de importação
    tentativas_importacao = db.Column(db.Integer, default=0)
    ultima_tentativa_importacao = db.Column(db.DateTime, nullable=True)
    status_importacao = db.Column(db.String(30), default='Pendente')
    dados_adicionais = db.Column(db.Text, nullable=True)
    
    # Chave estrangeira
    nf_id = db.Column(db.Integer, db.ForeignKey('nf_notas.id', ondelete='CASCADE'), nullable=False)
    
    # Datas de controle
    data_criacao = db.Column(db.DateTime, default=datetime.now)
    data_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def save(self):
        """
        Salva o item de nota fiscal no banco de dados
        """
        db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o item de nota fiscal do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    
    def importar_para_estoque(self, usuario_id, centro_custo_id=None, observacao=None):
        """
        Importa o item da nota fiscal para o estoque
        
        Args:
            usuario_id: ID do usuário que está realizando a importação
            centro_custo_id: ID do centro de custo (opcional)
            observacao: Observação adicional para a movimentação
            
        Returns:
            tuple: (bool, str) - (Sucesso, Mensagem)
        """
        from models.estoque import Estoque, MovimentacaoEstoque
        
        # Verificar se o item já foi importado
        if self.importado_estoque:
            return (False, "Item já foi importado para o estoque.")
        
        # Verificar se o item tem um material vinculado
        if not self.material_id:
            return (False, "Este item não está vinculado a um material do sistema.")
        
        try:
            # Buscar estoque existente para o material
            estoque = Estoque.query.filter_by(material_id=self.material_id).first()
            
            # Se não existe estoque para este material, criar um novo
            if not estoque:
                print(f"Criando novo estoque para o material {self.material_id}")
                estoque = Estoque(
                    material_id=self.material_id,
                    tipo_item='material',
                    quantidade=0,
                    localizacao='Estoque principal',
                    centro_custo_id=centro_custo_id,
                    usuario_id=usuario_id
                )
                estoque.save()
                db.session.refresh(estoque)
            else:
                print(f"Estoque encontrado para o material {self.material_id}")
            # Criar movimentação de entrada no estoque
            if not observacao:
                observacao = f"Importação da NF {self.nota_fiscal.numero_nf} de {self.nota_fiscal.nome_emitente}"
                
            # Adicionar informação sobre conversão de unidade, se aplicável
            if self.fator_conversao_aplicado and self.unidade_original:
                observacao += f" (Conversão: {self.quantidade_original} {self.unidade_original} → {self.quantidade} {self.unidade})"
            
            # Registrar a quantidade atual antes da atualização para log
            quantidade_anterior = float(estoque.quantidade) if estoque.quantidade else 0
            
            # Criar e salvar a movimentação
            movimentacao = MovimentacaoEstoque(
                estoque_id=estoque.id,
                tipo_movimento='entrada',
                quantidade=self.quantidade,
                data_movimento=self.nota_fiscal.data_emissao,
                nota_fiscal_item_id=self.id,
                origem_tipo='NotaFiscal',
                origem_id=self.nota_fiscal.id,
                observacao=observacao,
                usuario_id=usuario_id
            )
            
            # Salvar movimentação (isso vai atualizar o estoque automaticamente)
            movimentacao.save()
            
            # Garantir que o estoque seja atualizado corretamente
            
            
            # Verificar se a quantidade foi realmente atualizada
            quantidade_nova = float(estoque.quantidade) if estoque.quantidade else 0
            
            # Se a quantidade não foi atualizada, forçar a atualização diretamente
            if quantidade_nova <= quantidade_anterior:
                estoque.quantidade = quantidade_anterior + float(self.quantidade)
                estoque.save()
                quantidade_nova = float(estoque.quantidade)
            
            # Atualizar status do item
            self.importado_estoque = True
            self.data_importacao_estoque = datetime.now()
            self.usuario_importacao_id = usuario_id
            self.status_importacao = 'Importado'
            self.ultima_tentativa_importacao = datetime.now()
            self.tentativas_importacao += 1
            
            # Verificar se é uma importação automática baseada na observação
            if observacao and "Importação automática" in observacao:
                import json
                self.dados_adicionais = json.dumps({
                    "importacao_automatica": True,
                    "data_importacao_automatica": datetime.now().isoformat()
                })
            
            self.save()
            
            # Verificar se o material é da categoria EPI
            # Se for, criar automaticamente um registro de EPI para este material
            from models.epi import EPI
            if self.material and self.material.categoria == 'EPI':
                # Verificar se já existe um EPI para este material
                epi_existente = EPI.query.filter_by(material_id=self.material_id).first()
                
                if not epi_existente:
                    # Criar um novo registro de EPI
                    epi = EPI()
                    epi.material_id = self.material_id
                    epi.estoque_minimo = 1  # Valor padrão
                    epi.usuario_id = usuario_id
                    
                    # Salvar o EPI (não precisa adicionar estoque, pois já foi criado como material)
                    epi.save()
                    
                    # Adicionar mensagem sobre a criação do EPI
                    mensagem_extra = f" Material identificado como EPI. Registro de EPI criado automaticamente."
                    return (True, f"Item importado com sucesso. {self.quantidade} {self.unidade or ''} adicionado(s) ao estoque. Estoque anterior: {quantidade_anterior}, Estoque atual: {quantidade_nova}{mensagem_extra}")
            
            return (True, f"Item importado com sucesso. {self.quantidade} {self.unidade or ''} adicionado(s) ao estoque. Estoque anterior: {quantidade_anterior}, Estoque atual: {quantidade_nova}")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            # Registrar a tentativa
            self.ultima_tentativa_importacao = datetime.now()
            self.tentativas_importacao += 1
            self.status_importacao = 'Erro'
            self.dados_adicionais = str(e)
            self.save()
            
            return (False, f"Erro ao importar item para estoque: {str(e)}")
    
    def __repr__(self):
        """
        Representação em string do item de nota fiscal
        """
        return f'<NotaFiscalItem {self.id} - {self.descricao[:30]}>' 