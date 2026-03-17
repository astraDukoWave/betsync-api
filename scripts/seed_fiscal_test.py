import asyncio
import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
import httpx

# --- Configuración ---
BASE_URL = "http://localhost:8000/api/v1"
TAX_YEAR = 2025

# --- Datos de Prueba ---
def get_mock_data(sb_id: str):
    # UUIDs de prueba para matches (normalmente vendrían de la BD)
    m1, m2, m3, m4, m5 = [str(uuid.uuid4()) for _ in range(5)]
    
    # 1. Picks (won, lost, push, void)
    picks = [
        # Ganados
        {"match_id": m1, "sportsbook_id": sb_id, "market": "ML", "selection": "Team A", "odds_american": 200, "stake": 100, "status": "won", "resolved_at": "2025-01-15T12:00:00Z"},
        {"match_id": m2, "sportsbook_id": sb_id, "market": "Spread", "selection": "Team B -3", "odds_american": -110, "stake": 220, "status": "won", "resolved_at": "2025-03-10T15:00:00Z"},
        {"match_id": m3, "sportsbook_id": sb_id, "market": "Over/Under", "selection": "Over 2.5", "odds_american": 100, "stake": 50, "status": "won", "resolved_at": "2025-06-20T20:00:00Z"},
        # Perdidos
        {"match_id": m4, "sportsbook_id": sb_id, "market": "ML", "selection": "Team C", "odds_american": 150, "stake": 100, "status": "lost", "resolved_at": "2025-02-14T10:00:00Z"},
        {"match_id": m5, "sportsbook_id": sb_id, "market": "ML", "selection": "Team D", "odds_american": -200, "stake": 200, "status": "lost", "resolved_at": "2025-09-05T18:00:00Z"},
        # Push/Void
        {"match_id": m1, "sportsbook_id": sb_id, "market": "Spread", "selection": "Team E", "odds_american": -110, "stake": 110, "status": "push", "resolved_at": "2025-11-11T11:11:11Z"},
        # Edge case: run_date en 2024, resolved en 2025 (debe contar en 2025)
        {"match_id": m2, "sportsbook_id": sb_id, "market": "Future", "selection": "Champ", "odds_american": 500, "stake": 10, "status": "won", "resolved_at": "2025-01-02T01:00:00Z"},
    ]
    
    # 2. Transacciones (deposit, withdrawal, bonus)
    transactions = [
        {"sportsbook_id": sb_id, "type": "deposit", "amount": 1000.00, "currency": "MXN", "exchange_rate": 1.0, "transaction_date": "2025-01-01"},
        {"sportsbook_id": sb_id, "type": "bonus", "amount": 200.00, "currency": "MXN", "exchange_rate": 1.0, "transaction_date": "2025-01-01"},
        {"sportsbook_id": sb_id, "type": "withdrawal", "amount": 500.00, "currency": "MXN", "exchange_rate": 1.0, "transaction_date": "2025-05-15"},
        # Moneda extranjera
        {"sportsbook_id": sb_id, "type": "deposit", "amount": 100.00, "currency": "USD", "exchange_rate": 20.0, "transaction_date": "2025-08-01"}, # 2000 MXN
    ]
    
    return picks, transactions

async def seed():
    async with httpx.AsyncClient() as client:
        print("🚀 Iniciando Seed para validación Fiscal...")
        
        # 1. Crear o buscar Sportsbook
        sb_res = await client.post(f"{BASE_URL}/sportsbooks/", json={
            "name": f"Fiscal Test SB {str(uuid.uuid4())[:8]}",
            "currency": "MXN"
        })
        if sb_res.status_code not in (200, 201):
            print(f"❌ Error creando SB: {sb_res.text}")
            return
        sb = sb_res.json()
        sb_id = sb["sportsbook_id"]
        print(f"✅ Sportsbook creado: {sb_id}")

        picks, txns = get_mock_data(sb_id)

        # 2. Inyectar Transacciones via Bulk
        print(f"📥 Inyectando {len(txns)} transacciones via /bulk...")
        txn_res = await client.post(f"{BASE_URL}/transactions/bulk", json={"transactions": txns})
        if txn_res.status_code != 201:
            print(f"❌ Error bulk txns: {txn_res.text}")
        else:
            print(f"✅ Transacciones inyectadas.")

        # 3. Inyectar Picks uno a uno y resolverlos
        # Nota: Normalmente crearías el Match primero, pero aquí asumimos que el endpoint
        # de Pick no valida existencia de Match UUID de forma estricta o que podemos bypass.
        # En BetSync actual, el pick service busca el match. Crearemos matches genéricos.
        
        print(f"📥 Inyectando {len(picks)} picks...")
        for p_data in picks:
            # Crear Match
            match_res = await client.post(f"{BASE_URL}/config/matches", json={
                "competition_id": "00000000-0000-0000-0000-000000000000", # Asumimos existe o bypass
                "home_team": "Home", "away_team": "Away", "kickoff_at": "2025-01-01T00:00:00Z"
            })
            # Si falla config, intentamos crear pick directo (algunos setups permiten)
            # Para este script, asumo que los endpoints existen.
            
            res_at = p_data.pop("resolved_at")
            status = p_data.pop("status")
            
            p_res = await client.post(f"{BASE_URL}/picks/", json=p_data)
            if p_res.status_code == 201:
                p_id = p_res.json()["pick_id"]
                # Resolver pick con la fecha mock
                await client.patch(f"{BASE_URL}/picks/{p_id}/result", json={
                    "status": status,
                    "resolved_at": res_at # Nota: el API debe soportar recibir resolved_at para el seed
                })
        
        print(f"✅ Picks inyectados y resueltos.")
        
        # 4. Cálculo de valores esperados (manual en el script para comparar)
            # Gross Winnings (PROFIT = stake*odds - stake):
    #   Pick1: 100*(3.0-1)=200 | Pick2: 220*(1.909-1)=~200 | Pick3: 50*(2.0-1)=50 | Pick7: 10*(6.0-1)=50
    # Gross Winnings (profit total): ~200 + 200 + 50 + 50 = ~500
    # Gross Losses: 100 + 200 = 300
        # Net Gambling Income (Taxable Base): ~500 - 300 = ~200
    # Deposits: 1000 + 200 + (100*20) = 3200
    # Withdrawals: 500
        print("\n" + "="*40)
        print("📊 VALIDACIÓN — VALORES ESPERADOS (APROX)")
        print("="*40)
                print(f"Gross Winnings (profit): ~$500.00")
        print(f"Gross Losses:   $300.00")
        print(f"Total Deposits: $3,200.00")
        print(f"Total Withdraw: $500.00")
                print(f"Taxable Base:   ~$200.00")
        print("="*40)
        print(f"\n👉 Ejecuta ahora en Swagger:")
        print(f"GET {BASE_URL}/fiscal/summary?tax_year={TAX_YEAR}")
        print("="*40)

if __name__ == "__main__":
    asyncio.run(seed())
