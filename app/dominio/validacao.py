"""Validações de domínio para envio de Relatos e Pedidos de Ajuda.

Funções puras que verificam as regras de entrada obrigatórias do domínio
Refúgio e sinalizam falhas por meio da exceção ``ErroValidacao``. A camada de
API converte essa exceção na resposta JSON padronizada
``{ "erro": <mensagem>, "campo": <opcional> }`` com status 400.

O Nível_de_Gravidade é armazenado como as strings 'baixo', 'medio' e 'alto'
(sem acento em 'medio', conforme o enum do modelo de dados). As mensagens
voltadas ao Cidadão, porém, listam os valores com a grafia natural
"baixo", "médio", "alto" exigida pelos critérios de aceitação.

Referências de design:
- Envio de Relatos (R4.2, R4.3, R4.4)
- Pedido de Ajuda (R11.2)
- Error Handling — mensagens padronizadas e formato de erro
"""

# Níveis de gravidade aceitos no armazenamento (sem acento em 'medio').
NIVEIS_VALIDOS = ("baixo", "medio", "alto")

# Rótulos exibidos ao Cidadão (com a grafia natural "médio"), usados na
# mensagem de erro de nível inválido (R4.4).
_NIVEIS_EXIBIDOS = ("baixo", "médio", "alto")

# Mensagens exigidas pelos critérios de aceitação (Error Handling).
MSG_DESCRICAO_OBRIGATORIA = "a descrição é obrigatória"
MSG_FOTO_OBRIGATORIA = "a foto é obrigatória"

# Nomes de campo usados na resposta de erro padronizada.
CAMPO_DESCRICAO = "descricao"
CAMPO_FOTO = "foto"
CAMPO_NIVEL = "nivel_gravidade"


class ErroValidacao(Exception):
    """Erro de validação de domínio.

    Carrega a ``mensagem`` destinada ao Cidadão e, opcionalmente, o ``campo``
    que originou a falha, de modo a alimentar a resposta JSON padronizada
    ``{ "erro", "campo" }`` usada pela API.
    """

    def __init__(self, mensagem: str, campo: str | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.campo = campo


def _descricao_vazia(descricao) -> bool:
    """Retorna True quando a descrição é ausente, vazia ou apenas espaços."""
    return descricao is None or not descricao.strip()


def validar_relato(descricao, nivel, tem_foto) -> None:
    """Valida os dados de envio de um Relato (R4.2, R4.3, R4.4).

    Regras, na ordem de verificação:
        1. Descrição vazia/apenas espaços é rejeitada (R4.2).
        2. Ausência de foto é rejeitada (R4.3).
        3. Nível fora de {'baixo', 'medio', 'alto'} é rejeitado, com mensagem
           listando os valores válidos "baixo", "médio", "alto" (R4.4).

    Args:
        descricao: Descrição textual do Relato.
        nivel: Nível_de_Gravidade informado ('baixo', 'medio' ou 'alto').
        tem_foto: Indicador booleano de que uma foto foi anexada ao Relato.

    Returns:
        ``None`` quando o Relato é válido.

    Raises:
        ErroValidacao: quando qualquer regra acima é violada; a instância
            carrega a ``mensagem`` e o ``campo`` correspondente.
    """
    if _descricao_vazia(descricao):
        raise ErroValidacao(MSG_DESCRICAO_OBRIGATORIA, campo=CAMPO_DESCRICAO)

    if not tem_foto:
        raise ErroValidacao(MSG_FOTO_OBRIGATORIA, campo=CAMPO_FOTO)

    if nivel not in NIVEIS_VALIDOS:
        validos = ", ".join(_NIVEIS_EXIBIDOS)
        raise ErroValidacao(
            f"o nível de gravidade deve ser um dos valores: {validos}",
            campo=CAMPO_NIVEL,
        )

def validar_pedido(descricao) -> None:
    """Valida os dados de criação de um Pedido de Ajuda (R11.2).

    Regra:
        1. Descrição vazia/apenas espaços é rejeitada (R11.2).

    Args:
        descricao: Descrição textual da situação informada pelo Cidadão.

    Returns:
        ``None`` quando o Pedido de Ajuda é válido.

    Raises:
        ErroValidacao: quando a descrição é ausente, vazia ou apenas espaços;
            a instância carrega a ``mensagem`` e o ``campo`` correspondente.
    """
    if _descricao_vazia(descricao):
        raise ErroValidacao(MSG_DESCRICAO_OBRIGATORIA, campo=CAMPO_DESCRICAO)
