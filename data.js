// data.js — este arquivo NAO contem mais os dados: ele os carrega.
//
// Ate 2026-11 aqui moravam 13,9 MB de JSON (`window.VENDAS = {...}`) servidos
// num <script> SINCRONO: o navegador parava de construir a pagina, baixava
// 3,5 MB comprimidos, descomprimia e rodava JSON.parse antes de pintar um
// pixel. Com a serie indo de 116 para 237 meses, o arquivo dobrou.
//
// Agora os dados estao em data/meta.json (dimensoes) e data/cubo.bin.gz (as
// linhas, colunar e comprimido, ~2,1 MB), buscados em segundo plano. O formato
// esta documentado em scripts/cubos.py. GERADO — nao edite a mao.
(function(){
  var antes = window.__chartPronto || Promise.resolve();

  async function inflar(buffer){
    // Gzip no arquivo, nao no transporte: o GitHub Pages nao comprime
    // application/octet-stream, entao confiar no servidor traria 7,3 MB crus.
    if (typeof DecompressionStream === 'undefined') throw new Error('navegador sem DecompressionStream');
    var fluxo = new Blob([buffer]).stream().pipeThrough(new DecompressionStream('gzip'));
    return await new Response(fluxo).arrayBuffer();
  }

  function decodificar(cru, nCampos){
    var cab = new DataView(cru);
    var magico = String.fromCharCode(cab.getUint8(0), cab.getUint8(1),
                                     cab.getUint8(2), cab.getUint8(3));
    if (magico !== 'VLQ1') throw new Error('cubo com magico inesperado: ' + magico);
    var n = cab.getUint32(4, true), P = cab.getUint8(8);
    if (P !== nCampos) throw new Error('cubo tem ' + P + ' colunas, meta diz ' + nCampos);
    var tipos = new Uint8Array(cru, 9, P), pos = 9 + P;
    // Array comum, e nao typed array: a guarda do painel usa Array.isArray, e
    // o arquivo antigo tambem entregava Array. Mesma memoria de antes.
    var rows = new Array(n * P);
    for (var c = 0; c < P; c++){
      var t = tipos[c], larg = (t === 1 ? 1 : t === 2 ? 2 : 4);
      // .slice() em vez de view: Uint16Array/Int32Array exigem deslocamento
      // multiplo de 2/4 bytes, e as colunas nao caem alinhadas.
      var fatia = cru.slice(pos, pos + n * larg);
      var col = t === 1 ? new Uint8Array(fatia)
              : t === 2 ? new Uint16Array(fatia)
              : t === 4 ? new Uint32Array(fatia)
                        : new Int32Array(fatia);
      for (var i = 0; i < n; i++) rows[i * P + c] = col[i];
      pos += n * larg;
    }
    return rows;
  }

  async function carregar(){
    var pedir = function(url, como){
      return fetch(url).then(function(r){
        if (!r.ok) throw new Error(url + ': HTTP ' + r.status);
        return r[como]();
      });
    };
    var partes = await Promise.all([pedir('data/meta.json', 'json'),
                                    pedir('data/cubo.bin.gz', 'arrayBuffer')]);
    var meta = partes[0];
    meta.rows = decodificar(await inflar(partes[1]), meta.campos.length);
    window.VENDAS = meta;
  }

  // Encadeia na promessa que o index.html ja espera, para nao precisar mexer
  // nele. Se falhar, marca __semDados e o painel mostra o aviso de sempre.
  window.__chartPronto = Promise.all([antes, carregar().catch(function(e){
    if (window.console) console.error('[dados]', e);
    window.__semDados = 1;
  })]);
})();
