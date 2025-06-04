# payment_kode_api/app/services/gateways/sicredi_client.py

import httpx
import base64
import asyncio
from fastapi import HTTPException
from typing import Any, Dict, Optional
import re
from datetime import datetime, timezone, timedelta

# ✅ MANTÉM: Imports das interfaces (SEM imports circulares)
from ...interfaces import (
   ConfigRepositoryInterface,
   PaymentRepositoryInterface,
   CertificateServiceInterface,
)

# ❌ REMOVIDO: Imports que causavam circular import
# from ...dependencies import (
#     get_config_repository,
#     get_payment_repository,
#     get_certificate_service,
# )

from ...utilities.logging_config import logger
from ...utilities.cert_utils import get_md5, build_ssl_context_from_memory

# 🔧 Timeout padrão para conexões Sicredi
TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


async def get_access_token(
   empresa_id: str, 
   retries: int = 2,
   config_repo: Optional[ConfigRepositoryInterface] = None,
   cert_service: Optional[CertificateServiceInterface] = None
) -> str:
   """
   ✅ MIGRADO: Solicita um novo token diretamente na API Sicredi via client_credentials.
   Agora usa interfaces para evitar imports circulares.
   """
   # ✅ LAZY LOADING: Dependency injection
   if config_repo is None:
       from ...dependencies import get_config_repository
       config_repo = get_config_repository()
   if cert_service is None:
       from ...dependencies import get_certificate_service
       cert_service = get_certificate_service()

   # ✅ USANDO INTERFACE
   credentials = await config_repo.get_empresa_config(empresa_id)
   if not credentials:
       raise ValueError("❌ Credenciais do Sicredi não configuradas corretamente.")

   client_id = credentials["sicredi_client_id"]
   client_secret = credentials["sicredi_client_secret"]
   env = credentials.get("sicredi_env", "production").lower()

   auth_url = (
       "https://api-h.pix.sicredi.com.br/oauth/token"
       if env == "homologation"
       else "https://api-pix.sicredi.com.br/oauth/token"
   )
   auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

   headers = {
       "Authorization": f"Basic {auth_header}",
       "Content-Type": "application/json"
   }
   
   # Corrige a query string, removendo duplicação de grant_type e incluindo apenas scopes válidos
   full_url = (
       f"{auth_url}"
       "?grant_type=client_credentials"
       "&scope=cob.read%20cob.write%20cobv.read%20cobv.write"
   )

   # ✅ USANDO INTERFACE
   certs = await cert_service.load_certificates_from_bucket(empresa_id)
   try:
       ssl_ctx = build_ssl_context_from_memory(
           cert_pem=certs["cert_path"],
           key_pem=certs["key_path"],
           ca_pem=certs["ca_path"]
       )
   except Exception as e:
       logger.error(f"❌ Erro ao montar SSLContext: {e}")
       raise HTTPException(status_code=500, detail="Erro ao processar certificados da empresa.")

   logger.debug(f"🔑 cert.pem md5: {get_md5(certs['cert_path'])}")
   logger.debug(f"🔑 key.key md5:  {get_md5(certs['key_path'])}")
   logger.debug(f"🔑 ca.pem md5:   {get_md5(certs['ca_path'])}")

   for attempt in range(1, retries + 1):
       try:
           async with httpx.AsyncClient(verify=ssl_ctx, timeout=TIMEOUT) as client:
               logger.info(f"🔐 Sicredi token attempt {attempt} → {full_url}")
               resp = await client.post(full_url, headers=headers)
               resp.raise_for_status()

               data = resp.json()
               token = data.get("access_token")
               if token:
                   return token

               logger.error(f"❌ Nenhum access_token no retorno Sicredi: {data}")
               break

       except httpx.HTTPStatusError as e:
           code = e.response.status_code
           logger.error(f"❌ HTTP {code} obtendo token Sicredi")
           if code in (401, 403) and attempt == retries:
               raise HTTPException(status_code=410, detail="Credenciais Sicredi inválidas ou expiradas.")
       except Exception as e:
           logger.error(f"❌ Erro inesperado ao requisitar token Sicredi: {e}")
           raise

       await asyncio.sleep(2)

   raise RuntimeError(f"❌ Falha ao obter token Sicredi para empresa {empresa_id}")


async def create_sicredi_pix_payment(
   empresa_id: str, 
   config_repo: Optional[ConfigRepositoryInterface] = None,
   cert_service: Optional[CertificateServiceInterface] = None,
   **payload: Any
) -> Dict[str, Any]:
   """
   ✅ MIGRADO: Cria ou altera uma cobrança Pix no Sicredi.
   Se `due_date` for fornecido, cria cobrança com vencimento via PUT /cobv/{txid}.
   Caso contrário, cria cobrança imediata via PUT /cob/{txid}.
   """
   # ✅ LAZY LOADING: Dependency injection
   if config_repo is None:
       from ...dependencies import get_config_repository
       config_repo = get_config_repository()
   if cert_service is None:
       from ...dependencies import get_certificate_service
       cert_service = get_certificate_service()

   # 1) Token Sicredi - ✅ USANDO INTERFACE
   token = await config_repo.get_sicredi_token_or_refresh(empresa_id)
   if not token:
       raise HTTPException(status_code=401, detail="Token Sicredi inválido ou expirado.")

   # 2) URL base (prod ou homolog) - ✅ USANDO INTERFACE
   credentials = await config_repo.get_empresa_config(empresa_id)
   env = credentials.get("sicredi_env", "production").lower()
   base_url = (
       "https://api-h.pix.sicredi.com.br/api/v2" if env == "homologation"
       else "https://api-pix.sicredi.com.br/api/v2"
   )

   # 3) Sanitiza txid
   raw_txid = payload.get("txid", "")
   txid = re.sub(r'[^A-Za-z0-9]', '', raw_txid).upper()[:35]
   if not txid:
       raise HTTPException(status_code=400, detail="txid inválido após sanitização.")

   # 4) Define tipo de cobrança pelo conteúdo do calendário
   is_scheduled = "dataDeVencimento" in payload.get("calendario", {})
   body_calendario = payload["calendario"]

   # 5) Monta body
   body: Dict[str, Any] = {
       "calendario": body_calendario,
       "chave": payload["chave"],
       "valor": {"original": payload["valor"]["original"]},
   }
   if "devedor" in payload:
       body["devedor"] = payload["devedor"]
   if "solicitacaoPagador" in payload:
       body["solicitacaoPagador"] = payload["solicitacaoPagador"]

   # 6) SSLContext mTLS - ✅ USANDO INTERFACE
   certs = await cert_service.load_certificates_from_bucket(empresa_id)
   try:
       ssl_ctx = build_ssl_context_from_memory(
           cert_pem=certs["cert_path"],
           key_pem=certs["key_path"],
           ca_pem=certs["ca_path"]
       )
   except Exception as e:
       logger.error(f"❌ Erro ao montar SSLContext (cobrança): {e}")
       raise HTTPException(status_code=500, detail="Erro com certificados da empresa.")

   # 7) Escolhe endpoint conforme tipo
   endpoint = f"{base_url}/{'cobv' if is_scheduled else 'cob'}/{txid}"

   # 8) Envia requisição
   async with httpx.AsyncClient(verify=ssl_ctx, timeout=TIMEOUT) as client:
       logger.info(f"📤 Enviando Pix para Sicredi: PUT {endpoint} – body: {body}")
       try:
           resp = await client.put(
               endpoint,
               json=body,
               headers={
                   "Authorization": f"Bearer {token}",
                   "Content-Type": "application/json"
               }
           )
           resp.raise_for_status()
       except httpx.HTTPStatusError as e:
           logger.error(f"❌ Sicredi retornou HTTP {e.response.status_code}: {e.response.text}")
           raise HTTPException(
               status_code=e.response.status_code,
               detail=f"Erro no gateway Sicredi: {e.response.text}"
           ) from e
       data = resp.json()

   # 9) (Re)registra webhook
   await register_sicredi_webhook(
       empresa_id, 
       payload["chave"],
       config_repo=config_repo,
       cert_service=cert_service
   )

   # 10) Calcula prazo de estorno (7 dias após vencimento se agendada; senão, 7 dias a partir de agora)
   if is_scheduled:
       due_date_str = payload["calendario"]["dataDeVencimento"]
       try:
           due_date_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
       except ValueError:
           due_date_date = datetime.fromisoformat(due_date_str).date()
       refund_deadline = (due_date_date + timedelta(days=7)).isoformat()
   else:
       now = datetime.now(timezone.utc)
       refund_deadline = (now + timedelta(days=7)).isoformat()

   # 11) Prepara retorno
   result: Dict[str, Any] = {
       "qr_code": data.get("pixCopiaECola"),
       "pix_link": data.get("location"),
       "status": data.get("status"),
       "refund_deadline": refund_deadline
   }
   if is_scheduled:
       result["due_date"] = payload["calendario"]["dataDeVencimento"]
   else:
       result["expiration"] = data["calendario"].get("expiracao")

   return result


async def register_sicredi_webhook(
   empresa_id: str, 
   chave_pix: str,
   config_repo: Optional[ConfigRepositoryInterface] = None,
   cert_service: Optional[CertificateServiceInterface] = None
) -> Any:
   """
   ✅ MIGRADO: Consulta e, se ausente, registra o webhook no Sicredi via PUT /webhook/{chave}.
   """
   # ✅ LAZY LOADING: Dependency injection
   if config_repo is None:
       from ...dependencies import get_config_repository
       config_repo = get_config_repository()
   if cert_service is None:
       from ...dependencies import get_certificate_service
       cert_service = get_certificate_service()

   # ✅ USANDO INTERFACE
   credentials = await config_repo.get_empresa_config(empresa_id)
   webhook_url = credentials.get("webhook_pix")
   if not webhook_url:
       logger.warning(f"⚠️ WEBHOOK_PIX não configurado para empresa {empresa_id}")
       return

   # ✅ USANDO INTERFACE
   token = await config_repo.get_sicredi_token_or_refresh(empresa_id)
   env = credentials.get("sicredi_env", "production").lower()
   base_url = (
       "https://api-h.pix.sicredi.com.br/api/v2"
       if env == "homologation"
       else "https://api-pix.sicredi.com.br/api/v2"
   )
   headers = {
       "Authorization": f"Bearer {token}",
       "Content-Type": "application/json"
   }

   # ✅ USANDO INTERFACE
   certs = await cert_service.load_certificates_from_bucket(empresa_id)
   try:
       ssl_ctx = build_ssl_context_from_memory(
           cert_pem=certs["cert_path"],
           key_pem=certs["key_path"],
           ca_pem=certs["ca_path"]
       )
   except Exception as e:
       logger.error(f"❌ Erro SSLContext (webhook): {e}")
       raise HTTPException(status_code=500, detail="Erro com certificados da empresa.")

   async with httpx.AsyncClient(verify=ssl_ctx, timeout=TIMEOUT) as client:
       # Verifica se já existe
       resp = await client.get(f"{base_url}/webhook/{chave_pix}", headers=headers)
       if resp.status_code == 200:
           logger.info(f"✅ Webhook já existe para {chave_pix}")
           return

       # Registra novo webhook
       logger.info(f"📤 Registrando webhook Sicredi para {chave_pix}")
       resp = await client.put(
           f"{base_url}/webhook/{chave_pix}",
           json={"webhookUrl": webhook_url},
           headers=headers
       )
       resp.raise_for_status()
       logger.info(f"✅ Webhook Sicredi registrado para {chave_pix}")
       return resp.json()


async def create_sicredi_pix_refund(
   empresa_id: str,
   txid: str,
   amount: Optional[float] = None,
   config_repo: Optional[ConfigRepositoryInterface] = None,
   cert_service: Optional[CertificateServiceInterface] = None
) -> Dict[str, Any]:
   """
   ✅ MIGRADO: Estorna uma cobrança Pix no Sicredi.
   - Para cobrança com vencimento (cobv): PATCH /cobv/{txid} {"status":"REMOVIDA_PELO_USUARIO_RECEBEDOR"}
   - Senão (cob imediata): POST /cob/{txid}/devolucao (opcionalmente com {"valor":{"original":"x.xx"}})
   """
   # ✅ LAZY LOADING: Dependency injection
   if config_repo is None:
       from ...dependencies import get_config_repository
       config_repo = get_config_repository()
   if cert_service is None:
       from ...dependencies import get_certificate_service
       cert_service = get_certificate_service()

   # 1) Busca token e credenciais - ✅ USANDO INTERFACE
   token = await config_repo.get_sicredi_token_or_refresh(empresa_id)
   if not token:
       raise HTTPException(401, "Token Sicredi inválido ou expirado.")
   
   credentials = await config_repo.get_empresa_config(empresa_id)
   env = credentials.get("sicredi_env", "production").lower()
   base_url = (
       "https://api-h.pix.sicredi.com.br/api/v2"
       if env == "homologation"
       else "https://api-pix.sicredi.com.br/api/v2"
   )

   # 2) Sanitiza txid
   sanitized_txid = re.sub(r'[^A-Za-z0-9]', '', txid).upper()

   # 3) Monta SSLContext para mTLS - ✅ USANDO INTERFACE
   certs = await cert_service.load_certificates_from_bucket(empresa_id)
   ssl_ctx = build_ssl_context_from_memory(
       cert_pem=certs["cert_path"],
       key_pem=certs["key_path"],
       ca_pem=certs.get("ca_path")
   )

   headers = {
       "Authorization": f"Bearer {token}",
       "Content-Type": "application/json"
   }

   async with httpx.AsyncClient(verify=ssl_ctx, timeout=10.0) as client:
       # a) Tenta PATCH em cobv
       url_cobv = f"{base_url}/cobv/{sanitized_txid}"
       try:
           logger.info(f"🔄 [create_sicredi_pix_refund] PATCH {url_cobv}")
           resp = await client.patch(
               url_cobv,
               json={"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"},
               headers=headers
           )
           resp.raise_for_status()
           data = resp.json()
           return {"status": data.get("status", "").upper(), **data}
       except httpx.HTTPStatusError as e:
           # Se não for 404, repassa erro
           if e.response.status_code != 404:
               logger.error(f"❌ [create_sicredi_pix_refund] PATCH HTTP {e.response.status_code}: {e.response.text}")
               raise HTTPException(e.response.status_code, f"Erro no gateway Sicredi: {e.response.text}")
           # 404 → segue para estorno imediato

       # b) Tenta POST em cob/devolucao
       url_cob = f"{base_url}/cob/{sanitized_txid}/devolucao"
       body = None
       if amount is not None:
           body = {"valor": {"original": f"{amount:.2f}"}}

       try:
           logger.info(f"🔄 [create_sicredi_pix_refund] POST {url_cob} body={body or '{}'}")
           resp = await client.post(url_cob, json=body, headers=headers)
           resp.raise_for_status()
           data = resp.json()
           return {"status": data.get("status", "").upper(), **data}
       except httpx.HTTPStatusError as e:
           logger.error(f"❌ [create_sicredi_pix_refund] POST HTTP {e.response.status_code}: {e.response.text}")
           if e.response.status_code == 404:
               raise HTTPException(404, "Cobrança não encontrada no Sicredi")
           raise HTTPException(e.response.status_code, f"Erro no gateway Sicredi: {e.response.text}")

   # Não achou nem cobv nem cob
   raise HTTPException(404, "Cobrança não encontrada no Sicredi")


# ========== CLASSES WRAPPER PARA INTERFACE ==========

class SicrediGateway:
   """
   ✅ NOVO: Classe wrapper que implementa SicrediGatewayInterface
   Permite uso direto das funções via dependency injection
   """
   
   def __init__(
       self,
       config_repo: Optional[ConfigRepositoryInterface] = None,
       cert_service: Optional[CertificateServiceInterface] = None
   ):
       # ✅ LAZY LOADING nos constructors também
       if config_repo is None:
           from ...dependencies import get_config_repository
           config_repo = get_config_repository()
       if cert_service is None:
           from ...dependencies import get_certificate_service
           cert_service = get_certificate_service()
           
       self.config_repo = config_repo
       self.cert_service = cert_service
   
   async def create_pix_payment(self, empresa_id: str, **kwargs) -> Dict[str, Any]:
       """Implementa SicrediGatewayInterface.create_pix_payment"""
       return await create_sicredi_pix_payment(
           empresa_id,
           config_repo=self.config_repo,
           cert_service=self.cert_service,
           **kwargs
       )
   
   async def create_pix_refund(self, empresa_id: str, txid: str, amount: Optional[float] = None) -> Dict[str, Any]:
       """Implementa SicrediGatewayInterface.create_pix_refund"""
       return await create_sicredi_pix_refund(
           empresa_id,
           txid,
           amount,
           config_repo=self.config_repo,
           cert_service=self.cert_service
       )
   
   async def get_access_token(self, empresa_id: str) -> str:
       """Implementa SicrediGatewayInterface.get_access_token"""
       return await get_access_token(
           empresa_id,
           config_repo=self.config_repo,
           cert_service=self.cert_service
       )
   
   async def register_webhook(self, empresa_id: str, chave_pix: str) -> Any:
       """Implementa SicrediGatewayInterface.register_webhook"""
       return await register_sicredi_webhook(
           empresa_id,
           chave_pix,
           config_repo=self.config_repo,
           cert_service=self.cert_service
       )


# ========== FUNÇÃO PARA DEPENDENCY INJECTION ==========

def get_sicredi_gateway_instance() -> SicrediGateway:
   """
   ✅ NOVO: Função para criar instância do SicrediGateway
   Pode ser usada nos dependencies.py
   """
   return SicrediGateway()


# ========== BACKWARD COMPATIBILITY ==========
# Mantém as funções originais para compatibilidade, mas agora elas usam interfaces

async def get_access_token_legacy(empresa_id: str, retries: int = 2) -> str:
   """
   ⚠️ DEPRECATED: Use get_access_token com dependency injection
   Mantido apenas para compatibilidade
   """
   logger.warning("⚠️ Usando função legacy get_access_token_legacy. Migre para a nova versão com interfaces.")
   return await get_access_token(empresa_id, retries)


# ========== EXPORTS ==========

__all__ = [
   # Funções principais (migradas)
   "get_access_token",
   "create_sicredi_pix_payment", 
   "register_sicredi_webhook",
   "create_sicredi_pix_refund",
   
   # Classe wrapper
   "SicrediGateway",
   "get_sicredi_gateway_instance",
   
   # Legacy (deprecated)
   "get_access_token_legacy",
]