#!/usr/bin/env bash
# Generate mTLS certificates for Neuro-Pipeline (CA + server + client).
# Usage: bash tools/certs/generate_certs.sh [output_dir]
set -euo pipefail

OUT="${1:-certs}"
DAYS=365
CN_CA="Neuro-Pipeline CA"
CN_SERVER="neuro-pipeline-central"
CN_CLIENT="neuro-pipeline-edge"

mkdir -p "$OUT"

echo "=== Generating CA ==="
openssl genrsa -out "$OUT/ca-key.pem" 4096
openssl req -new -x509 -key "$OUT/ca-key.pem" -sha256 \
    -subj "/CN=${CN_CA}" -days "$DAYS" -out "$OUT/ca.pem"

echo "=== Generating Server cert ==="
openssl genrsa -out "$OUT/server-key.pem" 2048
openssl req -new -key "$OUT/server-key.pem" \
    -subj "/CN=${CN_SERVER}" -out "$OUT/server.csr"

cat > "$OUT/server-ext.cnf" <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:localhost,IP:127.0.0.1,IP:192.168.1.100
EOF

openssl x509 -req -in "$OUT/server.csr" -CA "$OUT/ca.pem" -CAkey "$OUT/ca-key.pem" \
    -CAcreateserial -out "$OUT/server.pem" -days "$DAYS" -sha256 \
    -extfile "$OUT/server-ext.cnf"

echo "=== Generating Client cert ==="
openssl genrsa -out "$OUT/client-key.pem" 2048
openssl req -new -key "$OUT/client-key.pem" \
    -subj "/CN=${CN_CLIENT}" -out "$OUT/client.csr"

cat > "$OUT/client-ext.cnf" <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature
extendedKeyUsage=clientAuth
EOF

openssl x509 -req -in "$OUT/client.csr" -CA "$OUT/ca.pem" -CAkey "$OUT/ca-key.pem" \
    -CAcreateserial -out "$OUT/client.pem" -days "$DAYS" -sha256 \
    -extfile "$OUT/client-ext.cnf"

# Cleanup CSR and temp files
rm -f "$OUT"/*.csr "$OUT"/*.cnf "$OUT"/*.srl

echo ""
echo "=== Certificates generated in $OUT/ ==="
ls -la "$OUT"/*.pem
echo ""
echo "Files:"
echo "  CA:          $OUT/ca.pem, $OUT/ca-key.pem"
echo "  Server:      $OUT/server.pem, $OUT/server-key.pem"
echo "  Client:      $OUT/client.pem, $OUT/client-key.pem"
