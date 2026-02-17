"""수급 연속성 라우터."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import verify_token

router = APIRouter(prefix="/api/supply", tags=["supply"])


class SupplySnapshotItem(BaseModel):
    id: int
    snapshot_time: str
    market: str
    index_value: float | None = None
    index_change_rate: float | None = None
    foreign_net_buy: int | None = None
    institution_net_buy: int | None = None
    individual_net_buy: int | None = None
    foreign_trend: str | None = None
    institution_trend: str | None = None


@router.get("/latest", response_model=list[SupplySnapshotItem])
async def get_latest_supply(
    market: str = Query(default="KOSPI"),
    limit: int = Query(default=10, le=60),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """최근 수급 스냅샷 조회"""
    result = await db.execute(
        text(
            "SELECT id, snapshot_time, market, index_value, index_change_rate, "
            "foreign_net_buy, institution_net_buy, individual_net_buy, "
            "foreign_trend, institution_trend "
            "FROM supply_snapshots "
            "WHERE market = :market "
            "ORDER BY snapshot_time DESC "
            "LIMIT :limit"
        ),
        {"market": market, "limit": limit},
    )
    rows = result.mappings().all()
    return [
        SupplySnapshotItem(
            id=r["id"],
            snapshot_time=str(r["snapshot_time"]),
            market=r["market"],
            index_value=float(r["index_value"]) if r["index_value"] else None,
            index_change_rate=float(r["index_change_rate"]) if r["index_change_rate"] else None,
            foreign_net_buy=r["foreign_net_buy"],
            institution_net_buy=r["institution_net_buy"],
            individual_net_buy=r["individual_net_buy"],
            foreign_trend=r["foreign_trend"],
            institution_trend=r["institution_trend"],
        )
        for r in rows
    ]


@router.get("/trend")
async def get_supply_trend(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """KOSPI/KOSDAQ 최신 수급 추세 요약"""
    summaries = {}
    for market in ["KOSPI", "KOSDAQ"]:
        result = await db.execute(
            text(
                "SELECT index_value, index_change_rate, "
                "foreign_net_buy, institution_net_buy, individual_net_buy, "
                "foreign_trend, institution_trend, snapshot_time "
                "FROM supply_snapshots "
                "WHERE market = :market "
                "ORDER BY snapshot_time DESC LIMIT 1"
            ),
            {"market": market},
        )
        row = result.mappings().first()
        if row:
            summaries[market] = {
                "index_value": float(row["index_value"]) if row["index_value"] else 0,
                "index_change_rate": float(row["index_change_rate"]) if row["index_change_rate"] else 0,
                "foreign_net_buy": row["foreign_net_buy"] or 0,
                "institution_net_buy": row["institution_net_buy"] or 0,
                "individual_net_buy": row["individual_net_buy"] or 0,
                "foreign_trend": row["foreign_trend"] or "flat",
                "institution_trend": row["institution_trend"] or "flat",
                "snapshot_time": str(row["snapshot_time"]),
            }
        else:
            summaries[market] = None

    return summaries
