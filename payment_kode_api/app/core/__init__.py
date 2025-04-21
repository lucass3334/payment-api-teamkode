import uvicorn

def start():
    """Função para iniciar o servidor Uvicorn"""
    from payment_kode_api.app.main import app  # ✅ Importação dentro da função evita erro
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    start()  # 🔹 Apenas inicia se executado diretamente  
