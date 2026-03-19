import asyncio
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

# Import models directly to create DB records
from app.models.sport import Sport
from app.models.competition import Competition
from app.models.match import Match

# --- Configuración ---
BASE_URL = "http://localhost:8000/api/v1"

# DB connection (same as app)
from app.core.database import engine


async def create_prerequisite_entities(db_session: AsyncSession, tax_year: int):
    """Create Sport, Competition, and Matches directly in DB via SQLAlchemy.

    Since there are no API endpoints for these entities, we create them
    directly to satisfy FK constraints for picks.

    Flushes the FK chain in one transaction, then commit() so other
    connections (the API) see sport/competition/match rows before httpx.
    """
    print("📦 Creating Sport, Competition, and Matches via DB...")

    uid = uuid.uuid4().hex[:8]
    match_ids: list[str] = []

    sport = Sport(
        name=f"Fiscal Test Soccer {uid}",
        slug=f"fiscal-soccer-{uid}",
    )
    db_session.add(sport)
    await db_session.flush()
    sport_id = sport.sport_id
    print(f"✅ Sport created: {sport_id}")

    comp = Competition(
        sport_id=sport_id,
        name=f"Test League {uid}",
        country="MEX",
        tier="A",
    )
    db_session.add(comp)
    await db_session.flush()
    comp_id = comp.competition_id
    print(f"✅ Competition created: {comp_id}")

    for i in range(5):
        match = Match(
            competition_id=comp_id,
            home_team=f"Home {i+1}",
            away_team=f"Away {i+1}",
            kickoff_at=datetime(
                tax_year, 1, 1 + i, 12, 0, 0, tzinfo=timezone.utc
            ),
        )
        db_session.add(match)
        await db_session.flush()
        match_ids.append(str(match.match_id))

    await db_session.commit()
    print(f"✅ Committed Sport, Competition, and {len(match_ids)} matches to DB")
    return match_ids


def get_mock_data(sb_id: str, match_ids: list, tax_year: int):
    m1, m2, m3, m4, m5 = match_ids
    sb = str(sb_id)

    picks = [
        {"match_id": str(m1), "sportsbook_id": sb, "market": "ML", "selection": "Team A", "odds_american": 200, "stake": 100, "status": "won"},
        {"match_id": str(m2), "sportsbook_id": sb, "market": "Spread", "selection": "Team B -3", "odds_american": -110, "stake": 220, "status": "won"},
        {"match_id": str(m3), "sportsbook_id": sb, "market": "Over/Under", "selection": "Over 2.5", "odds_american": 100, "stake": 50, "status": "won"},
        {"match_id": str(m4), "sportsbook_id": sb, "market": "ML", "selection": "Team C", "odds_american": 150, "stake": 100, "status": "lost"},
        {"match_id": str(m5), "sportsbook_id": sb, "market": "ML", "selection": "Team D", "odds_american": -200, "stake": 200, "status": "lost"},
        {"match_id": str(m1), "sportsbook_id": sb, "market": "Spread", "selection": "Team E", "odds_american": -110, "stake": 110, "status": "push"},
    ]

    transactions = [
        {"sportsbook_id": sb, "type": "deposit", "amount": 1000.00, "currency": "MXN", "exchange_rate": 1.0, "transaction_date": f"{tax_year}-01-01"},
        {"sportsbook_id": sb, "type": "bonus", "amount": 200.00, "currency": "MXN", "exchange_rate": 1.0, "transaction_date": f"{tax_year}-01-01"},
        {"sportsbook_id": sb, "type": "withdrawal", "amount": 500.00, "currency": "MXN", "exchange_rate": 1.0, "transaction_date": f"{tax_year}-05-15"},
        {"sportsbook_id": sb, "type": "deposit", "amount": 100.00, "currency": "USD", "exchange_rate": 20.0, "transaction_date": f"{tax_year}-08-01"},
    ]

    return picks, transactions


async def seed():
    tax_year = date.today().year

    # Create async session for DB work
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as db:
        match_ids = await create_prerequisite_entities(db, tax_year)

    # Now use HTTP API for sportsbook, transactions, picks
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("\n🚀 Iniciando Seed para validación Fiscal...")
        print(f"   (Año fiscal de consulta: {tax_year})")

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

        picks, txns = get_mock_data(sb_id, match_ids, tax_year)
        
        # 2. Inyectar Transacciones via Bulk
        print(f"\n📥 Inyectando {len(txns)} transacciones via /bulk...")
        txn_res = await client.post(f"{BASE_URL}/transactions/bulk", json={"transactions": txns})
        if txn_res.status_code != 201:
            print(f"❌ Error bulk txns: {txn_res.text}")
        else:
            print(f"✅ Transacciones inyectadas.")
        
        # 3. Inyectar Picks y resolverlos
        print(f"\n📥 Inyectando {len(picks)} picks...")
        picks_ok = True
        for p_data in picks:
            status = p_data.pop("status")
            payload = {
                "match_id": str(p_data["match_id"]),
                "sportsbook_id": str(p_data["sportsbook_id"]),
                "market": p_data["market"],
                "selection": p_data["selection"],
                "odds_american": p_data["odds_american"],
                "stake": p_data["stake"],
            }
            p_res = await client.post(f"{BASE_URL}/picks/", json=payload)
            if p_res.status_code == 201:
                p_id = p_res.json()["pick_id"]
                resolve_res = await client.patch(
                    f"{BASE_URL}/picks/{p_id}/result",
                    json={"status": status},
                )
                if resolve_res.status_code != 200:
                    picks_ok = False
                    print(f"⚠️  Error resolviendo pick {p_id}: {resolve_res.text}")
            else:
                picks_ok = False
                print(f"❌ Error creando pick: {p_res.text}")

        if picks_ok:
            print("✅ Picks inyectados y resueltos.")
        else:
            print("❌ Falló la inyección de picks; no se valida el resumen fiscal.")
            return

        # 5. Verificar resumen fiscal (Taxable Base ~ $150 MXN por redondeo de odds)
        fs_res = await client.get(
            f"{BASE_URL}/fiscal/summary",
            params={"tax_year": tax_year},
        )
        if fs_res.status_code != 200:
            print(f"❌ Error leyendo resumen fiscal: {fs_res.text}")
            return
        fs = fs_res.json()
        tb = Decimal(str(fs["taxable_base_estimate_mxn"]))
        print("\n" + "=" * 60)
        print("📊 RESUMEN FISCAL (API)")
        print("=" * 60)
        print(f"  Net gambling income: {fs['net_gambling_income_mxn']} MXN")
        print(f"  Taxable base (estimate): {fs['taxable_base_estimate_mxn']} MXN")
        print("=" * 60)
        if abs(tb - Decimal("150")) <= Decimal("2"):
            print("✅ Inyección OK — Taxable Base ~ $150.00 MXN")
        else:
            print(
                f"⚠️  Taxable Base esperada ~150 MXN; obtenida {tb} MXN "
                "(revisa año fiscal y datos de seed)."
            )
        
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
        print(f"\n👉 Swagger / curl:")
        print(f"GET {BASE_URL}/fiscal/summary?tax_year={tax_year}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed())
