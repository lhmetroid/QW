from __future__ import annotations

import argparse
import ipaddress
import os
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a local self-signed TLS certificate for uvicorn.")
    parser.add_argument("--cert-file", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--common-name", default="localhost")
    parser.add_argument("--days", type=int, default=3650)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def write_dev_certificate(cert_file: str, key_file: str, common_name: str, days: int, force: bool) -> None:
    if not force and os.path.exists(cert_file) and os.path.exists(key_file):
        return

    os.makedirs(os.path.dirname(cert_file), exist_ok=True)
    os.makedirs(os.path.dirname(key_file), exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "QW Local Dev"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=max(1, days)))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.DNSName("127.0.0.1.nip.io"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                    x509.IPAddress(ipaddress.ip_address("::1")),
                ]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private_key=key, algorithm=hashes.SHA256())
    )

    with open(key_file, "wb") as key_handle:
        key_handle.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    with open(cert_file, "wb") as cert_handle:
        cert_handle.write(cert.public_bytes(serialization.Encoding.PEM))


def main() -> int:
    args = parse_args()
    write_dev_certificate(
        cert_file=os.path.abspath(args.cert_file),
        key_file=os.path.abspath(args.key_file),
        common_name=args.common_name,
        days=args.days,
        force=args.force,
    )
    print(os.path.abspath(args.cert_file))
    print(os.path.abspath(args.key_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
