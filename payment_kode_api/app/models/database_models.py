from pydantic import BaseModel

class PaymentModel(BaseModel):
    """
    Modelo para representar pagamentos no banco de dados.
    """
    id: int
    amount: float
    customer_id: str
    status: str
    created_at: str
