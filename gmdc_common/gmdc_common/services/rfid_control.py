"""Zebra FX cloud control - login, mode, start/stop inventory via HTTPS."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("gmdc_common.services.rfid_control")


def align_transmit_power(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Give set_mode one transmitPower array for each enabled antenna.

    Zebra rejects a flat list such as ``[30]`` when one antenna is enabled:
    the outer array must contain exactly that many inner arrays.
    """
    body = dict(payload)
    antennas = body.get("antennas")
    power = body.get("transmitPower")
    if not isinstance(antennas, list) or not antennas:
        return body
    if not isinstance(power, list) or not power:
        return body
    nested = all(isinstance(item, (list, tuple)) for item in power)
    if nested and len(power) == len(antennas):
        return body
    numbers = []
    if nested:
        for item in power:
            if item:
                numbers.append(item[0])
    elif all(
        isinstance(item, (int, float)) and not isinstance(item, bool) for item in power
    ):
        numbers = list(power)
    else:
        return body
    if not numbers:
        return body
    if len(numbers) == 1:
        values = numbers * len(antennas)
    elif len(numbers) == len(antennas):
        values = numbers
    else:
        return body
    body["transmitPower"] = 31, 31 # [[value] for value in values]
    return body


# Default CUSTOM mode payload. transmitPower is one inner array per antenna.
DEFAULT_MODE_PAYLOAD: Dict[str, Any] = {
    "type":"CUSTOM",
    "antennaStopCondition":{
       "type":"DURATION",
       "value":150
    },
    "antennas":[
       5,6
    ],
    "query":{
       "tagpopulation":1,
       "sel":"ALL",
       "session":"S0",
       "target":"AB"
    },
    "modeSpecificSettings":{
       "interval":{
          "unit":"seconds",
          "value":0
       }
    },
    "selects":[
       {
          "target":"S0",
          "action":"INVB_NOTHING",
          "membank":"TID",
          "pointer":6,
          "length":24,
          "mask":"800600"
       }
    ],
    "transmitPower":[
       31,31
    ],
    "radioStartConditions":{
       
    },
    "radioStopConditions":{
       
    },
    "reportFilter":{
       "duration":1,
       "type":"PER_ANTENNA"
    }
}


class RFIDCloudControl:
    """
    IDLE sequence:
      1. GET  /cloud/localRestLogin  (Basic Auth) -> bearer token from message
      2. PUT  /cloud/mode            (Bearer)
      3. PUT  /cloud/start           (Bearer)

    After RFID receive:
      4. PUT  /cloud/stop            (Bearer)
      5. (caller) OCI RFID validate
    """

    def __init__(
        self,
        base_url: str,
        username: str = "admin",
        password: str = "Csmpl@123",
        timeout: float = 10.0,
        verify_ssl: bool = False,
        mode_payload: Optional[Dict[str, Any]] = None,
    ):
        self.base_url = base_url.rstrip("/") + "/"
        self.username = username
        self.password = password
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.mode_payload = mode_payload or dict(DEFAULT_MODE_PAYLOAD)
        self._bearer_token: Optional[str] = None
        self._session = requests.Session()

    @classmethod
    def from_rfid_ip(
        cls,
        ip: str,
        username: str = "admin",
        password: str = "Csmpl@123",
        use_https: bool = True,
        mode_payload: Optional[Dict[str, Any]] = None,
    ) -> "RFIDCloudControl":
        scheme = "https" if use_https else "http"
        return cls(
            base_url=f"{scheme}://{ip}",
            username=username,
            password=password,
            mode_payload=mode_payload,
        )

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def _auth_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers

    def login(self) -> bool:
        """
        GET /cloud/localRestLogin with Basic Auth.
        Bearer token is taken from response JSON 'message' field.
        """
        url = self._url("cloud/localRestLogin")
        logger.info("RFID cloud login GET %s (user=%s)", url, self.username)
        try:
            resp = self._session.get(
                url,
                auth=(self.username, self.password),
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
            logger.info(
                "RFID cloud login http=%s body=%s",
                resp.status_code,
                (resp.text or "")[:300],
            )
            if resp.status_code not in (200, 201):
                self._bearer_token = None
                return False
            try:
                data = resp.json()
            except Exception:
                data = {}
            token = ""
            if isinstance(data, dict):
                token = str(
                    data.get("message")
                    or data.get("token")
                    or data.get("access_token")
                    or ""
                ).strip()
            if token.lower().startswith("bearer "):
                token = token[7:].strip()
            if not token:
                logger.error("RFID login OK but no bearer token in message")
                self._bearer_token = None
                return False
            self._bearer_token = token
            logger.info("RFID bearer token acquired (len=%s)", len(token))
            return True
        except requests.RequestException as e:
            logger.error("RFID cloud login error: %s", e)
            self._bearer_token = None
            return False

    def set_mode(self, payload: Optional[Dict[str, Any]] = None) -> bool:
        """PUT /cloud/mode with Bearer token and CUSTOM mode payload."""
        if not self._bearer_token and not self.login():
            return False
        url = self._url("cloud/mode")
        body = align_transmit_power(payload or self.mode_payload)
        logger.info(
            "RFID cloud set mode PUT %s antennas=%s transmitPower=%s",
            url,
            body.get("antennas"),
            body.get("transmitPower"),
        )
        try:
            print(body)
            resp = self._session.put(
                url,
                json=body,
                headers=self._auth_headers(),
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
            if resp.status_code in (401, 403):
                logger.warning("RFID mode unauthorized - re-login and retry")
                if self.login():
                    resp = self._session.put(
                        url,
                        json=body,
                        headers=self._auth_headers(),
                        timeout=self.timeout,
                        verify=self.verify_ssl,
                    )
            logger.info(
                "RFID cloud mode http=%s body=%s",
                resp.status_code,
                (resp.text or "")[:300],
            )
            if resp.status_code in (200, 201, 204):
                return True
            if resp.status_code in (404, 405):
                resp = self._session.post(
                    url,
                    json=body,
                    headers=self._auth_headers(),
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )
                logger.info(
                    "RFID cloud mode POST fallback http=%s body=%s",
                    resp.status_code,
                    (resp.text or "")[:300],
                )
                return resp.status_code in (200, 201, 204)
            return False
        except requests.RequestException as e:
            logger.error("RFID cloud mode error: %s", e)
            return False

    def _put_start_stop(self, path: str, label: str) -> bool:
        """PUT start/stop with Bearer token (same as mode)."""
        if not self._bearer_token and not self.login():
            logger.error("RFID cloud %s aborted - no bearer token", label)
            return False
        url = self._url(path)
        logger.info("RFID cloud %s PUT %s (Bearer)", label, url)
        try:
            resp = self._session.put(
                url,
                headers=self._auth_headers(),
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
            if resp.status_code in (401, 403):
                logger.warning("RFID %s unauthorized - re-login and retry", label)
                if self.login():
                    resp = self._session.put(
                        url,
                        headers=self._auth_headers(),
                        timeout=self.timeout,
                        verify=self.verify_ssl,
                    )
            logger.info(
                "RFID cloud %s http=%s body=%s",
                label,
                resp.status_code,
                (resp.text or "")[:200],
            )
            if resp.status_code in (200, 201, 204):
                return True
            if resp.status_code in (404, 405):
                resp = self._session.post(
                    url,
                    headers=self._auth_headers(),
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )
                logger.info(
                    "RFID cloud %s POST fallback http=%s",
                    label,
                    resp.status_code,
                )
                return resp.status_code in (200, 201, 204)
            return False
        except requests.RequestException as e:
            logger.error("RFID cloud %s error: %s", label, e)
            return False

    def stop(self) -> bool:
        """PUT /cloud/stop after RFID tags received (Bearer)."""
        return self._put_start_stop("cloud/stop", "stop")

    def start(self) -> bool:
        """PUT /cloud/start after mode is set (Bearer)."""
        return self._put_start_stop("cloud/start", "start")

    def prepare_idle(self) -> bool:
        """
        Full IDLE prepare sequence:
          login -> set mode -> start
        """
        logger.info("RFID IDLE prepare: login -> mode -> start")
        if not self.login():
            logger.error("RFID IDLE prepare failed at login")
            return False
        if not self.set_mode():
            logger.error("RFID IDLE prepare failed at set_mode")
            return False
        if not self.start():
            logger.error("RFID IDLE prepare failed at start")
            return False
        logger.info("RFID IDLE prepare complete - reader scanning")
        return True


def build_rfid_cloud_control(
    rfid_cfg: dict, enabled: bool = True
) -> Optional[RFIDCloudControl]:
    if not enabled:
        return None
    ip = (rfid_cfg or {}).get("ip") or ""
    if not ip:
        logger.warning("No RFID IP configured - cloud control disabled")
        return None

    username = (
        os.getenv("RFID_USERNAME")
        or (rfid_cfg or {}).get("username")
        or "admin"
    )
    password = (
        os.getenv("RFID_PASSWORD")
        or (rfid_cfg or {}).get("password")
        or "change"
    )
    mode_payload = (rfid_cfg or {}).get("mode_payload") or None

    return RFIDCloudControl.from_rfid_ip(
        ip=ip,
        username=username,
        password=password,
        use_https=True,
        mode_payload=mode_payload,
    )
