/**
 * Campo nome do equipamento: busca materiais (categorias Equipamento / Ferramenta).
 * Marque o input com class equipamento-busca-material-input e data-busca-url="...".
 * Envolva em .equipamento-busca-material-wrap com .equipamento-busca-material-dropdown.
 */
(function () {
    function debounce(fn, ms) {
        var t;
        return function () {
            var ctx = this;
            var args = arguments;
            clearTimeout(t);
            t = setTimeout(function () {
                fn.apply(ctx, args);
            }, ms);
        };
    }

    function escapeHtml(s) {
        var d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    function initEquipamentoBuscaMaterial() {
        document.querySelectorAll('.equipamento-busca-material-input[data-busca-url]').forEach(
            function (input) {
                var wrap = input.closest('.equipamento-busca-material-wrap');
                if (!wrap) {
                    return;
                }
                var dd = wrap.querySelector('.equipamento-busca-material-dropdown');
                if (!dd) {
                    return;
                }
                var url = input.getAttribute('data-busca-url');
                if (!url) {
                    return;
                }
                var formEl = input.closest('form');
                var matSel = formEl
                    ? formEl.querySelector('select.equipamento-select-material')
                    : null;

                function hide() {
                    dd.classList.add('d-none');
                    dd.innerHTML = '';
                }

                function show(items) {
                    dd.innerHTML = '';
                    if (!items.length) {
                        hide();
                        return;
                    }
                    items.forEach(function (it) {
                        var btn = document.createElement('button');
                        btn.type = 'button';
                        btn.className =
                            'list-group-item list-group-item-action py-2 px-3 text-start ' +
                            'border-0 border-bottom';
                        var cod = it.codigo
                            ? ' <span class="text-muted small">(' +
                              escapeHtml(it.codigo) +
                              ')</span>'
                            : '';
                        var cat = it.categoria
                            ? '<span class="badge bg-secondary ms-1">' +
                              escapeHtml(it.categoria) +
                              '</span>'
                            : '';
                        btn.innerHTML =
                            '<span class="fw-medium">' +
                            escapeHtml(it.nome) +
                            '</span>' +
                            cod +
                            cat;
                        btn.addEventListener('mousedown', function (e) {
                            e.preventDefault();
                            input.value = it.nome;
                            var label =
                                (it.nome || '') +
                                (it.codigo ? ' (' + it.codigo + ')' : '') +
                                (it.categoria ? ' [' + it.categoria + ']' : '');
                            if (
                                matSel &&
                                typeof jQuery !== 'undefined' &&
                                jQuery(matSel).data('select2')
                            ) {
                                var $m = jQuery(matSel);
                                var vid = String(it.id);
                                var jaExiste = false;
                                $m.find('option').each(function () {
                                    if (String(this.value) === vid) {
                                        jaExiste = true;
                                        return false;
                                    }
                                });
                                if (!jaExiste) {
                                    $m.append(new Option(label, vid, true, true));
                                } else {
                                    $m.val(vid);
                                }
                                $m.trigger('change');
                            } else if (matSel) {
                                matSel.value = String(it.id);
                            }
                            wrap.dataset.materialNomeVinculado = it.nome || '';
                            hide();
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                        });
                        dd.appendChild(btn);
                    });
                    dd.classList.remove('d-none');
                }

                var runSearch = debounce(function () {
                    var q = (input.value || '').trim();
                    if (q.length < 2) {
                        hide();
                        return;
                    }
                    var sep = url.indexOf('?') >= 0 ? '&' : '?';
                    fetch(url + sep + 'q=' + encodeURIComponent(q), {
                        headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    })
                        .then(function (r) {
                            return r.json();
                        })
                        .then(function (data) {
                            show(data.results || []);
                        })
                        .catch(function () {
                            hide();
                        });
                }, 300);

                if (matSel) {
                    input.addEventListener('input', function () {
                        if (!wrap.dataset.materialNomeVinculado) {
                            return;
                        }
                        var vinc = wrap.dataset.materialNomeVinculado || '';
                        if ((input.value || '').trim() !== (vinc || '').trim()) {
                            if (
                                typeof jQuery !== 'undefined' &&
                                jQuery(matSel).data('select2')
                            ) {
                                jQuery(matSel).val(null).trigger('change');
                            } else {
                                matSel.value = '';
                            }
                            delete wrap.dataset.materialNomeVinculado;
                        }
                    });
                }
                input.addEventListener('input', runSearch);
                input.addEventListener('focus', function () {
                    if ((input.value || '').trim().length >= 2) {
                        runSearch();
                    }
                });
                document.addEventListener('click', function (e) {
                    if (!wrap.contains(e.target)) {
                        hide();
                    }
                });
                input.addEventListener('keydown', function (e) {
                    if (e.key === 'Escape') {
                        hide();
                    }
                });
            }
        );
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initEquipamentoBuscaMaterial);
    } else {
        initEquipamentoBuscaMaterial();
    }
})();
