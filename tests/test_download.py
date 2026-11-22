"""Politica de retry do download da ANP (regressao dos runs #24 e #25).

Em 2026-11-22 duas execucoes seguidas morreram em 2m44s cada, as oito
requisicoes com `ConnectionResetError(104)` no zip E na URL direta: a origem
estava derrubando a conexao. A politica de entao -- 4 tentativas, backoff
10/20/40 -- gastava 70 segundos de espera e desistia. Para uma origem que cai
por minutos ou horas, 70 segundos nao e paciencia.

Estes testes travam a politica nova sem gastar relogio: `baixar` recebe
`dormir`, `agora` e `aleatorio` injetados, entao da para provar que o
orcamento e respeitado em microssegundos.
"""
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import update_dashboard as ud  # noqa: E402

ZIP_MINIMO = b"PK\x03\x04resto"


class Relogio:
    """Relogio falso: so anda quando alguem dorme."""

    def __init__(self):
        self.t = 0.0

    def agora(self):
        return self.t

    def dormir(self, s):
        self.t += s


@pytest.fixture
def relogio():
    return Relogio()


def reset(*_a, **_k):
    raise requests.ConnectionError("('Connection aborted.', "
                                   "ConnectionResetError(104, 'Connection reset by peer'))")


# --- backoff ----------------------------------------------------------------

def test_primeira_tentativa_nao_espera():
    assert ud.espera_da_tentativa(1) == 0.0


def test_backoff_dobra_ate_o_teto():
    """Sem teto, a 8a espera seria de 32 minutos sozinha."""
    semjitter = [ud.espera_da_tentativa(i, aleatorio=lambda: 0.5)
                 for i in range(2, 10)]
    assert semjitter[0] == pytest.approx(ud.ESPERA_BASE)
    assert semjitter[1] == pytest.approx(ud.ESPERA_BASE * 2)
    assert all(b <= ud.ESPERA_MAX + 1e-9 for b in semjitter)
    assert semjitter[-1] == pytest.approx(ud.ESPERA_MAX)
    assert semjitter == sorted(semjitter)        # nunca diminui


def test_jitter_fica_na_faixa_declarada():
    """Dois crons mais um dispatch nao podem bater no mesmo segundo."""
    base = ud.ESPERA_BASE * 2
    for extremo in (0.0, 1.0):
        v = ud.espera_da_tentativa(3, aleatorio=(lambda e: lambda: e)(extremo))
        assert abs(v - base) == pytest.approx(base * ud.JITTER)
    assert ud.espera_da_tentativa(3, aleatorio=lambda: 0.0) > 0


# --- classificacao do modo de falha -----------------------------------------
# "indisponivel apos N tentativas" nao distingue origem fora do ar de URL que
# mudou, e a reacao e oposta: esperar contra ir olhar o site.

def test_reset_de_conexao_tem_nome_proprio():
    try:
        reset()
    except Exception as e:
        assert ud.classificar_falha(e) == "conexao derrubada pela origem"


def test_http_leva_o_codigo():
    r = requests.Response()
    r.status_code = 404
    assert ud.classificar_falha(requests.HTTPError(response=r)) == "http 404"


def test_timeouts_sao_distintos():
    assert ud.classificar_falha(requests.ConnectTimeout()) == "timeout de conexao"
    assert ud.classificar_falha(requests.ReadTimeout()) == "timeout de leitura"


def test_erro_desconhecido_nao_vira_rotulo_errado():
    assert ud.classificar_falha(ValueError("x")) == "ValueError"


# --- orcamento --------------------------------------------------------------

def test_desiste_dentro_do_orcamento(relogio, monkeypatch):
    """O job tem timeout de 45 min: estourar o relogio do runner mata a rotina
    sem e-mail de falha e sem log legivel, que e pior do que falhar."""
    monkeypatch.setattr(ud, "_get", reset)
    with pytest.raises(RuntimeError, match="ANP indisponível"):
        ud.baixar(dormir=relogio.dormir, agora=relogio.agora,
                  aleatorio=lambda: 0.5)
    assert relogio.t <= ud.ORCAMENTO


def test_orcamento_curto_corta_as_tentativas(relogio, monkeypatch):
    monkeypatch.setattr(ud, "_get", reset)
    monkeypatch.setattr(ud, "ORCAMENTO", 20)
    with pytest.raises(RuntimeError, match="orcamento"):
        ud.baixar(dormir=relogio.dormir, agora=relogio.agora,
                  aleatorio=lambda: 0.5)
    assert relogio.t <= 20


def test_a_politica_nova_espera_muito_mais_que_a_antiga(relogio, monkeypatch):
    """A regressao concreta: a politica antiga gastava 70s antes de desistir."""
    monkeypatch.setattr(ud, "_get", reset)
    with pytest.raises(RuntimeError):
        ud.baixar(dormir=relogio.dormir, agora=relogio.agora,
                  aleatorio=lambda: 0.5)
    assert relogio.t > 10 * 60


def test_mensagem_final_conta_e_classifica_as_falhas(relogio, monkeypatch):
    monkeypatch.setattr(ud, "_get", reset)
    with pytest.raises(RuntimeError) as e:
        ud.baixar(dormir=relogio.dormir, agora=relogio.agora,
                  aleatorio=lambda: 0.5)
    msg = str(e.value)
    # Duas URLs por tentativa (zip e csv direto).
    assert "conexao derrubada pela origem x" in msg
    assert "requisição(ões) falharam" in msg


# --- caminho feliz ----------------------------------------------------------

def test_sucesso_na_primeira_nao_dorme(relogio, monkeypatch):
    monkeypatch.setattr(ud, "_get", lambda url: ZIP_MINIMO)
    monkeypatch.setattr(ud, "_extrair_do_zip", lambda b: [("x.csv", b"a;b")])
    assert ud.baixar(dormir=relogio.dormir, agora=relogio.agora) == [("x.csv", b"a;b")]
    assert relogio.t == 0.0


def test_recupera_depois_de_falhar(relogio, monkeypatch):
    """Falha transitoria e o caso comum; desistir dela seria o pior desfecho."""
    chamadas = {"n": 0}

    def instavel(url):
        chamadas["n"] += 1
        if chamadas["n"] <= 3:
            reset()
        return ZIP_MINIMO

    monkeypatch.setattr(ud, "_get", instavel)
    monkeypatch.setattr(ud, "_extrair_do_zip", lambda b: [("ok.csv", b"1")])
    assert ud.baixar(dormir=relogio.dormir, agora=relogio.agora,
                     aleatorio=lambda: 0.5) == [("ok.csv", b"1")]
    assert 0 < relogio.t < ud.ORCAMENTO


def test_resposta_que_nao_e_zip_vira_o_csv_direto(relogio, monkeypatch):
    monkeypatch.setattr(ud, "_get", lambda url: b"Ano;Mes;...")
    assert ud.baixar(dormir=relogio.dormir, agora=relogio.agora) == [
        (ud.ALVO_CSV, b"Ano;Mes;...")]


def test_timeout_e_tupla_conexao_leitura():
    """Timeout unico de 300s valia tambem para CONECTAR: com a origem fora do
    ar, cada tentativa segurava 5 minutos antes de desistir."""
    assert isinstance(ud.TIMEOUT, tuple) and len(ud.TIMEOUT) == 2
    assert ud.TIMEOUT[0] <= 60 < ud.TIMEOUT[1]
