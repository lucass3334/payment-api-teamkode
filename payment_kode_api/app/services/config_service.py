from ..database.database import get_empresa_config
import tempfile
import base64

def get_empresa_credentials(empresa_id: str):
    """
    Retorna todas as credenciais da empresa para os serviços Sicredi, Rede e Asaas.
    """
    config = get_empresa_config(empresa_id)
    if not config:
        raise ValueError(f"Configuração da empresa {empresa_id} não encontrada.")

    return {
        "asaas_api_key": config.get("asaas_api_key"),
        "sicredi_client_id": config.get("sicredi_client_id"),
        "sicredi_client_secret": config.get("sicredi_client_secret"),
        "sicredi_api_key": config.get("sicredi_api_key"),
        "rede_pv": config.get("rede_pv"),
        "rede_api_key": config.get("rede_api_key"),
        "sicredi_cert_base64": config.get("sicredi_cert_base64"),
        "sicredi_key_base64": config.get("sicredi_key_base64"),
        "sicredi_ca_base64": config.get("sicredi_ca_base64"),
    }

def create_temp_cert_files(empresa_id: str):
    """
    Gera arquivos temporários para os certificados mTLS do Sicredi a partir dos valores Base64.
    Retorna os caminhos para uso no request.
    """
    credentials = get_empresa_credentials(empresa_id)

    temp_files = {}
    for key, filename in [
        ("sicredi_cert_base64", "sicredi-cert.pem"),
        ("sicredi_key_base64", "sicredi-key.pem"),
        ("sicredi_ca_base64", "sicredi-ca.pem")
    ]:
        if credentials[key]:  # Apenas cria arquivos se houver dados base64
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(base64.b64decode(credentials[key]))
                temp_file.flush()
                temp_files[key] = temp_file.name  # Retorna o caminho do arquivo

    return temp_files
