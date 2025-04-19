
# 🔐 Certificados mTLS - Integração com Sicredi Pix

Este documento descreve o processo completo para **gerar e validar a cadeia de certificados (CA)** necessária para autenticação mTLS com a API Pix do **Sicredi**.

## 🧩 Visão Geral

Para comunicação segura com a Sicredi via mTLS, precisamos:

- Certificado **da empresa (cliente)** → `sicredi-cert.pem`
- **Chave privada** da empresa → `sicredi-key.pem`
- Cadeia de certificação completa → `sicredi-ca.pem` ← **este documento ensina como montar**

---

## 📁 Estrutura Final dos Arquivos

| Nome do Arquivo       | Conteúdo                                      |
|-----------------------|-----------------------------------------------|
| `sicredi-cert.pem`    | Certificado público da empresa                |
| `sicredi-key.pem`     | Chave privada da empresa                      |
| `sicredi-ca.pem`      | CA Intermediária + CA Raiz da DigiCert        |

---

## 📥 1. Download dos Certificados

### A. Certificados da empresa Sicredi
Acesse o portal Sicredi e baixe:

- `22308504000106.cer` (ou nome similar)
- `CadeiaCompletaSicredi.cer`

Renomeie:
```bash
mv 22308504000106.cer empresa-sicredi.cer
```

### B. Certificados da DigiCert
Acesse: [https://www.digicert.com/kb/digicert-root-certificates.htm](https://www.digicert.com/kb/digicert-root-certificates.htm)

Baixe os seguintes certificados:

- **Intermediário**: `DigiCert SHA2 Extended Validation Server CA`
- **Raiz**: `DigiCert High Assurance EV Root CA`

---

## 🛠 2. Converter todos os `.cer` para `.pem`

Execute os comandos abaixo para converter os arquivos para o formato PEM:

```bash
# Certificado da empresa
openssl x509 -inform DER -in empresa-sicredi.cer -out sicredi-cert.pem

# Intermediário DigiCert
openssl x509 -inform DER -in "DigiCertSHA2ExtendedValidationServerCA.crt" -out digicert-intermediario.pem

# Raiz DigiCert
openssl x509 -inform DER -in "DigiCertHighAssuranceEVRootCA.crt" -out digicert-raiz.pem
```

---

## 🧬 3. Montar o `sicredi-ca.pem` (Cadeia de certificação)

Use o comando abaixo para concatenar os certificados:

```bash
cat digicert-intermediario.pem digicert-raiz.pem > sicredi-ca.pem
```

> **Ordem correta:**
> - Primeiro o **Intermediário**
> - Depois o **Raiz**

---

## ✅ 4. Validar a cadeia com OpenSSL

Execute o comando abaixo para validar o SSL com o Sicredi:

```bash
openssl s_client -connect api-pix.sicredi.com.br:443 -CAfile sicredi-ca.pem
```

### Esperado:
```
Verify return code: 0 (ok)
```

---

## 🚀 5. Uso no código Python (exemplo)

```python
import ssl

context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
context.load_cert_chain(certfile="sicredi-cert.pem", keyfile="sicredi-key.pem")
context.load_verify_locations(cafile="sicredi-ca.pem")
```

---

## 🧪 Dica: Testar em memória com Python

Você pode carregar os conteúdos em memória sem precisar salvar em disco:

```python
from ssl import create_default_context
from tempfile import NamedTemporaryFile

def montar_contexto(cert: str, key: str, ca: str):
    with NamedTemporaryFile(delete=False) as cert_file, \
         NamedTemporaryFile(delete=False) as key_file, \
         NamedTemporaryFile(delete=False) as ca_file:
        
        cert_file.write(cert.encode())
        key_file.write(key.encode())
        ca_file.write(ca.encode())

        cert_file.flush()
        key_file.flush()
        ca_file.flush()

        context = create_default_context()
        context.load_cert_chain(certfile=cert_file.name, keyfile=key_file.name)
        context.load_verify_locations(cafile=ca_file.name)

        return context
```

---

## 📬 Suporte

Em caso de dúvidas ou erro `unable to get local issuer certificate`, revise a **ordem dos certificados** ou verifique se o arquivo `.cer` foi realmente convertido para `.pem`.

---

## 🛡️ Segurança

> Nunca compartilhe a `sicredi-key.pem` fora de ambientes controlados. Ela é **a chave privada da sua empresa** e permite autenticação total junto à Sicredi.

---

```

Se quiser posso gerar este README.md automaticamente, te mandar um `.md` ou colar direto no repositório. Deseja?