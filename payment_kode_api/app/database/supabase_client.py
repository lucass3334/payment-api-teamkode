# payment_kode_api/app/database/supabase_client.py
from supabase import create_client
from payment_kode_api.app.core.config import settings

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
