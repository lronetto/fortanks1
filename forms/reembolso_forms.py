from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, SelectField, SelectMultipleField, FieldList, FormField, HiddenField, FileField, TextAreaField, MultipleFileField, DateField
from wtforms.validators import DataRequired, Optional, NumberRange
from flask_wtf.file import FileAllowed, FileRequired

class DocumentoAvulsoForm(FlaskForm):
    fornecedor = StringField('Fornecedor', validators=[DataRequired()])
    ndocumento = StringField('Número do Documento', validators=[DataRequired()])
    data_documento = DateField('Data do Documento', validators=[DataRequired()])
    descricao = StringField('Descrição', validators=[DataRequired()])
    valor = DecimalField('Valor', validators=[DataRequired(), NumberRange(min=0)])
    anexos = MultipleFileField('Anexos', validators=[Optional()])

class ReembolsoForm(FlaskForm):
    centro_custo_id = SelectField('Centro de Custo', coerce=int, validators=[DataRequired()])
    notas_fiscais = SelectMultipleField('Notas Fiscais', coerce=int, validators=[Optional()])
    documentos_avulsos = FieldList(FormField(DocumentoAvulsoForm), min_entries=0)
    submit = StringField('Salvar')
    csrf_token = HiddenField() 