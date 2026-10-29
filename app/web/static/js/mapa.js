/* =========================================================================
   Refúgio — Tela Mapa (tarefa 12.3)
   -------------------------------------------------------------------------
   JavaScript vanilla (sem passo de build) que inicializa o mapa Leaflet e
   desenha, sobre o Município selecionado, as camadas consumidas da API:

     - Áreas Afetadas   GET /api/areas           -> polígonos coloridos (R1.1, R1.2, R12.x)
     - Abrigos          GET /api/abrigos         -> marcadores (nome/endereco/capacidade) (R2.1, R2.2)
     - Relatos          GET /api/relatos         -> marcadores por nível + foto (R5.1, R5.2)
     - Incidentes       GET /api/incidentes      -> círculo por gravidade média + veracidade (R9.6, R12.4)
     - Incidentes Ext.  GET /api/incidentes-externos -> procedência Portal (R15.3)

   Botões-pílula alternam a visibilidade de cada camada; o seletor de
   gravidade re-consulta /api/relatos?gravidade= (R5.3). O card de detalhe
   exibe os dados do elemento selecionado. Quando os tiles do OpenStreetMap
   falham ao carregar, o aviso de navegadores compatíveis é exibido (R10.8).

   Cores de gravidade (R12.1–R12.3) — alinhadas ao Sistema de Design:
     baixo  -> amarelo  #F2C94C
     medio  -> laranja  #E8A028
     alto   -> vermelho #C9291C
   ========================================================================= */

(function () {
  "use strict";

  // Cores de gravidade por nível (R12.1–R12.3). Espelham estilo.css.
  var COR_POR_NIVEL = {
    baixo: "#F2C94C",
    medio: "#E8A028",
    alto: "#C9291C",
  };

  // Rótulos legíveis por nível de gravidade.
  var ROTULO_NIVEL = {
    baixo: "Baixa",
    medio: "Média",
    alto: "Alta",
  };

  // Cor neutra usada para incidentes externos sem gravidade classificável
  // (coerente com COR_NEUTRA_EXTERNA do backend).
  var COR_EXTERNA_NEUTRA = "#6B7A8F";

  // Centro de fallback (Ribeirão Preto) caso /api/municipios falhe.
  var CENTRO_PADRAO = [-21.1775, -47.8103];
  var ZOOM_PADRAO = 12;

  // Estado da aplicação da tela.
  var mapa = null;
  var municipioAtual = null; // { id, nome, centro_lat, centro_lng, padrao }
  var tilesOk = false;

  // Grupos de camadas do Leaflet, um por tipo de dado.
  var camadas = {
    areas: null,
    abrigos: null,
    relatos: null,
    incidentes: null,
    externos: null,
  };

  // Elementos de UI reaproveitados.
  var elDetalhe = null;
  var elAvisoTiles = null;
  var elRotuloMunicipio = null;

  /* -----------------------------------------------------------------------
     Utilidades
     ----------------------------------------------------------------------- */

  // Escapa texto para inserção segura em HTML (evita quebra de popups/markup).
  function escaparHtml(valor) {
    if (valor === null || valor === undefined) {
      return "";
    }
    return String(valor)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Busca JSON de um endpoint relativo, lançando em respostas não-OK.
  function obterJson(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (
      resposta
    ) {
      if (!resposta.ok) {
        throw new Error("Falha ao consultar " + url + " (HTTP " + resposta.status + ")");
      }
      return resposta.json();
    });
  }

  // Deriva a cor de uma gravidade média contínua em [1.0, 3.0] (R12.4).
  function corPorMedia(media) {
    if (media <= 1.5) {
      return COR_POR_NIVEL.baixo;
    }
    if (media <= 2.5) {
      return COR_POR_NIVEL.medio;
    }
    return COR_POR_NIVEL.alto;
  }

  // Cria um ícone de ponto colorido (divIcon) para marcadores de Relatos.
  function iconePonto(cor, tamanho) {
    var px = tamanho || 18;
    return L.divIcon({
      className: "",
      html:
        '<span class="marcador-ponto" style="background:' +
        escaparHtml(cor) +
        '"></span>',
      iconSize: [px, px],
      iconAnchor: [px / 2, px / 2],
    });
  }

  /* -----------------------------------------------------------------------
     Card de detalhe
     ----------------------------------------------------------------------- */

  // Renderiza o card de detalhe a partir de um título e uma lista de pares.
  // "linhas" é um array de { rotulo, valor } (valor já escapado quando HTML).
  function mostrarDetalhe(titulo, linhas, extrasHtml) {
    var html = "<h2>" + escaparHtml(titulo) + "</h2><dl>";
    linhas.forEach(function (linha) {
      if (linha.valor === null || linha.valor === undefined || linha.valor === "") {
        return;
      }
      html +=
        "<dt>" +
        escaparHtml(linha.rotulo) +
        "</dt><dd>" +
        (linha.html ? linha.valor : escaparHtml(linha.valor)) +
        "</dd>";
    });
    html += "</dl>";
    if (extrasHtml) {
      html += extrasHtml;
    }
    elDetalhe.innerHTML = html;
  }

  // Monta uma pastilha colorida (selo) para gravidade por nível.
  function pastilhaNivel(nivel) {
    var rotulo = ROTULO_NIVEL[nivel] || nivel || "—";
    var classe =
      nivel === "baixo"
        ? "gravidade-baixo"
        : nivel === "medio"
        ? "gravidade-medio"
        : nivel === "alto"
        ? "gravidade-alto"
        : "";
    return '<span class="pastilha ' + classe + '">' + escaparHtml(rotulo) + "</span>";
  }

  /* -----------------------------------------------------------------------
     Desenho das camadas
     ----------------------------------------------------------------------- */

  // Áreas Afetadas: polígonos coloridos pela Cor_de_Gravidade (R1.1, R1.2).
  function desenharAreas(dados) {
    var grupo = camadas.areas;
    grupo.clearLayers();

    var areas = (dados && dados.areas) || [];
    areas.forEach(function (area) {
      if (!area.poligono || area.poligono.length < 3) {
        return;
      }
      var cor = area.cor || COR_POR_NIVEL[area.nivel_gravidade] || COR_EXTERNA_NEUTRA;
      var poligono = L.polygon(area.poligono, {
        color: cor,
        weight: 2,
        fillColor: cor,
        fillOpacity: 0.35,
      });
      poligono.on("click", function () {
        mostrarDetalhe("Área afetada", [
          { rotulo: "Descrição", valor: area.descricao },
          {
            rotulo: "Gravidade",
            valor: pastilhaNivel(area.nivel_gravidade),
            html: true,
          },
          { rotulo: "Atualizada em", valor: area.atualizado_em },
        ]);
      });
      poligono.addTo(grupo);
    });
  }

  // Abrigos: marcadores com nome, endereço e capacidade (R2.1, R2.2).
  function desenharAbrigos(dados) {
    var grupo = camadas.abrigos;
    grupo.clearLayers();

    var abrigos = (dados && dados.abrigos) || [];
    abrigos.forEach(function (abrigo) {
      if (abrigo.lat === null || abrigo.lng === null) {
        return;
      }
      var marcador = L.marker([abrigo.lat, abrigo.lng], {
        alt: "Abrigo: " + (abrigo.nome || ""),
        title: abrigo.nome || "Abrigo",
      });

      var capacidade =
        abrigo.capacidade !== null && abrigo.capacidade !== undefined
          ? abrigo.capacidade + " pessoas"
          : "não informada";

      marcador.bindPopup(
        "<strong>" +
          escaparHtml(abrigo.nome || "Abrigo") +
          "</strong><br>" +
          escaparHtml(abrigo.endereco || "") +
          "<br>Capacidade: " +
          escaparHtml(capacidade)
      );

      marcador.on("click", function () {
        var linhas = [
          { rotulo: "Endereço", valor: abrigo.endereco },
          { rotulo: "Capacidade", valor: capacidade },
        ];
        if (
          abrigo.distancia_metros !== null &&
          abrigo.distancia_metros !== undefined
        ) {
          linhas.push({
            rotulo: "Distância",
            valor: Math.round(abrigo.distancia_metros) + " m",
          });
        }
        mostrarDetalhe(abrigo.nome || "Abrigo", linhas);
      });

      marcador.addTo(grupo);
    });
  }

  // Relatos: marcadores coloridos por nível, popup com descrição/foto (R5.2).
  function desenharRelatos(dados) {
    var grupo = camadas.relatos;
    grupo.clearLayers();

    var relatos = (dados && dados.relatos) || [];
    relatos.forEach(function (relato) {
      if (relato.lat === null || relato.lng === null) {
        return;
      }
      var cor = COR_POR_NIVEL[relato.nivel_gravidade] || COR_EXTERNA_NEUTRA;
      var marcador = L.marker([relato.lat, relato.lng], {
        icon: iconePonto(cor, 18),
        alt:
          "Reporte da comunidade, gravidade " +
          (ROTULO_NIVEL[relato.nivel_gravidade] || "desconhecida"),
        title: relato.descricao || "Reporte",
      });

      // Caminho da foto servido em /fotos (R5.2). foto_path guarda o nome/caminho.
      var fotoUrl = null;
      if (relato.foto_path) {
        var nome = String(relato.foto_path).replace(/^.*[\\/]/, "");
        fotoUrl = "/fotos/" + encodeURIComponent(nome);
      }

      var popup =
        pastilhaNivel(relato.nivel_gravidade) +
        (relato.validado ? ' <span class="pastilha">Validado</span>' : "") +
        "<br>" +
        escaparHtml(relato.descricao || "");
      if (fotoUrl) {
        popup +=
          '<br><img src="' +
          escaparHtml(fotoUrl) +
          '" alt="Foto do reporte da comunidade" style="max-width:200px;margin-top:6px;border-radius:10px">';
      }
      marcador.bindPopup(popup);

      marcador.on("click", function () {
        var extras = fotoUrl
          ? '<img src="' +
            escaparHtml(fotoUrl) +
            '" alt="Foto do reporte da comunidade">'
          : "";
        mostrarDetalhe(
          "Reporte da comunidade",
          [
            {
              rotulo: "Gravidade",
              valor: pastilhaNivel(relato.nivel_gravidade),
              html: true,
            },
            { rotulo: "Descrição", valor: relato.descricao },
            { rotulo: "Validado", valor: relato.validado ? "Sim" : "Não" },
            { rotulo: "Enviado em", valor: relato.criado_em },
          ],
          extras
        );
      });

      marcador.addTo(grupo);
    });
  }

  // Incidentes locais: círculo colorido pela gravidade média; mostra
  // gravidade média e veracidade no detalhe (R9.6, R12.4).
  function desenharIncidentes(dados) {
    var grupo = camadas.incidentes;
    grupo.clearLayers();

    var incidentes = (dados && dados.incidentes) || [];
    incidentes.forEach(function (incidente) {
      if (incidente.centro_lat === null || incidente.centro_lng === null) {
        return;
      }
      var cor = incidente.cor || corPorMedia(incidente.gravidade_media || 1);
      var circulo = L.circleMarker([incidente.centro_lat, incidente.centro_lng], {
        radius: 12,
        color: cor,
        weight: 3,
        fillColor: cor,
        fillOpacity: 0.5,
      });

      var mediaFmt =
        incidente.gravidade_media !== null && incidente.gravidade_media !== undefined
          ? incidente.gravidade_media.toFixed(2)
          : "—";

      circulo.on("click", function () {
        mostrarDetalhe("Incidente", [
          { rotulo: "Tipo", valor: incidente.tipo },
          { rotulo: "Gravidade média", valor: mediaFmt },
          { rotulo: "Veracidade", valor: incidente.veracidade },
          { rotulo: "Nº de reportes", valor: incidente.qtd_relatos },
        ]);
      });

      circulo.bindTooltip(
        "Incidente — gravidade " + mediaFmt + " · veracidade " +
          escaparHtml(incidente.veracidade || "—")
      );
      circulo.addTo(grupo);
    });
  }

  // Incidentes Externos: marcador distinto com selo de procedência (R15.3).
  function desenharExternos(dados) {
    var grupo = camadas.externos;
    grupo.clearLayers();

    var externos = (dados && dados.incidentes_externos) || [];
    var fonte = (dados && dados.fonte) || "Portal de Dados Abertos";

    externos.forEach(function (ext) {
      if (ext.centro_lat === null || ext.centro_lng === null) {
        return;
      }
      var cor = ext.cor || COR_EXTERNA_NEUTRA;
      // Losango (quadrado rotacionado) para diferenciar visualmente a origem.
      var marcador = L.marker([ext.centro_lat, ext.centro_lng], {
        icon: L.divIcon({
          className: "",
          html:
            '<span class="marcador-ponto" style="background:' +
            escaparHtml(cor) +
            ";transform:rotate(45deg);border-radius:3px" +
            '"></span>',
          iconSize: [20, 20],
          iconAnchor: [10, 10],
        }),
        alt: "Incidente externo — fonte: " + fonte,
        title: "Incidente externo (" + fonte + ")",
      });

      var gravFmt =
        ext.gravidade_externa !== null && ext.gravidade_externa !== undefined
          ? ext.gravidade_externa
          : "não informada";

      marcador.bindPopup(
        '<span class="selo-externo">fonte: ' +
          escaparHtml(fonte) +
          "</span><br><strong>" +
          escaparHtml(ext.tipo || "Incidente externo") +
          "</strong><br>Gravidade: " +
          escaparHtml(gravFmt)
      );

      marcador.on("click", function () {
        mostrarDetalhe(
          "Incidente externo",
          [
            { rotulo: "Tipo", valor: ext.tipo },
            { rotulo: "Gravidade", valor: gravFmt },
            { rotulo: "Identificador", valor: ext.id_externo },
          ],
          '<p style="margin:8px 0 0"><span class="selo-externo">fonte: ' +
            escaparHtml(fonte) +
            "</span></p>"
        );
      });

      marcador.addTo(grupo);
    });
  }

  /* -----------------------------------------------------------------------
     Carga de dados
     ----------------------------------------------------------------------- */

  // Exibe a mensagem de ausência de dados no card de detalhe, se aplicável.
  function registrarMensagem(mensagem) {
    if (mensagem) {
      // Mensagens de ausência (R1.3, R2.3) ficam disponíveis no console e no
      // detalhe inicial; não sobrescrevem uma seleção ativa do usuário.
      console.info("[Refúgio/Mapa]", mensagem);
    }
  }

  // Carrega Relatos respeitando o filtro de gravidade selecionado (R5.3).
  function carregarRelatos() {
    var sel = document.getElementById("filtro-gravidade");
    var gravidade = sel ? sel.value : "";
    var url = "/api/relatos";
    if (gravidade) {
      url += "?gravidade=" + encodeURIComponent(gravidade);
    }
    return obterJson(url)
      .then(desenharRelatos)
      .catch(function (erro) {
        console.error(erro);
      });
  }

  // Carrega todas as camadas do Município atual.
  function carregarCamadas() {
    var promessas = [];

    promessas.push(
      obterJson("/api/areas")
        .then(function (d) {
          desenharAreas(d);
          registrarMensagem(d.mensagem);
        })
        .catch(function (e) {
          console.error(e);
        })
    );

    promessas.push(
      obterJson("/api/abrigos")
        .then(function (d) {
          desenharAbrigos(d);
          registrarMensagem(d.mensagem);
        })
        .catch(function (e) {
          console.error(e);
        })
    );

    promessas.push(carregarRelatos());

    promessas.push(
      obterJson("/api/incidentes")
        .then(desenharIncidentes)
        .catch(function (e) {
          console.error(e);
        })
    );

    promessas.push(
      obterJson("/api/incidentes-externos")
        .then(desenharExternos)
        .catch(function (e) {
          console.error(e);
        })
    );

    return Promise.all(promessas);
  }

  /* -----------------------------------------------------------------------
     Filtros de camada (botões-pílula)
     ----------------------------------------------------------------------- */

  function alternarCamada(nome, ativo) {
    var grupo = camadas[nome];
    if (!grupo) {
      return;
    }
    if (ativo) {
      if (!mapa.hasLayer(grupo)) {
        mapa.addLayer(grupo);
      }
    } else if (mapa.hasLayer(grupo)) {
      mapa.removeLayer(grupo);
    }
  }

  function ligarBotoesFiltro() {
    var botoes = document.querySelectorAll(".mapa-filtros .botao[data-camada]");
    Array.prototype.forEach.call(botoes, function (botao) {
      botao.addEventListener("click", function () {
        var nome = botao.getAttribute("data-camada");
        var ativoAgora = botao.getAttribute("aria-pressed") === "true";
        var novo = !ativoAgora;
        botao.setAttribute("aria-pressed", novo ? "true" : "false");
        alternarCamada(nome, novo);
      });
    });

    var sel = document.getElementById("filtro-gravidade");
    if (sel) {
      sel.addEventListener("change", carregarRelatos);
    }
  }

  /* -----------------------------------------------------------------------
     Inicialização do mapa
     ----------------------------------------------------------------------- */

  function criarMapa(centro, zoom) {
    mapa = L.map("mapa", {
      center: centro,
      zoom: zoom,
      zoomControl: true,
    });

    var tiles = L.tileLayer(
      "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        maxZoom: 19,
        attribution:
          '&copy; colaboradores do <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }
    );

    // Detecta falha de carregamento de tiles e exibe o aviso (R10.8).
    tiles.on("tileerror", function () {
      if (!tilesOk) {
        mostrarAvisoTiles();
      }
    });
    tiles.on("tileload", function () {
      tilesOk = true;
      esconderAvisoTiles();
    });

    tiles.addTo(mapa);

    // Rede de segurança: se nenhum tile carregar em 8s, mostra o aviso.
    setTimeout(function () {
      if (!tilesOk) {
        mostrarAvisoTiles();
      }
    }, 8000);

    // Cria os grupos de camada e os adiciona (todos visíveis por padrão).
    Object.keys(camadas).forEach(function (nome) {
      camadas[nome] = L.layerGroup().addTo(mapa);
    });
  }

  function mostrarAvisoTiles() {
    if (elAvisoTiles) {
      elAvisoTiles.hidden = false;
    }
  }

  function esconderAvisoTiles() {
    if (elAvisoTiles) {
      elAvisoTiles.hidden = true;
    }
  }

  function atualizarRotuloMunicipio() {
    if (!elRotuloMunicipio) {
      return;
    }
    if (municipioAtual && municipioAtual.nome) {
      elRotuloMunicipio.textContent = "Município: " + municipioAtual.nome;
    } else {
      elRotuloMunicipio.textContent = "Município padrão";
    }
  }

  function iniciar() {
    elDetalhe = document.getElementById("detalhe");
    elAvisoTiles = document.getElementById("aviso-tiles");
    elRotuloMunicipio = document.getElementById("rotulo-municipio");

    // Leaflet precisa estar disponível (recurso necessário, R10.8).
    if (typeof L === "undefined") {
      mostrarAvisoTiles();
      return;
    }

    // Descobre o centro do Município padrão via /api/municipios.
    obterJson("/api/municipios")
      .then(function (dados) {
        var lista = (dados && dados.municipios) || [];
        var padrao = null;
        for (var i = 0; i < lista.length; i++) {
          if (lista[i].padrao) {
            padrao = lista[i];
            break;
          }
        }
        if (!padrao && lista.length > 0) {
          padrao = lista[0];
        }
        municipioAtual = padrao;
        var centro =
          padrao && padrao.centro_lat !== undefined && padrao.centro_lng !== undefined
            ? [padrao.centro_lat, padrao.centro_lng]
            : CENTRO_PADRAO;
        return centro;
      })
      .catch(function (erro) {
        console.error(erro);
        return CENTRO_PADRAO;
      })
      .then(function (centro) {
        criarMapa(centro, ZOOM_PADRAO);
        atualizarRotuloMunicipio();
        ligarBotoesFiltro();
        return carregarCamadas();
      })
      .catch(function (erro) {
        console.error(erro);
      });
  }

  // Dispara a inicialização após o DOM estar pronto (o script usa defer, mas
  // mantemos a verificação para robustez).
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
