from app.routes import payments_router, webhooks_router

app.include_router(payments_router, prefix="/payments", tags=["payments"])
app.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])
 