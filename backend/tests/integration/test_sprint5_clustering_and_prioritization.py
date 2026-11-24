"""PostgreSQL + FastAPI integration tests for Sprint 5 (Clustering, Review 2, Prioritization)."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.clustering import ClusterKeyword, ClusterReview, KeywordCluster
from app.models.data_source import DataSource
from app.models.research import Keyword, KeywordMetric, ResearchRun
from app.models.serp import KeywordIntent, SerpResult, SerpSnapshot
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def _auth_headers(client: TestClient, email: str = "sprint5@example.com") -> dict[str, str]:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Sprint5 User"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_sprint5_clustering_review2_and_prioritization(
    api_client: TestClient, db_session: Session
) -> None:
    client = api_client
    headers = _auth_headers(client)
    proj = client.post(
        "/api/v1/projects",
        json={"name": "CRM SEO", "niche": "SaaS", "target_country": "VN", "target_language": "vi"},
        headers=headers,
    ).json()
    run = client.post(
        f"/api/v1/projects/{proj['id']}/research-runs",
        json={"name": "Sprint 5 Run", "seed_keywords": []},
        headers=headers,
    ).json()
    run_id = run["id"]

    # Add 3 keywords via Review 1 manual endpoint
    kws = []
    for text in [
        "phan mem crm tot nhat",
        "top phan mem crm cho doanh nghiep",
        "cach nau pho bo ha noi",
    ]:
        r = client.post(
            f"/api/v1/research-runs/{run_id}/keywords",
            json={"keyword": text},
            headers=headers,
        )
        assert r.status_code == 201
        kws.append(r.json())

    # Seed SERP overlap & intents & search volume directly in DB
    ds = db_session.scalar(select(DataSource).where(DataSource.code == "gkp_csv"))
    assert ds is not None
    run_obj = db_session.scalar(select(ResearchRun).where(ResearchRun.id == run_id))
    assert run_obj is not None

    urls_by_idx = [
        ["https://a.com/crm", "https://b.com/crm", "https://c.com/crm"],
        ["https://a.com/crm", "https://b.com/crm", "https://d.com/crm"],
        ["https://food.com/pho", "https://cook.com/pho"],
    ]
    intents_by_idx = ["COMMERCIAL", "COMMERCIAL", "INFORMATIONAL"]
    vols_by_idx = [5400, 1900, 12000]

    for idx, kw in enumerate(kws):
        snap = SerpSnapshot(
            research_run_id=run_obj.id,
            keyword_id=kw["id"],
            provider_code="dataforseo_serp",
            query_text=kw["original_keyword"],
            country_code="VN",
            language_code="vi",
            device="desktop",
            data_status="AVAILABLE",
            collected_at=datetime.now(UTC),
        )
        db_session.add(snap)
        db_session.flush()
        for pos, u in enumerate(urls_by_idx[idx], start=1):
            db_session.add(
                SerpResult(
                    serp_snapshot_id=snap.id,
                    position=pos,
                    url=u,
                    normalized_url=u,
                    domain=u.split("/")[2],
                    title=f"Title {pos}",
                )
            )
        db_session.add(
            KeywordIntent(
                keyword_id=kw["id"],
                serp_snapshot_id=snap.id,
                primary_intent=intents_by_idx[idx],
                confidence=Decimal("0.910"),
                reasoning="SERP evidence",
                evidence=[],
                model_version="heuristic-v1",
                prompt_version="intent-v1",
                origin="AI",
                is_current=True,
            )
        )
        db_session.add(
            KeywordMetric(
                keyword_id=kw["id"],
                source_id=ds.id,
                metric_type="SEARCH_VOLUME",
                numeric_value=Decimal(str(vols_by_idx[idx])),
                raw_value=str(vols_by_idx[idx]),
                unit="searches_per_month",
                country_code="VN",
                language_code="vi",
                data_status="AVAILABLE",
                collected_at=datetime.now(UTC),
            )
        )
    db_session.commit()

    # 1. Run hybrid clustering -> should produce 2 clusters (CRM cluster of 2, Pho cluster of 1)
    c_resp = client.post(
        f"/api/v1/research-runs/{run_id}/clusters/run",
        json={"distance_threshold": 0.45},
        headers=headers,
    )
    assert c_resp.status_code == 200
    clusters = c_resp.json()
    assert len(clusters) == 2
    crm_cluster = next(c for c in clusters if len(c["members"]) == 2)
    pho_cluster = next(c for c in clusters if len(c["members"]) == 1)

    # 2. Review 2: Rename + Split + Merge + Approve + verify invariant (no keyword in 2 active clusters)
    ren = client.patch(
        f"/api/v1/clusters/{crm_cluster['id']}/rename",
        json={"cluster_name": "CRM Software Comparison", "notes": "Clearer topic"},
        headers=headers,
    )
    assert ren.status_code == 200
    assert ren.json()["cluster_name"] == "CRM Software Comparison"
    assert ren.json()["origin"] == "HUMAN"

    kw_to_split = crm_cluster["members"][1]["keyword_id"]
    split_resp = client.post(
        f"/api/v1/clusters/{crm_cluster['id']}/split",
        json={"keyword_ids_to_extract": [kw_to_split], "new_cluster_name": "Enterprise CRM"},
        headers=headers,
    )
    assert split_resp.status_code == 200
    orig_after, new_after = split_resp.json()
    assert len(orig_after["members"]) == 1
    assert len(new_after["members"]) == 1

    merge_resp = client.post(
        "/api/v1/clusters/merge",
        json={
            "source_cluster_ids": [orig_after["id"], new_after["id"]],
            "target_cluster_name": "Unified CRM Cluster",
        },
        headers=headers,
    )
    assert merge_resp.status_code == 200
    merged = merge_resp.json()
    assert len(merged["members"]) == 2

    app_resp = client.post(
        f"/api/v1/clusters/{merged['id']}/approve",
        json={"notes": "Approved for brief"},
        headers=headers,
    )
    assert app_resp.status_code == 200
    assert app_resp.json()["status"] == "APPROVED"

    # Invariant check: no keyword belongs to 2 active clusters
    active_memberships = list(
        db_session.scalars(
            select(ClusterKeyword)
            .join(KeywordCluster, ClusterKeyword.cluster_id == KeywordCluster.id)
            .where(KeywordCluster.status.in_(("ACTIVE", "APPROVED")))
        ).all()
    )
    active_kw_ids = [m.keyword_id for m in active_memberships]
    assert len(active_kw_ids) == len(set(active_kw_ids))
    assert pho_cluster["id"] is not None

    reviews = list(db_session.scalars(select(ClusterReview)).all())
    assert len(reviews) >= 5

    # 3. Prioritization API
    p_resp = client.post(f"/api/v1/research-runs/{run_id}/prioritize", headers=headers)
    assert p_resp.status_code == 200
    p_data = p_resp.json()
    assert p_data["scored_keywords"] >= 3
    assert all(item["priority_reasoning"] for item in p_data["top_keywords"])

    db_kws = list(db_session.scalars(select(Keyword).where(Keyword.research_run_id == run_id)).all())
    assert all(k.priority_score is not None and k.priority_tier in ("P1", "P2", "P3") for k in db_kws)
