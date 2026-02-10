$(function() {
  // Submissão AJAX do acabamento
  $('#formAcabamento').on('submit', function(e) {
    e.preventDefault();
    var form = $(this);
    $.post(form.attr('action'), form.serialize())
      .done(function(resp) {
        if (resp.success) {
          alert('Acabamento registrado com sucesso!');
          location.reload();
        } else {
          alert(resp.message || 'Erro ao registrar acabamento.');
        }
      })
      .fail(function(xhr) {
        alert('Erro ao registrar acabamento: ' + (xhr.responseJSON && xhr.responseJSON.message ? xhr.responseJSON.message : 'Erro desconhecido.'));
      });
  });

  // Submissão AJAX do transporte
  $('#formTransporte').on('submit', function(e) {
    e.preventDefault();
    var form = $(this);
    $.post(form.attr('action'), form.serialize())
      .done(function(resp) {
        if (resp.success) {
          alert('Transporte registrado com sucesso!');
          location.reload();
        } else {
          alert(resp.message || 'Erro ao registrar transporte.');
        }
      })
      .fail(function(xhr) {
        alert('Erro ao registrar transporte: ' + (xhr.responseJSON && xhr.responseJSON.message ? xhr.responseJSON.message : 'Erro desconhecido.'));
      });
  });

  
 // Autocomplete de transporte
 $('#transportadora').on('focus', function() {
    var tanque_ids = $('#tanque_ids').val();
    if (!tanque_ids || tanque_ids.length === 0) return;
    // Buscar peças dos tanques selecionados
    $.ajax({
      url: '/acabamento-transporte/api/transportadoras',
      method: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({ tanque_ids: tanque_ids }),
      headers: {
        'X-CSRFToken': $('input[name="csrf_token"]').val()
      },
      success: function(data) {
        console.log(data);
        var transportadoras = data.map(function(p) { return p; });
        $('#transportadora').autocomplete({
          source: transportadoras,
          minLength: 2
        });
      }
    });
  });
  

 
  // Inicialização do select2 para o campo de peça no acabamento (agora múltiplo)
  $('#acabamento-peca_id').select2({
    dropdownParent: $('#modalAcabamento'),
    theme: 'bootstrap-5',
    placeholder: 'Pesquise a peça pelo nome',
    allowClear: true,
    multiple: true,
    width: '100%',
    scrollAfterSelect: true,
    dropdownAutoWidth: true,
    ajax: {
      url: '/acabamento-transporte/api/pecas',
      method: 'GET',
      dataType: 'json',
      delay: 250,
      data: function(params) {
        return {
          tanque_ids: [$('#acabamento-tanque_id').val()],
          nome: params.term || '',
          apenas_concretadas: 1,
          apenas_acabadas:0,
          nao_acabadas: 1
        };
      },
      processResults: function(data) {
        return {
          results: data.map(function(peca) {
            return {
              id: peca.id,
              text: peca.nome + ' (' + peca.numero_sequencial + ')',
              tanque_nome: peca.tanque_nome
            };
          })
        };
      },
      cache: true
    },
    minimumInputLength: 2
  });
  $('#transporte-peca_id').select2({
    dropdownParent: $('#modalTransporte'),
    theme: 'bootstrap-5',
    placeholder: 'Pesquise a peça pelo nome',
    allowClear: true,
    multiple: true,
    width: '100%',
    scrollAfterSelect: true,
    dropdownAutoWidth: true,
    ajax: {
      url: '/acabamento-transporte/api/pecas',
      method: 'GET',
      dataType: 'json',
      delay: 250,
      data: function(params) {
        return {
          tanque_ids: [$('#transporte-tanque_ids').val()],
          nome: params.term || '',
          apenas_concretadas: 1,
          apenas_acabadas:0,
          nao_acabadas: 0
        };
      },
      processResults: function(data) {
        return {
          results: data.map(function(peca) {
            return {
              id: peca.id,
              text: peca.tanque_nome + ' - ' + peca.nome,
              tanque_nome: peca.tanque_nome
            };
          })
        };
      },
      cache: true
    },
    minimumInputLength: 2
  });
  $('#transporte-tanque_id').select2({
    dropdownParent: $('#modalTransporte'),
    theme: 'bootstrap-5',
    placeholder: 'Pesquise a peça pelo nome',
    allowClear: true,
    multiple: true,
    ajax: {
      url: '/acabamento-transporte/api/tanques',
      method: 'GET',
      dataType: 'json',
      delay: 250,

      processResults: function(data) {
        return {
          results: data.map(function(tanque) {
            return {
              id: tanque.id,
              text: tanque.nome
            };
          })
        };
      },
      cache: true
    },
  });
  // Limpar o select2 ao trocar o tanque
  $('#tanque_id').on('change', function() {
    $('#peca_id').val(null).trigger('change');
  });

  // --- Nota Fiscal: autocomplete com notas de venda da matriz ---
  $('#nota_fiscal').autocomplete({
    source: function(request, response) {
      $.get('/acabamento-transporte/api/notas-venda-matriz', { q: request.term || '' }, function(data) {
        var list = Array.isArray(data) ? data : (data && typeof data === 'object' && !Array.isArray(data) ? [data] : []);
        var items = list.map(function(n) {
          var num = n.numero_nf != null ? String(n.numero_nf) : '';
          var dest = (n.nome_destinatario || '').substring(0, 40);
          var dataEmissao = n.data_emissao || '';
          return {
            label: 'NF ' + num + ' - ' + dest + (dataEmissao ? ' (' + dataEmissao + ')' : ''),
            value: num,
            chave_acesso: n.chave_acesso || '',
            numero_nf: num
          };
        });
        response(items);
      }).fail(function() { response([]); });
    },
    minLength: 0,
    delay: 0,
    appendTo: '#modalTransporte .modal-body',
    select: function(event, ui) {
      $('#nota_fiscal').val(ui.item.numero_nf);
      $('#nota_fiscal_chave').val(ui.item.chave_acesso || '');
      $('#cte_frete').val('').prop('readonly', false).attr('placeholder', 'Carregando CT-e...');
      var chave = ui.item.chave_acesso;
      if (chave) {
        $.get('/acabamento-transporte/api/cte-por-nota', { chave_nf: chave }, function(ctes) {
          if ($('#cte_frete').autocomplete('instance')) {
            $('#cte_frete').autocomplete('destroy');
          }
          var itensCte = (ctes || []).map(function(c) {
            var desc = 'CT-e ' + c.numero_nf;
            if (c.placa) desc += ' - Placa ' + c.placa;
            if (c.nome_emitente) desc += ' - ' + c.nome_emitente;
            return { label: desc, value: c.numero_nf, placa: c.placa || '', transportadora: c.nome_emitente || '' };
          });
          if (itensCte.length === 0) {
            $('#cte_frete').attr('placeholder', 'Nenhum CT-e vinculado a esta NF');
            return;
          }
          $('#cte_frete').attr('placeholder', 'Selecione o CT-e (opcional)');
          $('#cte_frete').autocomplete({
            source: itensCte,
            minLength: 0,
            appendTo: '#modalTransporte .modal-body',
            select: function(ev, u) {
              if (u.item.placa) $('#placa_carreta').val(u.item.placa);
              if (u.item.transportadora) $('#transportadora').val(u.item.transportadora);
            }
          });
        }).fail(function() {
          $('#cte_frete').attr('placeholder', 'Erro ao carregar CT-e');
        });
      } else {
        $('#cte_frete').attr('placeholder', 'Selecione a nota acima para carregar CT-e');
      }
      return false;
    }
  });
  // Ao focar no campo, abrir lista (com minLength 0 mostra as últimas notas mesmo sem digitar)
  $('#nota_fiscal').on('focus', function() {
    var $el = $(this);
    if ($el.autocomplete('instance')) {
      $el.autocomplete('search', $el.val() || '');
    }
  });

  // Ao abrir o modal de transporte, limpar chave e CT-e
  $('#modalTransporte').on('show.bs.modal', function() {
    $('#nota_fiscal_chave').val('');
    $('#cte_frete').val('').prop('readonly', true).attr('placeholder', 'Selecione a nota acima para carregar CT-e');
    if ($('#cte_frete').autocomplete('instance')) {
      $('#cte_frete').autocomplete('destroy');
    }
  });

  // Remover autocomplete/datalist antigo do campo de peça no acabamento, se existir
  $('#peca_nome').autocomplete && $('#peca_nome').autocomplete('destroy');
  $('#datalistPecas').remove();
}); 