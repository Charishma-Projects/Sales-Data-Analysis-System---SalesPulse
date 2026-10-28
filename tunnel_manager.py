"""
tunnel_manager.py - Public Tunneling and Public Key Authentication System
Generates and manages Public API Keys, and provisions live public URLs
via localtunnel so the application can be accessed publicly over the Internet.
"""

import os
import secrets
import subprocess
import threading
import time
import re
import requests
from typing import Optional, Dict, Any
from database import DatabaseManager

DEFAULT_KEY_PREFIX = "pk_live_sales_"


class TunnelAndKeyManager:
    def __init__(self, db_manager: DatabaseManager, port: int = 5000):
        self.db = db_manager
        self.port = port
        self.public_url: Optional[str] = None
        self.tunnel_process: Optional[subprocess.Popen] = None
        self.tunnel_error: Optional[str] = None
        self.public_ip: str = "Unknown"
        self._ensure_public_key()
        self._fetch_public_ip()

    def _ensure_public_key(self) -> str:
        """Ensures a persistent Public Key exists in the database."""
        existing_key = self.db.get_setting("PUBLIC_API_KEY")
        if not existing_key:
            new_key = f"{DEFAULT_KEY_PREFIX}{secrets.token_hex(16)}"
            self.db.set_setting("PUBLIC_API_KEY", new_key)
            return new_key
        return existing_key

    def get_public_key(self) -> str:
        """Returns the active Public Key."""
        key = self.db.get_setting("PUBLIC_API_KEY")
        if not key:
            return self._ensure_public_key()
        return key

    def regenerate_public_key(self) -> str:
        """Generates a new Public Key and saves to DB."""
        new_key = f"{DEFAULT_KEY_PREFIX}{secrets.token_hex(16)}"
        self.db.set_setting("PUBLIC_API_KEY", new_key)
        return new_key

    def validate_api_key(self, key_to_check: Optional[str]) -> bool:
        """Validates an incoming API Key against the stored Public Key."""
        if not key_to_check:
            return False
        stored_key = self.get_public_key()
        return secrets.compare_digest(stored_key, key_to_check.strip())

    def _fetch_public_ip(self):
        """Fetches public IP address used as password for localtunnel."""
        def worker():
            for service in ["https://api.ipify.org", "https://loca.lt/mytunnelpassword", "https://ifconfig.me/ip"]:
                try:
                    resp = requests.get(service, timeout=4)
                    if resp.status_code == 200 and resp.text.strip():
                        self.public_ip = resp.text.strip()
                        return
                except Exception:
                    continue
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def start_tunnel(self) -> Optional[str]:
        """
        Starts localtunnel in a background thread and captures the assigned public URL.
        """
        if self.public_url and self.tunnel_process and self.tunnel_process.poll() is None:
            return self.public_url

        def run_tunnel():
            try:
                # Run npx localtunnel
                cmd = f"npx --yes localtunnel --port {self.port}"
                self.tunnel_process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )

                for line in self.tunnel_process.stdout:
                    line = line.strip()
                    match = re.search(r"https://[a-zA-Z0-9-]+\.loca\.lt", line)
                    if match:
                        self.public_url = match.group(0)
                        self.db.set_setting("PUBLIC_TUNNEL_URL", self.public_url)
                        print(f"\n=======================================================")
                        print(f"[PUBLIC URL] Live URL: {self.public_url}")
                        print(f"[AUTH KEY]   Public API Key: {self.get_public_key()}")
                        print(f"[PASSWORD]   Localtunnel Password (IP): {self.public_ip}")
                        print(f"=======================================================\n")
                        break
            except Exception as e:
                self.tunnel_error = str(e)
                print(f"[TunnelManager] Error starting tunnel: {e}")

        thread = threading.Thread(target=run_tunnel, daemon=True)
        thread.start()
        
        # Wait up to 6 seconds for URL
        for _ in range(12):
            if self.public_url:
                break
            time.sleep(0.5)

        return self.public_url

    def get_status(self) -> Dict[str, Any]:
        """Returns tunnel and authentication status."""
        is_active = (self.public_url is not None) and (self.tunnel_process is None or self.tunnel_process.poll() is None)
        return {
            "is_active": is_active,
            "public_url": self.public_url or f"http://127.0.0.1:{self.port}",
            "public_key": self.get_public_key(),
            "public_ip": self.public_ip,
            "tunnel_service": "Localtunnel (Global HTTPS CDN)",
            "port": self.port,
            "error": self.tunnel_error
        }
