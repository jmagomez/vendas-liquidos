"""Artefatos que o painel carrega: formato binario e cubos marginais.

Medido no artefato de 2026-11-01 (237 meses, 725.581 combinacoes):

    data.js      13,9 MB (3,5 MB gzip), <script> SINCRONO
    cubo.bin.gz   2,1 MB,               fetch assincrono, decodificacao ~0

Estes testes travam o que nao pode mudar sem quebrar o painel: o round-trip tem
de ser EXATO (o artefato e numero publicado, nao aproximacao), o cabecalho tem
de ser reconhecivel, e a codificacao tem de ser deterministica -- senao cada
rodada gera bytes diferentes do mesmo dado e vira um commit por mes sem
conteudo novo.
"""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import cubos  # noqa: E402

CAMPOS = ["mes", "comp", "uf", "mkt", "prod", "qtd"]


def dados(n_meses=3, n_comps=2, qtd=10000):
    rows = []
    for m in range(n_meses):
        for c in range(n_comps):
            rows += [m, c, 0, 0, 0, qtd + m * 100 + c]
    return {
        "months": [f"2026-{m + 1:02d}" for m in range(n_meses)],
        "comps": [f"AGENTE {c}" for c in range(n_comps)],
        "ufs": ["SP"], "mkts": ["TRR"], "prods": ["Diesel B"],
        "campos": CAMPOS, "rows": rows,
        "parciais": [], "ultimo_completo": f"2026-{n_meses:02d}",
        "herdados": [], "fonte": {"sha256": "abc123"}, "updated": "2026-11-01",
    }


# --- formato binario --------------------------------------------------------

def test_round_trip_exato():
    d = dados()
    assert cubos.decodificar(cubos.codificar(d), CAMPOS) == d["rows"]


def test_round_trip_com_quantidade_negativa():
    """A ANP publica estornos. Se a coluna de quantidade virasse sem sinal, eles
    voltariam como numeros gigantes e o volume do mes ficaria errado."""
    d = dados()
    d["rows"][5] = -4321
    assert cubos.decodificar(cubos.codificar(d), CAMPOS)[5] == -4321


def test_largura_cresce_com_o_alcance():
    """Indice ate 255 cabe em 1 byte; acima disso, 2. E o que faz o arquivo
    ser 7,3 MB em vez de 17,4 MB antes do gzip."""
    pequeno = dados(n_comps=2)
    grande = dados(n_comps=300)
    assert len(gzip.decompress(cubos.codificar(grande))) > \
           len(gzip.decompress(cubos.codificar(pequeno)))
    # a coluna 'comp' do grande precisa de 2 bytes
    bruto = gzip.decompress(cubos.codificar(grande))
    tipos = list(bruto[9:9 + len(CAMPOS)])
    assert tipos[CAMPOS.index("comp")] == cubos.U16
    assert tipos[CAMPOS.index("mes")] == cubos.U8
    assert tipos[CAMPOS.index("qtd")] == cubos.I32


def test_magico_errado_derruba():
    ruim = gzip.compress(b"XXXX" + b"\0" * 32)
    with pytest.raises(RuntimeError, match="magico"):
        cubos.decodificar(ruim, CAMPOS)


def test_numero_de_colunas_tem_de_bater():
    blob = cubos.codificar(dados())
    with pytest.raises(RuntimeError, match="colunas"):
        cubos.decodificar(blob, CAMPOS[:-1])


def test_codificacao_deterministica():
    """Bytes iguais para dado igual: sem isso, cada rodada commitaria 2 MB
    novos mesmo sem dado novo (o gzip carimba a hora se deixarem)."""
    d = dados()
    assert cubos.codificar(d) == cubos.codificar(d)


def test_sem_campos_derruba():
    with pytest.raises(RuntimeError, match="campos"):
        cubos.codificar({"rows": [1, 2, 3], "campos": []})


def test_rows_incompleto_derruba():
    with pytest.raises(RuntimeError, match="multiplo"):
        cubos.codificar({"rows": [1, 2, 3], "campos": CAMPOS})


# --- cubos marginais --------------------------------------------------------

def test_marginal_soma_por_mes_e_dimensao():
    d = dados(n_meses=2, n_comps=2)
    m = cubos.marginais(d)["cubo-mes-agente.json"]
    assert m["dim"] == "comp"
    # 2 meses x 2 agentes = 4 celulas, e a soma bate com o total
    assert len(m["k"]) == 4
    assert sum(m["v"]) == sum(d["rows"][5::6])


def test_marginal_colapsa_as_outras_dimensoes():
    """O cubo mes x produto nao pode depender de quantos agentes existem."""
    d = dados(n_meses=2, n_comps=5)
    m = cubos.marginais(d)["cubo-mes-produto.json"]
    assert len(m["k"]) == 2          # 2 meses x 1 produto
    assert sum(m["v"]) == sum(d["rows"][5::6])


# --- escrita em disco -------------------------------------------------------

def test_escrever_e_ler_de_volta(tmp_path):
    d = dados(n_meses=4, n_comps=3)
    tamanhos = cubos.escrever(tmp_path, d)
    assert cubos.NOME_META in tamanhos and cubos.NOME_CUBO in tamanhos
    volta = cubos.ler(tmp_path)
    assert volta["rows"] == d["rows"]
    assert volta["months"] == d["months"]
    assert volta["fonte"] == d["fonte"]
    assert volta["ultimo_completo"] == d["ultimo_completo"]


def test_meta_nao_leva_as_linhas(tmp_path):
    """meta.json e baixado primeiro e tem de ser pequeno: se as linhas
    vazassem para dentro dele, o ganho inteiro iria embora."""
    cubos.escrever(tmp_path, dados(n_meses=5, n_comps=5))
    m = json.loads((tmp_path / cubos.DIR_DADOS / cubos.NOME_META)
                   .read_text(encoding="utf-8"))
    assert "rows" not in m
    assert m["n_linhas"] == 25


def test_nao_deixa_tmp_para_tras(tmp_path):
    """Escrita atomica: um job interrompido nao pode deixar artefato pela
    metade sendo servido como se fosse bom."""
    cubos.escrever(tmp_path, dados())
    assert not list((tmp_path / cubos.DIR_DADOS).glob("*.tmp"))


def test_ler_sem_arquivos_devolve_none(tmp_path):
    assert cubos.ler(tmp_path) is None


# --- o carregador que substituiu o data.js ----------------------------------

def test_carregador_e_pequeno_e_nao_tem_dados(tmp_path):
    """O ponto da mudanca: data.js deixou de ser 13,9 MB de JSON."""
    alvo = tmp_path / "data.js"
    tam = cubos.escrever_carregador(alvo)
    assert tam < 8 * 1024, "o carregador nao pode voltar a engordar"
    texto = alvo.read_text(encoding="utf-8")
    assert "data/cubo.bin.gz" in texto and "data/meta.json" in texto
    # 3 KB de codigo, nao 13,9 MB de dado: o tamanho E o contrato aqui.
    assert len(texto.encode("utf-8")) == tam


def test_carregador_encadeia_na_promessa_que_a_pagina_espera():
    """O index.html nao foi tocado: ele espera por __chartPronto, entao o
    carregador tem de encadear nessa mesma promessa, e nao criar outra."""
    js = cubos.CARREGADOR_JS
    assert "window.__chartPronto = Promise.all([antes" in js
    assert "window.__semDados = 1" in js          # caminho de falha preservado


def test_carregador_entrega_array_comum():
    """A guarda do painel usa Array.isArray, que recusa typed array."""
    assert "new Array(n * P)" in cubos.CARREGADOR_JS


def test_escrever_pelo_data_js_grava_tudo(tmp_path):
    """Contrato de ponta: data_js.escrever -> data/ + carregador, e
    data_js.carregar devolve o mesmo cubo de volta."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import data_js
    d = dados(n_meses=3, n_comps=2)
    alvo = tmp_path / "data.js"
    data_js.escrever(alvo, d)
    assert alvo.exists() and (tmp_path / "data" / "meta.json").exists()
    volta = data_js.carregar(alvo)
    assert volta["rows"] == d["rows"]
    assert volta["months"] == d["months"]


def test_carregar_sem_artefato_nenhum_devolve_none(tmp_path):
    import data_js
    cubos.escrever_carregador(tmp_path / "data.js")   # carregador, mas sem data/
    assert data_js.carregar(tmp_path / "data.js") is None
