"""Server HTTPS locale per provare il sito dal telefono.

I browser attivano la decifratura (Web Crypto) solo su HTTPS o localhost:
da un indirizzo http://192.168.x.x la funzione e' spenta. Qui generiamo un
certificato autofirmato valido per l'IP del PC, cosi' l'anteprima funziona
come funzionera' su GitHub Pages.
"""
import datetime
import http.server
import ipaddress
import os
import socket
import ssl
import sys

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

RADICE = os.path.dirname(os.path.abspath(__file__))
CERT = os.path.join(RADICE, "data", "locale-cert.pem")
CHIAVE = os.path.join(RADICE, "data", "locale-key.pem")
PORTA = 8443


def ip_locale() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def genera_certificato(ip: str) -> None:
    chiave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Spese locali")])
    alt = x509.SubjectAlternativeName([
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        x509.IPAddress(ipaddress.ip_address(ip)),
    ])
    adesso = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(nome).issuer_name(nome)
            .public_key(chiave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(adesso - datetime.timedelta(days=1))
            .not_valid_after(adesso + datetime.timedelta(days=825))
            .add_extension(alt, critical=False)
            .sign(chiave, hashes.SHA256()))

    os.makedirs(os.path.dirname(CERT), exist_ok=True)
    with open(CERT, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(CHIAVE, "wb") as f:
        f.write(chiave.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()))


def main() -> int:
    ip = ip_locale()
    # il certificato vale per un IP preciso: se la rete cambia va rifatto
    if not (os.path.exists(CERT) and os.path.exists(CHIAVE)) or "--rigenera" in sys.argv:
        genera_certificato(ip)
        print("Certificato generato.")
    else:
        try:
            with open(CERT, "rb") as f:
                esistente = x509.load_pem_x509_certificate(f.read())
            ips = esistente.extensions.get_extension_for_class(
                x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)
            if ipaddress.ip_address(ip) not in ips:
                genera_certificato(ip)
                print("Indirizzo IP cambiato: certificato rigenerato.")
        except Exception:
            genera_certificato(ip)

    os.chdir(os.path.join(RADICE, "sito"))
    contesto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contesto.load_cert_chain(CERT, CHIAVE)

    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORTA),
                                             http.server.SimpleHTTPRequestHandler)
    server.socket = contesto.wrap_socket(server.socket, server_side=True)

    print("=" * 58)
    print("  ANTEPRIMA (HTTPS)")
    print("=" * 58)
    print(f"\n  Dal telefono:  https://{ip}:{PORTA}")
    print(f"  Da questo PC:  https://localhost:{PORTA}")
    print("\n  Il certificato e' autofirmato: il telefono mostrera' un avviso")
    print("  di sicurezza. E' atteso, il server sei tu.")
    print("    Android/Chrome : 'Avanzate' -> 'Procedi verso...'")
    print("    iPhone/Safari  : 'Mostra dettagli' -> 'Visita il sito web'")
    print("\n  CTRL+C per fermare.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer fermato.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
