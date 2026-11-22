"""Adaptadores de previsão do tempo."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from math import isfinite
from time import monotonic

import httpx

from ..datas import somar_dias
from ..dominio import PrevisaoClima, PrevisaoDia

CHUVAS_DEMO = [0, 2, 48, 12, 0, 0, 5]
MINIMAS_DEMO = [22, 22, 21, 21, 22, 23, 23]
MAXIMAS_DEMO = [31, 30, 26, 27, 30, 32, 31]
LOGGER = logging.getLogger(__name__)


class ClimaSimulado:
    """Mesma semana de src/lib/demo.ts: chuva forte no 3º dia."""

    def __init__(self, chuvas: list[float] | None = None) -> None:
        self.chuvas = chuvas or CHUVAS_DEMO

    def previsao(self, fazenda_id: str, lat: float, lon: float, hoje: str) -> PrevisaoClima:
        return PrevisaoClima(fazenda_id, [
            PrevisaoDia(somar_dias(hoje, i), float(c), float(MINIMAS_DEMO[i]), float(MAXIMAS_DEMO[i]))
            for i, c in enumerate(self.chuvas[:7])
        ], consultado_em=datetime.now(timezone.utc).isoformat())


class ClimaOpenMeteo:
    def __init__(self, cliente_http: httpx.Client | None = None) -> None:
        self.cliente_http = cliente_http or httpx.Client(timeout=10)
        self._cache: dict[tuple[str, float, float], tuple[float, PrevisaoClima]] = {}
        self._simulado = ClimaSimulado()

    def previsao(self, fazenda_id: str, lat: float, lon: float, hoje: str) -> PrevisaoClima:
        chave = (fazenda_id, lat, lon)
        anterior = self._cache.get(chave)
        if anterior and monotonic() - anterior[0] < 3 * 3600:
            return anterior[1]
        try:
            resposta = self.cliente_http.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": lat, "longitude": lon,
                "daily": "precipitation_sum,temperature_2m_min,temperature_2m_max",
                "timezone": "America/Maceio", "forecast_days": 7,
            })
            resposta.raise_for_status()
            dados = resposta.json()["daily"]
            dias = [
                PrevisaoDia(data, float(chuva), float(minima), float(maxima))
                for data, chuva, minima, maxima in zip(
                    dados["time"], dados["precipitation_sum"], dados["temperature_2m_min"],
                    dados["temperature_2m_max"], strict=True,
                )
            ]
            if len(dias) != 7 or any(
                not all(map(isfinite, (dia.chuva_mm, dia.temp_min_c, dia.temp_max_c))) for dia in dias
            ):
                raise ValueError("Previsão incompleta")
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            LOGGER.warning("Open-Meteo indisponível; usando %s", "cache" if anterior else "simulação")
            return anterior[1] if anterior else self._simulado.previsao(fazenda_id, lat, lon, hoje)
        previsao = PrevisaoClima(fazenda_id, dias, "open-meteo", datetime.now(timezone.utc).isoformat())
        self._cache[chave] = monotonic(), previsao
        return previsao
