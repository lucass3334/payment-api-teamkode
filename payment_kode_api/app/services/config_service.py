from ..database.database import get_empresa_config, get_empresa_certificados
import tempfile
import base64

def get_empresa_credentials(empresa_id: str):
    """
    Retorna todas as credenciais da empresa para os serviços Sicredi, Rede e Asaas.
    Combina dados de configuração e certificados de tabelas diferentes.
    """
    try:
        # Busca configurações básicas
        config = get_empresa_config(empresa_id)
        if not config:
            raise ValueError(f"Configuração da empresa {empresa_id} não encontrada.")

        # Busca certificados digitais
        certificados = get_empresa_certificados(empresa_id) or {}

        return {
            "asaas_api_key": config.get("asaas_api_key"),
            "sicredi_client_id": config.get("sicredi_client_id"),
            "sicredi_client_secret": config.get("sicredi_client_secret"),
            "sicredi_api_key": config.get("sicredi_api_key"),
            "rede_pv": config.get("rede_pv"),
            "rede_api_key": config.get("rede_api_key"),
            # Certificados são obrigatórios para operações no Sicredi
            "sicredi_cert_base64": certificados.get("sicredi_cert_base64"),
            "sicredi_key_base64": certificados.get("sicredi_key_base64"),
            "sicredi_ca_base64": certificados.get("sicredi_ca_base64"),
        }

    except Exception as e:
        raise RuntimeError(f"Falha ao obter credenciais da empresa {empresa_id}: {str(e)}")

def create_temp_cert_files(empresa_id: str):
    """
    Gera arquivos temporários para os certificados mTLS do Sicredi com tratamento de erros.
    """
    try:
        credentials = get_empresa_credentials(empresa_id)
        required_certs = {
            "sicredi_cert_base64": "sicredi-cert.pem",
            "sicredi_key_base64": "sicredi-key.pem",
            "sicredi_ca_base64": "sicredi-ca.pem"
        }

        temp_files = {}
        for key, filename in required_certs.items():
            cert_data = credentials.get(key)
            if not cert_data:
                raise ValueError(f"Certificado {key} não encontrado para empresa {empresa_id}")

            with tempfile.NamedTemporaryFile(delete=False, suffix=filename) as temp_file:
                temp_file.write(base64.b64decode(cert_data))
                temp_file.flush()
                temp_files[key] = temp_file.name

        return temp_files

    except Exception as e:
        raise RuntimeError(f"Falha ao gerar certificados temporários: {str(e)}")