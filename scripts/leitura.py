"""Decodificacao do arquivo da ANP e defesa contra mojibake.

Por que este modulo existe: em 2026-10-28 (run #17) a rotina caiu com
`col 1: esperado ~'mes', achado 'MÃªs'`. `MÃªs` e a assinatura de `Mês`
gravado em UTF-8 e lido como latin-1 -- a ANP trocou o encoding do
Liquidos_Vendas_Atual.csv e o pipeline tinha `encoding="latin-1"` fixo.

A trava de cabecalho pegou o caso por sorte: das sete colunas conferidas, so
`Mês` tem acento. Num arquivo cujo cabecalho fosse todo ASCII, a troca de
encoding passaria por TODAS as travas existentes (cabecalho, validacao por
linha, tolerancia de descarte, regressao de meses e de volume -- o volume nao
muda, so os rotulos corrompem) e o data.js seria gravado com `RaÃ­zen` ao lado
de `Raízen`. O mesmo agente contado duas vezes derruba ranking, market share e,
sobretudo, o HHI, que e quadratico na participacao. Daí as duas funcoes aqui:
uma detecta o encoding em vez de assumir, a outra recusa rotulo com marca de
mojibake.

Sem dependencia nova de proposito: deteccao por tentativa de decodificacao
estrita e deterministica e testavel, ao contrario de heuristica estatistica
(chardet), que num arquivo de 62 MB ainda custaria segundos para dar um palpite.
"""

# Ordem importa. utf-8-sig cobre o arquivo com BOM (Excel/.NET costumam gravar
# assim) e e identico a utf-8 quando nao ha BOM. cp1252 vem antes de latin-1
# porque e superconjunto dele: decodifica tambem as aspas curvas e o travessao
# da faixa 0x80-0x9F, que latin-1 mapeia para controles invisiveis. latin-1 fica
# por ultimo como rede: nunca falha, decodifica qualquer byte.
CANDIDATOS = ("utf-8-sig", "cp1252", "latin-1")


# --- Deteccao de mojibake ---------------------------------------------------
# PRIMEIRA VERSAO DESTA TRAVA ESTAVA ERRADA e derrubou o run #18: ela acusava
# qualquer "Ã" ou "Â", e esses caracteres sao letras legitimas do portugues em
# CAIXA ALTA -- que e exatamente como a ANP grava os nomes de agente:
# "AGILE ... DISTRIBUIÇÃO", "ATLÂNTICA PRODUTOS DE PETRÓLEO", "TORRÃO",
# "TABOCÃO". Quatro nomes reais bastaram para parar a rotina.
#
# O critério correto nao e o caractere isolado, e o PAR. Em UTF-8, um caractere
# acentuado e dois bytes: C3/C2 (ou C5/D0) seguidos de um byte de continuacao
# na faixa 0x80-0xBF. Lido byte a byte, isso vira "Ã"/"Â" seguido do caractere
# que aquela faixa representa -- "ª", "\xad", "‡", "ƒ"... Em portugues de
# verdade, "Ã" e "Â" sao sempre seguidos de LETRA ("ÃO", "ÃE", "ÂN"), nunca de
# um caractere dessa faixa. O par e a assinatura; a letra sozinha nao e.
#
# Validado contra os 370 rotulos reais do data.js (agentes, UFs, mercados,
# produtos, meses): zero falso positivo. E contra mojibake gerado nas duas
# interpretacoes possiveis (latin-1 e cp1252) de sete nomes acentuados:
# todos pegos.
_PREFIXOS = ("Ã", "Â", "Å", "Ð")  # C3, C2, C5, D0 como byte unico


def _sufixos() -> frozenset:
    """Caracteres que representam um byte de continuacao UTF-8 (0x80-0xBF).

    Monta o conjunto nas duas interpretacoes possiveis: latin-1 (controles
    invisiveis) e cp1252 (aspas curvas, travessao, etc.), porque o mojibake
    pode ter nascido de qualquer uma das duas.
    """
    s = set()
    for b in range(0x80, 0xC0):
        s.add(bytes([b]).decode("latin-1"))
        try:
            s.add(bytes([b]).decode("cp1252"))
        except UnicodeDecodeError:   # 0x81, 0x8D, 0x8F, 0x90, 0x9D nao existem em cp1252
            pass
    return frozenset(s)


SUFIXOS_MOJIBAKE = _sufixos()

# Replacement char: sinal de que alguem decodificou com errors="replace" em
# algum ponto da cadeia. Perda irreversivel de informacao, sempre erro.
MARCA_PERDA = "�"


def suspeita_mojibake(valor: str) -> bool:
    """True se o texto tiver assinatura de UTF-8 lido como byte unico."""
    v = valor or ""
    if MARCA_PERDA in v:
        return True
    return any(v[i] in _PREFIXOS and v[i + 1] in SUFIXOS_MOJIBAKE
               for i in range(len(v) - 1))


def decodificar(blob: bytes) -> tuple[str, str]:
    """Decodifica o arquivo da ANP devolvendo (texto, encoding_usado).

    Tenta cada candidato em modo estrito e devolve o primeiro que decodifica o
    arquivo INTEIRO sem erro. Modo estrito e essencial: e o que diferencia
    "este arquivo e UTF-8" de "este arquivo tem bytes que UTF-8 nao aceita".
    """
    if not blob:
        raise RuntimeError("arquivo da ANP veio vazio")
    erros = []
    for enc in CANDIDATOS:
        try:
            return blob.decode(enc), enc
        except UnicodeDecodeError as exc:
            erros.append(f"{enc}: {exc}")
    # Inalcancavel: latin-1 decodifica qualquer sequencia de bytes. Fica como
    # guarda para o caso de alguem mexer em CANDIDATOS e remover a rede.
    raise RuntimeError("nao consegui decodificar o arquivo da ANP: " + " | ".join(erros))


def conferir_sem_mojibake(valores, enc: str, onde: str = "arquivo") -> None:
    """Levanta se algum rotulo tiver marca de decodificacao errada.

    `valores` pode ser qualquer iteravel de strings (cabecalho, nomes de agente,
    produtos, UFs). Mostra no maximo cinco exemplos: a mensagem de erro vai para
    o log do Actions e para o e-mail de falha, e um dump de centenas de nomes
    corrompidos nao ajuda ninguem.
    """
    ruins = sorted({v for v in valores if suspeita_mojibake(v)})
    if not ruins:
        return
    exemplos = ", ".join(repr(v) for v in ruins[:5])
    raise RuntimeError(
        f"mojibake em {len(ruins)} valor(es) de {onde} apos decodificar como "
        f"{enc} — o encoding do arquivo da ANP provavelmente mudou de novo. "
        f"data.js NAO foi alterado. Exemplos: {exemplos}"
    )
