import asyncio
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Import models directly to create DB records
from app.models.sport import Sport
from app.models.competition import Competition
from app.models.match import Match

# --- Configuración ---
BASE_URL = "http://localhost:8000/api/v1"
TAX_YEAR = 2025

# DB connection (same as app)
from app.core.database import engine


async def create_prerequisite_entities(db_session: AsyncSession):
    """Create Sport, Competition, and Matches directly in DB via SQLAlchemy.
    
    Since there are no API endpoints for these entities, we create them
    directly to satisfy FK constraints for picks.
    """
    print("📦 Creating Sport, Competition, and Matches via DB...")
    
    # 1. Create Sport
    sport = Sport(name="Soccer", slug="soccer")
    db_session.add(sport)
    await db_session.flush()  # Get sport_id
    sport_id = sport.sport_id
    print(f"✅ Sport created: {sport_id}")
    
    # 2. Create Competition
    comp = Competition(
        sport_id=sport_id,
        name="Test League",
        country="MEX",
        tier="A"
    )
    db_session.add(comp)
    await db_session.flush()
    comp_id = comp.competition_id
    print(f"✅ Competition created: {comp_id}")
    
    # 3. Create 5 matches (one for each pick)
    match_ids = []
    for i in range(5):
        match = Match(
            competition_id=comp_id,
            home_team=f"Home {i+1}",
            away_team=f"Away {i+1}",
            kickoff_at=datetime(2025, 1, 1+i, 12, 0, 0)
        )
        db_session.add(match)
        await db_session.flush()
        match_ids.append(str(match.match_id))
    
    print(f"✅ Created {len(match_ids)} matches")
    await db_session.commit()
    return match_ids


def get_mock_data(sb_id: str, match_ids: list):
    # Use the match_ids we just created
    m1, m2, m3, m4, m5 = match_ids
    
    # 1. Picks (won, lost, push)
    picks = [
        # Ganados
        {"match_id": m1, "sportsbook_id": sb_id, "market": "ML", "selection": "Team A", "odds_american": 200, "stake": 100, "status": "won"},
        {"match_id": m2, "sportsbook_id": sb_id, "market": "Spread", "selection": "Team B -3", "odds_american": -110, "stake": 220, "status": "won"},
        {"match_id": m3, "sportsbook_id": sb_id, "market": "Over/Under", "selection": "Over 2.5", "odds_american": 100, "stake": 50, "status": "won"},
        # Perdidos
        {"match_id": m4, "sportsbook_id": sb_id, "market": "ML", "selection": "Team C", "odds_american": 150, "stake": 100, "status": "lost"},
        {"match_id": m5, "sportsbook_id": sb_id, "market": "ML", "selection": "Team D", "odds_american": -200, "stake": 200, "status": "lost"},
        # Push (no cuenta para taxable base)
        {"match_id": m1, "sportsbook_id": sb_id, "market": "Spread", "selection": "Team E", "odds_american": -110, "stake": 110, "status": "push"},
    ]
    
    # 2. Transacciones
    transactions = [
        {"sportsbook_id": sb_id, "type": "deposit", "amount": 1000.00, "currency": "MXN", "exchange_rate": 1.0, "transaction_date": "2025-01-01"},
        {"sportsbook_id": sb_id, "type": "bonus", "amount": 200.00, "currency": "MXN", "exchange_rate": 1.0, "transaction_date": "2025-01-01"},
        {"sportsbook_id": sb_id, "type": "withdrawal", "amount": 500.00, "currency": "MXN", "exchange_rate": 1.0, "transaction_date": "2025-05-15"},
        # Moneda extranjera
        {"sportsbook_id": sb_id, "type": "deposit", "amount": 100.00, "currency": "USD", "exchange_rate": 20.0, "transaction_date": "2025-08-01"},  # 2000 MXN
    ]
    
    return picks, transactions


async def seed():
    # Create async session for DB work
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as db:
        # Create prerequisite entities (sport, competition, matches)
        match_ids = await create_prerequisite_entities(db)
    
    # Now use HTTP API for sportsbook, transactions, picks
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("\n🚀 Iniciando Seed para validación Fiscal...")
        
        # 1. Crear Sportsbook
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
        
        picks, txns = get_mock_data(sb_id, match_ids)
        
        # 2. Inyectar Transacciones via Bulk
        print(f"\n📥 Inyectando {len(txns)} transacciones via /bulk...")
        txn_res = await client.post(f"{BASE_URL}/transactions/bulk", json={"transactions": txns})
        if txn_res.status_code != 201:
            print(f"❌ Error bulk txns: {txn_res.text}")
        else:
            print(f"✅ Transacciones inyectadas.")
        
        # 3. Inyectar Picks y resolverlos
        print(f"\n📥 Inyectando {len(picks)} picks...")
        for p_data in picks:
            status = p_data.pop("status")
            
            p_res = await client.post(f"{BASE_URL}/picks/", json=p_data)
            if p_res.status_code == 201:
                p_id = p_res.json()["pick_id"]
                # Resolver pick
                resolve_res = await client.patch(f"{BASE_URL}/picks/{p_id}/result", json={
                    "status": status
                })
                if resolve_res.status_code != 200:
                    print(f"⚠️  Error resolviendo pick {p_id}: {resolve_res.text}")
            else:
                print(f"❌ Error creando pick: {p_res.text}")
        
        print(f"✅ Picks inyectados y resueltos.")
        
        # 4. Cálculo de valores esperados
        # Gross Winnings (PROFIT = stake*odds - stake):
        # Pick1: 100*(3.0-1)=200 | Pick2: 220*(1.909-1)=~200 | Pick3: 50*(2.0-1)=50
        # Total profit: ~200 + 200 + 50 = ~450
        # Gross Losses: 100 + 200 = 300
        # Net Gambling Income (Taxable Base): ~450 - 300 = ~150
        # Deposits: 1000 + 200 + (100*20) = 3200
        # Withdrawals: 500
        print("\n" + "="*60)
        print("📊 VALIDACIÓN — VALORES ESPERADOS (APROX)")
        print("="*60)
        print(f"Gross Winnings (profit): ~$450.00")
        print(f"Gross Losses: $300.00")
        print(f"Net Gambling Income (Taxable Base): ~$150.00")
        print(f"Total Deposits: $3,200.00")
        print(f"Total Withdrawals: $500.00")
        print("="*60)
        print(f"\n👉 Ejecuta ahora en Swagger o curl:")
        print(f"GET {BASE_URL}/fiscal/summary?tax_year={TAX_YEAR}")
        print("="*60)


if __name__ == "__main__":
    asyncio.run(seed())
