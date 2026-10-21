import socket
import struct
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

PUERTO_SSDP = 1900
PUERTO_HTTP = 8091
GRUPO = "239.255.255.250"
UUID = "uuid:flowcast-televisor-simulado"
NOMBRE = "[TV] Televisor simulado FlowCast"
estado = {"transporte": "STOPPED", "uri": None}


def ip_para(destino: str) -> str:
    if destino.startswith("127."):
        return "10.0.2.2"
    sonda = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sonda.connect((destino, 9))
        return sonda.getsockname()[0]
    finally:
        sonda.close()


def respuesta_ssdp(ip: str, st: str) -> bytes:
    return (
        "HTTP/1.1 200 OK\r\n"
        "CACHE-CONTROL: max-age=1800\r\n"
        "EXT:\r\n"
        f"LOCATION: http://{ip}:{PUERTO_HTTP}/descripcion.xml\r\n"
        "SERVER: FlowCast/1.0 UPnP/1.0 TelevisorSimulado/1.0\r\n"
        f"ST: {st}\r\n"
        f"USN: {UUID}::{st}\r\n\r\n"
    ).encode()


def servidor_ssdp() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind(("", PUERTO_SSDP))
    sock.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_ADD_MEMBERSHIP,
        struct.pack("4sl", socket.inet_aton(GRUPO), socket.INADDR_ANY),
    )
    print(f"SSDP escuchando en UDP {PUERTO_SSDP} (multicast {GRUPO} y unicast)")
    while True:
        datos, origen = sock.recvfrom(4096)
        texto = datos.decode(errors="ignore")
        if not texto.startswith("M-SEARCH"):
            continue
        st = next(
            (
                l.split(":", 1)[1].strip()
                for l in texto.split("\r\n")
                if l.upper().startswith("ST:")
            ),
            "ssdp:all",
        )
        if st not in ("ssdp:all", "upnp:rootdevice") and "MediaRenderer" not in st:
            continue
        st_respuesta = (
            st if "MediaRenderer" in st else "urn:schemas-upnp-org:device:MediaRenderer:1"
        )
        sock.sendto(respuesta_ssdp(ip_para(origen[0]), st_respuesta), origen)
        print(f"M-SEARCH de {origen[0]}:{origen[1]} (ST={st}) -> respondido")


DESCRIPCION = f"""<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <specVersion><major>1</major><minor>0</minor></specVersion>
  <device>
    <deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
    <friendlyName>{NOMBRE}</friendlyName>
    <manufacturer>FlowCast</manufacturer>
    <modelName>Smart TV simulada</modelName>
    <UDN>{UUID}</UDN>
    <serviceList>
      <service>
        <serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
        <serviceId>urn:upnp-org:serviceId:AVTransport</serviceId>
        <controlURL>/control/AVTransport</controlURL>
        <eventSubURL>/eventos/AVTransport</eventSubURL>
        <SCPDURL>/AVTransport.xml</SCPDURL>
      </service>
    </serviceList>
  </device>
</root>
"""


def sobre_respuesta(accion: str, cuerpo: str = "") -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        f'<s:Body><u:{accion}Response xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">{cuerpo}</u:{accion}Response></s:Body></s:Envelope>'
    ).encode()


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, formato, *args):
        pass

    def do_GET(self):
        if self.path == "/descripcion.xml":
            cuerpo = DESCRIPCION.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            print(f"descripción servida a {self.client_address[0]}")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        longitud = int(self.headers.get("Content-Length", "0"))
        cuerpo = self.rfile.read(longitud).decode(errors="ignore")
        accion = self.headers.get("SOAPACTION", "").strip('"').split("#")[-1]
        respuesta = ""
        if accion == "SetAVTransportURI":
            inicio, fin = (
                cuerpo.find("<CurrentURI>") + len("<CurrentURI>"),
                cuerpo.find("</CurrentURI>"),
            )
            estado["uri"] = unquote(cuerpo[inicio:fin].replace("&amp;", "&"))
            estado["transporte"] = "STOPPED"
            print(f"SetAVTransportURI <- {estado['uri']}")
        elif accion == "Play":
            estado["transporte"] = "PLAYING"
            print("Play -> PLAYING")
        elif accion in ("Stop", "Pause"):
            estado["transporte"] = "STOPPED" if accion == "Stop" else "PAUSED_PLAYBACK"
            print(f"{accion} -> {estado['transporte']}")
        elif accion == "GetTransportInfo":
            respuesta = f"<CurrentTransportState>{estado['transporte']}</CurrentTransportState><CurrentTransportStatus>OK</CurrentTransportStatus><CurrentSpeed>1</CurrentSpeed>"
        else:
            print(f"acción no soportada: {accion}")
            self.send_response(500)
            self.end_headers()
            return
        datos = sobre_respuesta(accion, respuesta)
        self.send_response(200)
        self.send_header("Content-Type", 'text/xml; charset="utf-8"')
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)


if __name__ == "__main__":
    threading.Thread(target=servidor_ssdp, daemon=True).start()
    servidor = ThreadingHTTPServer(("", PUERTO_HTTP), Manejador)
    print(f"HTTP del televisor simulado en el puerto {PUERTO_HTTP}; Ctrl+C para salir")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
