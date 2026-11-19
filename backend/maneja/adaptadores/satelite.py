"""Leituras de NDVI da série local ou do Copernicus Data Space."""

from datetime import date, timedelta
from math import isfinite
from threading import Lock
from time import monotonic
from typing import Protocol

import httpx

from ..dominio import LeituraNdvi, Piquete

LIMITE_NUVEM = 0.30  # SPEC-007, risco R6
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
ESTATISTICAS_URL = "https://sh.dataspace.copernicus.eu/statistics/v1"

# A média da banda de nuvem mede a fração coberta; o NDVI usa uma máscara própria.
EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B04", "B08", "SCL", "dataMask"]}],
    output: [
      {id: "ndvi", bands: 1, sampleType: "FLOAT32"},
      {id: "nuvem", bands: 1, sampleType: "FLOAT32"},
      {id: "dataMask", bands: ["ndvi", "nuvem"]}
    ]
  };
}
function evaluatePixel(s) {
  const nuvem = [3, 8, 9, 10].includes(s.SCL);
  const valido = s.dataMask && s.SCL !== 0 && s.SCL !== 1;
  const soma = s.B08 + s.B04;
  return {
    ndvi: [soma ? (s.B08 - s.B04) / soma : 0],
    nuvem: [nuvem ? 1 : 0],
    dataMask: [valido && !nuvem && s.SCL !== 11 && soma ? 1 : 0, valido ? 1 : 0]
  };
}
"""


class ISatelite(Protocol):
    def ndvi(self, piquete: Piquete, data: str) -> LeituraNdvi | None: ...


class SateliteSimulado:
    def ndvi(self, piquete: Piquete, data: str) -> None:
        # A série já está no repositório de demonstração.
        return None


class SateliteCopernicus:
    def __init__(self, client_id: str, client_secret: str, cliente_http: httpx.Client | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.cliente_http = cliente_http or httpx.Client(timeout=15)
        self._token = ""
        self._token_ate = 0.0
        self._trava = Lock()

    def _autenticar(self) -> str:
        with self._trava:
            if monotonic() >= self._token_ate:
                resposta = self.cliente_http.post(TOKEN_URL, data={
                    "grant_type": "client_credentials", "client_id": self.client_id,
                    "client_secret": self.client_secret,
                })
                resposta.raise_for_status()
                dados = resposta.json()
                self._token = dados["access_token"]
                self._token_ate = monotonic() + max(0, float(dados.get("expires_in", 0)) - 30)
            return self._token

    def ndvi(self, piquete: Piquete, data: str) -> LeituraNdvi | None:
        fim = date.fromisoformat(data) + timedelta(days=1)
        resposta = self.cliente_http.post(
            ESTATISTICAS_URL, headers={"Authorization": f"Bearer {self._autenticar()}"}, json={
                "input": {
                    "bounds": {"geometry": piquete.geometria, "properties": {
                        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
                    }},
                    "data": [{"type": "sentinel-2-l2a"}],
                },
                "aggregation": {
                    "timeRange": {"from": f"{data}T00:00:00Z", "to": f"{fim}T00:00:00Z"},
                    "aggregationInterval": {"of": "P1D"}, "evalscript": EVALSCRIPT,
                    "resx": 0.00009, "resy": 0.00009,
                },
            },
        )
        resposta.raise_for_status()
        dados = resposta.json()
        for intervalo in dados["data"]:
            saidas = intervalo.get("outputs", {})
            ndvi = saidas.get("ndvi", {}).get("bands", {}).get("B0", {}).get("stats", {})
            nuvem = saidas.get("nuvem", {}).get("bands", {}).get("B0", {}).get("stats", {})
            valor, fracao = ndvi.get("mean"), nuvem.get("mean")
            if (isinstance(valor, (int, float)) and isinstance(fracao, (int, float))
                    and isfinite(valor) and -1 <= valor <= 1 and 0 <= fracao <= LIMITE_NUVEM):
                return LeituraNdvi(piquete.id, data, valor)
        return None
