/*
 * Tela "Pedir ajuda" — comportamento (tarefa 12.4).
 *
 * JavaScript vanilla, sem dependências. Ao submeter o formulário, publica um
 * Pedido de Ajuda via `POST /api/pedidos` (R11.1) e:
 *   - exibe a confirmação de publicação em caso de sucesso (R11.7);
 *   - exibe a mensagem de erro devolvida pela API em caso de 400, incluindo a
 *     rejeição por descrição obrigatória (R11.2) e a rejeição do Filtro de
 *     Conteúdo ("solicitações de pagamento não são permitidas por motivo de
 *     segurança", R11.5).
 *
 * O corpo da requisição exige `municipio_id` e `usuario_id`. Para o protótipo,
 * o `municipio_id` é o do Município padrão (obtido de `GET /api/municipios`) e
 * o `usuario_id` é fixo em 1 — o Cidadão de exemplo semeado no banco. A
 * localização (lat/lng) é opcional e pode ser preenchida via
 * `navigator.geolocation` ou manualmente.
 *
 * Após publicar, a lista de Pedidos recentes do Município é recarregada via
 * `GET /api/pedidos` (R11.8). Todas as chamadas usam caminhos relativos.
 */
(function () {
  "use strict";

  // usuario_id fixo do Cidadão de exemplo semeado no banco (protótipo).
  var USUARIO_ID_PROTOTIPO = 1;

  var form = document.getElementById("form-pedido");
  var campoDescricao = document.getElementById("descricao");
  var campoLat = document.getElementById("lat");
  var campoLng = document.getElementById("lng");
  var btnEnviar = document.getElementById("btn-enviar");
  var btnGps = document.getElementById("btn-gps");
  var statusLocal = document.getElementById("status-local");
  var regiaoMensagem = document.getElementById("mensagem");
  var listaRecentes = document.getElementById("lista-recentes");
  var recentesVazio = document.getElementById("recentes-vazio");

  // Município padrão resolvido a partir de /api/municipios (preenchido no load).
  var municipioId = null;

  // ---------------------------------------------------------------------
  // Detecção de recurso necessário (R10.8): sem fetch, exibe o aviso de
  // navegadores compatíveis e interrompe a inicialização.
  // ---------------------------------------------------------------------
  if (typeof window.fetch !== "function") {
    var aviso = document.getElementById("aviso-navegador");
    if (aviso) {
      aviso.hidden = false;
    }
    if (btnEnviar) {
      btnEnviar.disabled = true;
    }
    return;
  }

  // ---------------------------------------------------------------------
  // Mensagens (confirmação R11.7 / erros R11.2 e R11.5)
  // ---------------------------------------------------------------------

  /**
   * Exibe uma mensagem na região aria-live e move o foco para ela.
   * @param {string} texto Conteúdo a exibir.
   * @param {boolean} erro Quando true, aplica o estilo de erro (cor de ação).
   */
  function mostrarMensagem(texto, erro) {
    regiaoMensagem.textContent = texto;
    regiaoMensagem.hidden = false;
    regiaoMensagem.style.borderLeft = "6px solid " + (erro ? "#c9291c" : "#9dc48c");
    regiaoMensagem.style.color = erro ? "#c9291c" : "var(--cor-texto)";
    regiaoMensagem.focus();
  }

  // ---------------------------------------------------------------------
  // Localização via GPS (opcional)
  // ---------------------------------------------------------------------
  if (btnGps) {
    btnGps.addEventListener("click", function () {
      if (!navigator.geolocation) {
        statusLocal.textContent =
          "Localização automática indisponível. Informe as coordenadas manualmente.";
        return;
      }
      statusLocal.textContent = "Obtendo sua localização…";
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          campoLat.value = pos.coords.latitude.toFixed(6);
          campoLng.value = pos.coords.longitude.toFixed(6);
          statusLocal.textContent = "Localização preenchida pelo GPS do aparelho.";
        },
        function () {
          statusLocal.textContent =
            "Não foi possível obter o GPS. Informe as coordenadas manualmente.";
        }
      );
    });
  }

  // ---------------------------------------------------------------------
  // Resolução do Município padrão (GET /api/municipios)
  // ---------------------------------------------------------------------

  /**
   * Busca o id do Município padrão. Usa o campo `padrao`; se nenhum estiver
   * marcado, cai para o primeiro Município da lista.
   * @returns {Promise<number|null>} id do Município, ou null em caso de falha.
   */
  function resolverMunicipioPadrao() {
    return fetch("/api/municipios")
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("falha ao carregar municípios");
        }
        return resp.json();
      })
      .then(function (dados) {
        var municipios = (dados && dados.municipios) || [];
        if (municipios.length === 0) {
          return null;
        }
        var padrao = municipios.filter(function (m) {
          return m.padrao;
        })[0];
        return (padrao || municipios[0]).id;
      })
      .catch(function () {
        return null;
      });
  }

  // ---------------------------------------------------------------------
  // Lista de Pedidos recentes (GET /api/pedidos, R11.8)
  // ---------------------------------------------------------------------

  /** Formata um ISO datetime para exibição amigável, com fallback para o bruto. */
  function formatarData(iso) {
    var data = new Date(iso);
    if (isNaN(data.getTime())) {
      return iso;
    }
    return data.toLocaleString("pt-BR");
  }

  /** Cria o item de lista (card) para um Pedido de Ajuda. */
  function criarItemPedido(pedido) {
    var li = document.createElement("li");
    li.className = "card";

    var descricao = document.createElement("p");
    descricao.style.margin = "0 0 0.5rem";
    descricao.textContent = pedido.descricao;
    li.appendChild(descricao);

    var meta = document.createElement("p");
    meta.style.margin = "0";
    meta.style.color = "var(--cor-texto-suave)";
    meta.style.fontSize = "0.9rem";

    var partes = [formatarData(pedido.criado_em)];
    if (pedido.lat != null && pedido.lng != null) {
      partes.push(
        "Local: " + Number(pedido.lat).toFixed(4) + ", " + Number(pedido.lng).toFixed(4)
      );
    } else {
      partes.push("Sem localização informada");
    }
    meta.textContent = partes.join(" · ");
    li.appendChild(meta);

    return li;
  }

  /** Recarrega a lista de Pedidos recentes do Município. */
  function carregarRecentes() {
    var url = "/api/pedidos";
    if (municipioId != null) {
      url += "?municipio_id=" + encodeURIComponent(municipioId);
    }
    return fetch(url)
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("falha ao listar pedidos");
        }
        return resp.json();
      })
      .then(function (pedidos) {
        listaRecentes.innerHTML = "";
        if (!pedidos || pedidos.length === 0) {
          recentesVazio.hidden = false;
          return;
        }
        recentesVazio.hidden = true;
        pedidos.forEach(function (pedido) {
          listaRecentes.appendChild(criarItemPedido(pedido));
        });
      })
      .catch(function () {
        // Falha silenciosa: a listagem é auxiliar e não bloqueia o envio.
      });
  }

  // ---------------------------------------------------------------------
  // Envio do Pedido (POST /api/pedidos)
  // ---------------------------------------------------------------------

  form.addEventListener("submit", function (evento) {
    evento.preventDefault();

    var descricao = campoDescricao.value;

    // Monta o corpo exigido pela API. Envia lat/lng apenas quando informados.
    var corpo = {
      descricao: descricao,
      municipio_id: municipioId,
      usuario_id: USUARIO_ID_PROTOTIPO,
    };

    var lat = parseFloat(campoLat.value);
    var lng = parseFloat(campoLng.value);
    if (!isNaN(lat) && !isNaN(lng)) {
      corpo.lat = lat;
      corpo.lng = lng;
    }

    btnEnviar.disabled = true;

    fetch("/api/pedidos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    })
      .then(function (resp) {
        return resp.json().then(function (dados) {
          return { ok: resp.ok, dados: dados };
        });
      })
      .then(function (resultado) {
        if (resultado.ok) {
          // Sucesso: exibe a confirmação (R11.7) e limpa o formulário.
          var msg =
            (resultado.dados && resultado.dados.mensagem) ||
            "Pedido de ajuda publicado com sucesso.";
          mostrarMensagem(msg, false);
          form.reset();
          statusLocal.textContent = "";
          return carregarRecentes();
        }
        // Erro (400): exibe a mensagem `erro` devolvida pela API. Cobre a
        // descrição obrigatória (R11.2) e a rejeição do Filtro de Conteúdo
        // (R11.5), cuja mensagem vem diretamente do backend.
        var erro =
          (resultado.dados && resultado.dados.erro) ||
          "Não foi possível publicar o pedido. Tente novamente.";
        mostrarMensagem(erro, true);
      })
      .catch(function () {
        mostrarMensagem(
          "Não foi possível conectar ao servidor. Verifique sua conexão e tente novamente.",
          true
        );
      })
      .then(function () {
        btnEnviar.disabled = false;
      });
  });

  // ---------------------------------------------------------------------
  // Inicialização
  // ---------------------------------------------------------------------
  resolverMunicipioPadrao().then(function (id) {
    municipioId = id;
    carregarRecentes();
  });
})();
