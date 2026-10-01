import requests
from requests.exceptions import RequestException, Timeout
import logging

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class ServerService:
    def __init__(self):
        self.timeout = 10  # seconds

    def check_connection(self, ip, port):
        """
        Check if server is reachable.

        Local hosts (localhost / 127.0.0.1) are accepted without a live probe
        so commissioning can continue before the site app is running.
        """
        if not ip or not port:
            return {
                "status": 400,
                "message": "Server URL and Port are required"
            }

        host = str(ip).strip().lower()
        # Allow full URLs in the field - use hostname only for local check / probe
        if "://" in host:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(str(ip).strip() if "://" in str(ip) else f"http://{ip}")
                host = (parsed.hostname or host).lower()
            except Exception:
                pass
        port_str = str(port).strip()

        if host in _LOCAL_HOSTS:
            logger.info(
                "Server check: local host %s:%s - accepting without live probe",
                ip,
                port_str,
            )
            return {
                "status": 200,
                "message": f"Server recorded as {ip}:{port_str}.",
                "local": True,
            }

        url = f"http://{host}:{port_str}/"

        try:
            response = requests.get(url, timeout=self.timeout)

            if response.status_code == 200:
                return {
                    "status": 200,
                    "message": "Server is reachable and responding"
                }
            return {
                "status": response.status_code,
                "message": f"Server responded with status code: {response.status_code}"
            }

        except Timeout:
            return {
                "status": 408,
                "message": "Connection timed out. Server not responding."
            }

        except RequestException:
            logger.exception("Server connectivity check failed for %s:%s", ip, port)
            return {
                "status": 500,
                "message": (
                    f"Unable to connect to http://{ip}:{port_str}/. "
                    "Verify the host is online and the site API port is correct."
                )
            }
