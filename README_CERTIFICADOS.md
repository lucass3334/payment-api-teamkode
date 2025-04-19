
# 📜 Manual de Certificados mTLS - Sicredi

Este guia explica como gerar, validar e usar certificados mTLS para autenticação com a API Pix do Sicredi na infraestrutura da Payment Kode API.

---

## 🧾 Estrutura esperada dos arquivos

Para cada empresa, são esperados **três arquivos** em formato `.pem` ou `.key`:

- `sicredi-cert.pem` → Certificado da aplicação
- `sicredi-key.key` → Chave privada correspondente **sem passphrase**
- `sicredi-ca.pem` → Cadeia de certificados da Sicredi (CA)

---

## 🛠️ Como gerar os certificados

> O CSR (Certificate Signing Request) é gerado localmente e enviado ao Sicredi para emissão do certificado.

```bash
openssl genrsa -out sicredi-key.key 2048

openssl req -new -key sicredi-key.key \
  -out santo_amaro_csr_sicredi_v2.csr \
  -subj "/C=BR/ST=SP/L=São Paulo/O=SuaEmpresa/CN=api.seudominio.com.br"
```

Após enviar o CSR, o Sicredi devolverá:
- Um `.cer` (certificado da aplicação)
- E fornecerá uma cadeia `.cer` da autoridade certificadora

Converta os arquivos `.cer` para `.pem`:

```bash
openssl x509 -inform DER -in sicredi-cert.cer -out sicredi-cert.pem
openssl x509 -inform DER -in sicredi-ca.cer -out sicredi-ca.pem
```

---

## 📤 Upload para Supabase Storage

Os arquivos devem ser enviados para o bucket `certificados-sicredi`, no seguinte path:

```
certificados-sicredi/
└── <empresa_id>/
    ├── sicredi-cert.pem
    ├── sicredi-key.key
    └── sicredi-ca.pem
```

Você pode fazer isso por:
- 🔹 Painel Supabase
- 🔹 API `/certificados/upload` (envia via multipart form)
- 🔹 Script local com `supabase.storage.from_().upload()`

---

## ✅ Validação dos Certificados

Use o endpoint interno para validar se os certificados foram carregados corretamente:

```http
GET /certificados/validate?empresa_id=<uuid>
```

Retorno esperado:

```json
{
  "empresa_id": "3dd974c8-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "valid": true,
  "files": {
    "cert_path": true,
    "key_path": true,
    "ca_path": true
  }
}
```

---

## ❗ Cuidados

- O arquivo `.key` **NÃO pode conter passphrase**.
- Os certificados **são carregados em memória** e não ficam salvos em disco.
- O Supabase Storage **é o único ponto de verdade**.
- Em caso de erro: `certificate verify failed: unable to get local issuer certificate`, o problema está no `sicredi-ca.pem`.

---

## 🤝 Suporte

Para dúvidas ou problemas, entre em contato com a equipe técnica da Payment Kode.
