# -*- coding: utf-8 -*-
"""
Tunnel-Diagnoseskript
Dieses Skript dient dazu, die Tunnel-Erstellungslogik von Colabpro.py isoliert zu diagnostizieren.
Es startet einen Dummy-Webserver, um einen Port zu belegen, und führt dann den TunnelManager aus,
um die Ausgabe von cloudflared und localtunnel zur Analyse zu erfassen.
"""
import sys
import os
import shutil
import subprocess
import time
import threading
import re
from pathlib import Path
import traceback
from datetime import datetime
from collections import deque
import html
import socket
import http.server
import logging

# --- Grundlegende Konfiguration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('TunnelDiagnostik')
ROOT_DIR = Path(__file__).resolve().parent
TUNNEL_LOG_FILE = ROOT_DIR / "tunnel_output.log"
PROJECT_FOLDER_NAME = "wolf_project_diagnostic" # Verwenden Sie einen sicheren Ordnernamen

# --- Bereinigen Sie alte Protokolldateien ---
if TUNNEL_LOG_FILE.exists():
    TUNNEL_LOG_FILE.unlink()

# --- Kopiert und angepasst von Colabpro.py ---

# Mock-Objekte für die Ausführung außerhalb von Colab
class MockColab:
    def eval_js(self, *args, **kwargs): return ""
IN_COLAB = False
colab_output = MockColab()

TUNNEL_ORDER = ["Cloudflare", "Localtunnel", "Colab"]

class LogManager:
    """Ein einfacher Protokollmanager, um die Abhängigkeit von der vollständigen DisplayManager-UI zu entfernen."""
    def log(self, level, message):
        log.info(f"[{level}] {message}")

class TunnelManager:
    """Angepasste Version für die Diagnose."""
    def __init__(self, port, shared_state, project_path, log_manager, timeout=40):
        self.port = port
        self._state = shared_state
        self._project_path = Path(project_path)
        self._log = log_manager.log
        self._timeout = timeout
        self.threads = []
        self.processes = []

    def _run_tunnel_service(self, name, command, pattern, cwd):
        self._log("INFO", f"-> Starte Tunnel für {name}...")
        try:
            # Stellen Sie sicher, dass das Arbeitsverzeichnis existiert
            if not cwd.exists():
                cwd.mkdir(parents=True, exist_ok=True)

            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', cwd=cwd)
            self.processes.append(proc)

            start_time = time.monotonic()

            with open(TUNNEL_LOG_FILE, "a") as f:
                f.write(f"\n===== START {name} LOG =====\n")
                f.write(f"Befehl: {' '.join(command)}\n")

                for line in iter(proc.stdout.readline, ''):
                    f.write(line) # Schreiben Sie die rohe Ausgabe in die Datei
                    line = line.strip()
                    self._log("RUNNER", f"[{name}] {line}")

                    if time.monotonic() - start_time > self._timeout:
                        self._state["urls"][name] = {"url": "Fehler: Timeout"}
                        self._log("ERROR", f"❌ {name} Timeout")
                        f.write("===== END {name} LOG (TIMEOUT) =====\n")
                        return

                    match = re.search(pattern, line)
                    if match:
                        url = match.group(1)
                        self._state["urls"][name] = {"url": url}
                        self._log("SUCCESS", f"✅ {name} Erfolg: {url}")
                        f.write(f"\n--- ERFOLGREICH EXTRAHIERTE URL: {url} ---\n")
                        # Lassen Sie den Prozess noch einige Sekunden laufen, um eventuelle nachfolgende Nachrichten zu erfassen
                        time.sleep(2)
                        return

            proc.wait(timeout=1)
            if self._state["urls"].get(name) is None:
                 self._state["urls"][name] = {"url": f"Fehler: Prozess beendet (Code: {proc.returncode})"}
        except Exception as e:
            self._log("ERROR", f"❌ Fehler bei der Ausführung von {name}: {e}")
            self._state["urls"][name] = {"url": f"Fehler: Ausführung fehlgeschlagen"}
        finally:
            with open(TUNNEL_LOG_FILE, "a") as f:
                f.write(f"===== END {name} LOG =====\n")


    def _get_cloudflare_url(self):
        name = "Cloudflare"
        try:
            cf_path = self._project_path / 'cloudflared'
            if not cf_path.exists():
                self._log("INFO", "Lade Cloudflared herunter...")
                subprocess.run(['wget', '-q', 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64', '-O', str(cf_path)], check=True)
                subprocess.run(['chmod', '+x', str(cf_path)], check=True)
            command = [str(cf_path), 'tunnel', '--url', f'http://127.0.0.1:{self.port}']
            self._run_tunnel_service(name, command, r'(https?://\S+\.trycloudflare\.com)', self._project_path)
        except Exception as e:
            self._log("ERROR", f"❌ Cloudflared-Vorbereitung fehlgeschlagen: {e}")
            self._state["urls"][name] = {"url": "Fehler: Vorbereitung fehlgeschlagen"}


    def _get_localtunnel_url(self):
        name = "Localtunnel"
        try:
            # ÄNDERUNG: 'npx lt' zu 'npx localtunnel' geändert, da 'localtunnel' der Paketname ist.
            # Dies ist robuster und erfordert keine globale Installation.
            self._log("INFO", "Verwende 'npx localtunnel' für mehr Stabilität...")
            command = ['npx', 'localtunnel', '--port', str(self.port)]
            self._run_tunnel_service(name, command, r'(https?://\S+\.loca\.lt)', self._project_path)
        except Exception as e:
            self._log("ERROR", f"❌ Localtunnel-Vorbereitung fehlgeschlagen: {e}")
            self._state["urls"][name] = {"url": "Fehler: Vorbereitung fehlgeschlagen"}

    def _get_colab_url(self):
        name = "Colab"
        self._log("INFO", f"-> Starte Tunnel für {name}...")

        # ÄNDERUNG: Hinzufügen einer Validierungslogik, um nicht-öffentliche URLs zu erkennen.
        VALID_COLAB_DOMAINS = re.compile(r"\.(google\.com|googleusercontent\.com)$")

        # Simulieren Sie den schlechten Fall, den der Benutzer gemeldet hat
        mock_colab_return_value = "https://m-s-1pnrbthp201zi.europe-west4-b.c.codatalab-user-runtimes.internal"

        self._log("INFO", f"Simulierter Colab-URL-Rückgabewert: {mock_colab_return_value}")

        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(mock_colab_return_value)
            hostname = parsed_url.hostname

            if hostname and VALID_COLAB_DOMAINS.search(hostname):
                self._state["urls"][name] = {"url": mock_colab_return_value}
                self._log("SUCCESS", f"✅ {name} (simuliert) Erfolg mit gültiger URL.")
            else:
                self._log("WARN", f"⚠️ {name} hat eine ungültige oder nicht-öffentliche URL zurückgegeben, die verworfen wird: {mock_colab_return_value}")
                # Fügen Sie nichts zum Status hinzu, damit es als fehlgeschlagen angezeigt wird.
                self._state["urls"][name] = {"url": f"Fehler: Nicht-öffentliche URL erkannt"}

        except Exception as e:
            self._log("ERROR", f"❌ Fehler bei der Validierung der Colab-URL: {e}")

    def start_tunnels(self):
        self._state["urls"] = {}
        racers = [
            threading.Thread(target=self._get_cloudflare_url),
            threading.Thread(target=self._get_localtunnel_url),
            threading.Thread(target=self._get_colab_url),
        ]
        for r in racers: r.start(); self.threads.append(r)

        for r in self.threads:
            r.join()

    def stop_tunnels(self):
        self._log("INFO", "Stoppe alle Tunnel-Dienste...")
        for p in self.processes:
            if p.poll() is None:
                try:
                    p.terminate()
                    p.wait(timeout=5)
                except Exception as e:
                    self._log("ERROR", f"Fehler beim Beenden des Prozesses {p.pid}: {e}")

# --- Dummy-Server und Hauptlogik ---
def dummy_server(port, started_event):
    """Ein einfacher HTTP-Server, der auf einem Port lauscht."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", port))
        s.listen(1)
        started_event.set() # Signalisieren, dass der Server bereit ist
        s.settimeout(1)
        while not stop_server.is_set():
            try:
                conn, addr = s.accept()
                with conn:
                    # Einfache Handhabung, um den Server am Laufen zu halten
                    conn.recv(1024)
            except socket.timeout:
                continue

if __name__ == '__main__':
    # Erstellen Sie einen sicheren temporären Ordner für Artefakte
    project_path = ROOT_DIR / PROJECT_FOLDER_NAME
    if project_path.exists():
        shutil.rmtree(project_path)
    project_path.mkdir()

    # Finden Sie einen freien Port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        free_port = s.getsockname()[1]

    log.info(f"Dummy-Server wird auf Port {free_port} gestartet...")

    # Starten Sie den Dummy-Server in einem Thread
    started_event = threading.Event()
    stop_server = threading.Event()
    server_thread = threading.Thread(target=dummy_server, args=(free_port, started_event))
    server_thread.daemon = True
    server_thread.start()

    # Warten Sie, bis der Server tatsächlich gestartet ist
    started_event.wait(timeout=10)
    if not started_event.is_set():
        log.error("Dummy-Server konnte nicht gestartet werden.")
        sys.exit(1)

    log.info("Server gestartet. Starte TunnelManager...")

    shared_state_main = {"urls": {}}
    log_manager_main = LogManager()
    tunnel_manager = None
    try:
        tunnel_manager = TunnelManager(free_port, shared_state_main, project_path, log_manager_main)
        tunnel_manager.start_tunnels()

        log.info("--- DIAGNOSEERGEBNISSE ---")
        log.info(f"Protokolldatei geschrieben nach: {TUNNEL_LOG_FILE}")
        log.info("Extrahierte URLs:")
        for name, data in shared_state_main.get("urls", {}).items():
            log.info(f"  - {name}: {data.get('url', 'KEINE URL')}")
        log.info("-------------------------")

    except Exception as e:
        log.error(f"Ein Fehler ist aufgetreten: {e}")
        traceback.print_exc()
    finally:
        if tunnel_manager:
            tunnel_manager.stop_tunnels()
        stop_server.set()
        server_thread.join(timeout=5)
        log.info("Diagnoseskript beendet.")
        # Bereinigen Sie den Diagnoseordner
        shutil.rmtree(project_path)
