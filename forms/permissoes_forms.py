from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, NumberRange
from wtforms.widgets import TextArea

class ModuloForm(FlaskForm):
    """Formulário para criação e edição de módulos"""
    nome = StringField('Nome do Módulo', validators=[
        DataRequired(message='Nome é obrigatório'),
        Length(min=2, max=100, message='Nome deve ter entre 2 e 100 caracteres')
    ])
    
    descricao = TextAreaField('Descrição', validators=[
        Optional(),
        Length(max=500, message='Descrição deve ter no máximo 500 caracteres')
    ], render_kw={'rows': 3})
    
    icone = StringField('Ícone (Classe CSS)', validators=[
        Optional(),
        Length(max=50, message='Ícone deve ter no máximo 50 caracteres')
    ], render_kw={'placeholder': 'Ex: fas fa-users'})
    
    url = StringField('URL do Módulo', validators=[
        Optional(),
        Length(max=200, message='URL deve ter no máximo 200 caracteres')
    ], render_kw={'placeholder': 'Ex: /usuarios'})
    
    ordem = IntegerField('Ordem de Exibição', validators=[
        Optional(),
        NumberRange(min=0, max=999, message='Ordem deve ser entre 0 e 999')
    ], default=0)
    
    submit = SubmitField('Salvar')

class PermissaoForm(FlaskForm):
    """Formulário para criação e edição de permissões"""
    modulo_id = SelectField('Módulo', validators=[
        DataRequired(message='Módulo é obrigatório')
    ], coerce=int)
    
    tipo_permissao = SelectField('Tipo de Permissão', validators=[
        DataRequired(message='Tipo de permissão é obrigatório')
    ], choices=[
        ('usuario', 'Usuário Específico'),
        ('departamento', 'Departamento'),
        ('cargo', 'Cargo')
    ])
    
    usuario_id = SelectField('Usuário', validators=[
        Optional()
    ], coerce=int, choices=[])
    
    departamento_id = SelectField('Departamento', validators=[
        Optional()
    ], coerce=int, choices=[])
    
    cargo = StringField('Cargo', validators=[
        Optional(),
        Length(max=50, message='Cargo deve ter no máximo 50 caracteres')
    ], render_kw={'placeholder': 'Ex: Gerente, Técnico'})
    
    # Permissões específicas
    pode_visualizar = BooleanField('Pode Visualizar', default=True)
    pode_criar = BooleanField('Pode Criar', default=False)
    pode_editar = BooleanField('Pode Editar', default=False)
    pode_excluir = BooleanField('Pode Excluir', default=False)
    pode_exportar = BooleanField('Pode Exportar', default=False)
    
    submit = SubmitField('Salvar')
    
    def __init__(self, *args, **kwargs):
        super(PermissaoForm, self).__init__(*args, **kwargs)
        
        # Adicionar validação condicional baseada no tipo de permissão
        if self.tipo_permissao.data == 'usuario':
            self.usuario_id.validators = [DataRequired(message='Usuário é obrigatório para permissão de usuário')]
        elif self.tipo_permissao.data == 'departamento':
            self.departamento_id.validators = [DataRequired(message='Departamento é obrigatório para permissão de departamento')]
        elif self.tipo_permissao.data == 'cargo':
            self.cargo.validators = [DataRequired(message='Cargo é obrigatório para permissão de cargo')]
    
    def validate(self, extra_validators=None):
        """Validação customizada do formulário"""
        if not super().validate(extra_validators):
            return False
        
        # Validação condicional baseada no tipo de permissão
        if self.tipo_permissao.data == 'usuario' and not self.usuario_id.data:
            self.usuario_id.errors.append('Usuário é obrigatório para permissão de usuário')
            return False
        elif self.tipo_permissao.data == 'departamento' and not self.departamento_id.data:
            self.departamento_id.errors.append('Departamento é obrigatório para permissão de departamento')
            return False
        elif self.tipo_permissao.data == 'cargo' and not self.cargo.data:
            self.cargo.errors.append('Cargo é obrigatório para permissão de cargo')
            return False
        
        return True

