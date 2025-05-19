from wtforms import SelectField
from wtforms.widgets import Select as SelectWidget
from flask import url_for

class Select2Widget(SelectWidget):
    """
    Widget customizado para usar com Select2 JavaScript
    """
    def __call__(self, field, **kwargs):
        kwargs.setdefault('data-role', 'select2')
        if field.allow_blank:
            kwargs['data-allow-blank'] = 'true'
        if field.endpoint:
            kwargs['data-endpoint'] = field.endpoint
        if field.display_key:
            kwargs['data-display-key'] = field.display_key
        return super(Select2Widget, self).__call__(field, **kwargs)

class Select2Field(SelectField):
    """
    Campo de seleção com suporte para Select2 JavaScript.
    Suporta carregar dados dinamicamente via AJAX.
    """
    widget = Select2Widget()
    
    def __init__(self, label=None, validators=None, endpoint=None, display_key='name', 
                 allow_blank=True, blank_text='', **kwargs):
        super(Select2Field, self).__init__(label, validators=validators, **kwargs)
        self.endpoint = endpoint
        self.display_key = display_key
        self.allow_blank = allow_blank
        self.blank_text = blank_text
        
        # Adicionar opção em branco se permitido
        if allow_blank:
            self.choices = [('', blank_text)] + (self.choices or [])
    
    def pre_validate(self, form):
        """
        Desabilita a validação de choices para permitir valores carregados via AJAX
        que não estão na lista de choices inicial
        """
        if self.endpoint:  # Se tem endpoint, significa que os dados vêm via AJAX
            return True
        return super(Select2Field, self).pre_validate(form)