"""Testes do encoding do CSV da ANP (regressao dos runs #17 e #18).

O run #17 (2026-10-28) caiu com `col 1: esperado ~'mes', achado 'MÃªs'`: a ANP
passou a gravar o Liquidos_Vendas_Atual.csv em UTF-8 e o pipeline decodificava
com latin-1 fixo. O run #18 caiu na trava criada para o #17, por falso positivo
em nome real de agente. Estes testes travam tres coisas:

1. o arquivo e lido corretamente em UTF-8 (com e sem BOM), cp1252 e latin-1,
   produzindo o MESMO agregado;
2. rotulo com marca de mojibake derruba a rotina — inclusive quando o cabecalho
   esta limpo e so os nomes de agente corromperam, que e o cenario em que todas
   as travas antigas passavam e o data.js saia errado em silencio;
3. nome legitimo da ANP NAO derruba a rotina — inclusive os que tem 'CÇÃO' e
   'ATLÂN', que e o que quebrou o run #18.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import leitura  # noqa: E402
import update_dashboard as ud  # noqa: E402

# Cabecalho real da ANP, com os acentos que o arquivo de verdade tem.
CAB_ANP = [
    "Ano", "Mês", "Agente Regulado", "Codigo do Produto", "Nome do Produto",
    "Descricao do Produto", "Regiao Origem", "UF Origem", "Regiao Destinatario",
    "UF Destino", "Mercado Destinatario", "Quantidade de Produto (mil m³)",
]
CAB = ";".join(CAB_ANP)

AGENTE = "RAÍZEN COMBUSTÍVEIS S.A."
CHAVE = ("2026-09", AGENTE, "SP", "TRR", "Óleo Comb.")


def linha(ano=2026, mes=9, comp=AGENTE, uf="SP", mkt="TRR",
          prod="Óleo Comb.", qtd="1234,50"):
    # Sem separador de milhar de proposito: o parser so troca ',' por '.', como
    # o arquivo da ANP exige. "1.234,50" viraria "1.234.50" e seria descartado.
    campos = [""] * 12
    campos[ud.COL_ANO], campos[ud.COL_MES] = str(ano), str(mes)
    campos[ud.COL_COMP], campos[ud.COL_UF] = comp, uf
    campos[ud.COL_MKT], campos[ud.COL_QTD] = mkt, qtd
    campos[ud.COL_PROD] = prod
    return ";".join(campos)


def csv_bytes(*linhas, enc="utf-8", cabecalho=CAB):
    return ("\n".join([cabecalho, *linhas]) + "\n").encode(enc)


# --- deteccao de encoding ---------------------------------------------------

@pytest.mark.parametrize("enc,esperado", [
    ("utf-8", "utf-8-sig"),      # utf-8-sig == utf-8 quando nao ha BOM
    ("utf-8-sig", "utf-8-sig"),  # com BOM
    ("cp1252", "cp1252"),
])
def test_decodificar_identifica_encoding(enc, esperado):
    blob = csv_bytes(linha(), enc=enc)
    texto, achado = leitura.decodificar(blob)
    assert achado == esperado
    assert "Mês" in texto
    assert AGENTE in texto


def test_decodificar_vazio_derruba():
    with pytest.raises(RuntimeError, match="vazio"):
        leitura.decodificar(b"")


# --- agregacao e o caso exato do run #17 ------------------------------------

def test_utf8_e_o_caso_do_run_17():
    """Arquivo UTF-8: antes do hotfix caia em 'MÃªs'. Agora tem de agregar."""
    agg = ud.agregar(csv_bytes(linha(qtd="10,5"), linha(qtd="4,5"), enc="utf-8"))
    assert agg[CHAVE] == pytest.approx(15.0)


def test_agregados_iguais_entre_encodings():
    """Trocar o encoding da origem nao pode mudar um unico numero nem um rotulo."""
    linhas = (linha(qtd="10,5"), linha(prod="Gasolina C", qtd="4,5"))
    a = ud.agregar(csv_bytes(*linhas, enc="utf-8"))
    b = ud.agregar(csv_bytes(*linhas, enc="cp1252"))
    assert a == b


def test_latin1_continua_funcionando():
    """O hotfix nao pode quebrar o formato historico da ANP."""
    agg = ud.agregar(csv_bytes(linha(qtd="7,0"), enc="latin-1"))
    assert agg[CHAVE] == pytest.approx(7.0)


def test_encoding_vai_para_a_proveniencia():
    stats: dict = {}
    ud.agregar(csv_bytes(linha(qtd="1,0"), enc="utf-8"), stats)
    assert stats["encoding"] == "utf-8-sig"


# --- travas de mojibake -----------------------------------------------------

# Os dois testes abaixo usam DUPLA codificacao: o texto mojibake ('MÃªs') e
# gravado em UTF-8. E o unico jeito de a corrupcao sobreviver a decodificacao --
# e e exatamente o que acontece quando a origem conserta o encoding do arquivo
# mas nao o conteudo que ja estava corrompido. Mojibake gravado em latin-1, por
# outro lado, PRODUZ bytes UTF-8 validos e e recuperado corretamente pelo
# decodificador; esse caso esta coberto por test_utf8_e_o_caso_do_run_17.
def test_mojibake_no_cabecalho_derruba():
    cab_ruim = CAB.replace("Mês", "Mês".encode("utf-8").decode("latin-1"))
    with pytest.raises(RuntimeError, match="mojibake"):
        ud.agregar(csv_bytes(linha(), enc="utf-8", cabecalho=cab_ruim))


def test_mojibake_so_no_nome_do_agente_derruba():
    """O cenario perigoso: cabecalho limpo, rotulo corrompido.

    Nenhuma trava de volume pega isto -- o volume e identico. Sem a conferencia
    de dimensoes, 'RAÃZEN' e 'RAÍZEN' viram dois agentes e o HHI despenca.
    """
    agente_ruim = AGENTE.encode("utf-8").decode("latin-1")
    with pytest.raises(RuntimeError, match="mojibake"):
        ud.agregar(csv_bytes(linha(comp=agente_ruim), enc="utf-8"))


def test_replacement_char_derruba():
    with pytest.raises(RuntimeError, match="mojibake"):
        leitura.conferir_sem_mojibake(["RA�ZEN"], "utf-8-sig", "teste")


def test_nome_legitimo_nao_dispara_a_trava():
    """Falso positivo aqui pararia a rotina todo mes. Acento normal tem de passar."""
    leitura.conferir_sem_mojibake(
        ["RAÍZEN", "PETRÓLEO BRASILEIRO S.A.", "Óleo Comb.", "Mês"],
        "utf-8-sig", "teste")


# --- Regressao do run #18 ---------------------------------------------------
# A primeira versao desta trava acusava qualquer "Ã"/"Â" e derrubou o run #18
# (2026-10-31) com estes quatro nomes REAIS da ANP. "Ã" e "Â" sao letras
# legitimas do portugues em caixa alta, que e como a ANP grava agente.
NOMES_REAIS_DO_RUN_18 = [
    "AGILE LOGISTICA E DISTRIBUIÇÃO DE COMBUSTÍVEIS LTDA",
    "ATLÂNTICA PRODUTOS DE PETRÓLEO LTDA.",
    "DISTRIBUIDORA DE COMBUSTÍVEL TORRÃO LTDA.",
    "DISTRIBUIDORA TABOCÃO LTDA.",
]


@pytest.mark.parametrize("nome", NOMES_REAIS_DO_RUN_18)
def test_nome_real_da_anp_com_A_tilde_passa(nome):
    assert not leitura.suspeita_mojibake(nome)
    leitura.conferir_sem_mojibake([nome], "utf-8-sig", "teste")


def test_nome_real_corrompido_ainda_e_pego():
    """O par (Ã + byte de continuacao) e a assinatura; a letra sozinha nao e."""
    for nome in NOMES_REAIS_DO_RUN_18:
        for enc_errado in ("latin-1", "cp1252"):
            corrompido = nome.encode("utf-8").decode(enc_errado, errors="replace")
            assert leitura.suspeita_mojibake(corrompido), corrompido


def test_rotulos_reais_do_data_js_nao_disparam():
    """Varredura no artefato de producao: nenhum rotulo real pode ser acusado.

    E o teste que teria evitado o run #18 -- o artefato commitado tem os ~370
    rotulos que a ANP realmente publica, incluindo os nomes com 'ÇÃO' e 'ÂN'.
    """
    from pathlib import Path

    import data_js
    d = data_js.carregar(Path(__file__).resolve().parents[1] / "data.js")
    if d is None:                                 # pragma: no cover
        pytest.skip("sem artefato de dados no repositorio")
    rotulos = [*d["comps"], *d["ufs"], *d["mkts"], *d.get("prods", []), *d["months"]]
    acusados = [r for r in rotulos if leitura.suspeita_mojibake(r)]
    assert not acusados, f"falso positivo em {len(acusados)}: {acusados[:5]}"
