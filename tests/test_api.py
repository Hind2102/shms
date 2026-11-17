"""End-to-end tests through HTTP: the full report -> confirm -> route -> close workflow."""

import time

from tests.conftest import jpeg_bytes

REPORTER, OWNER_DIG, SUPERVISOR = 1, 4, 8  # ids from the deterministic seed (DIG is owned by user 4)


def h(uid):
    return {"X-User-Id": str(uid)}


def create(client, name="site_no_hard_hat.jpg", area="DIG", uid=REPORTER):
    return client.post(
        "/api/hazards", data={"area_code": area}, headers=h(uid), files={"photo": (name, jpeg_bytes(), "image/jpeg")}
    )


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_full_workflow_and_dashboard_update(client):
    before = client.get("/api/dashboard").json()["kpis"]["open"]
    t0 = time.perf_counter()
    r = create(client)
    assert r.status_code == 201
    draft = r.json()
    assert draft["status"] == "draft" and draft["ai_top_code"] == "no_hard_hat" and draft["ai_latency_ms"] is not None

    r = client.post(
        f"/api/hazards/{draft['id']}/confirm",
        headers=h(REPORTER),
        json={"category_code": "no_hard_hat", "consequence": 3, "description": "grinding"},
    )
    assert r.status_code == 200
    hz = r.json()
    assert hz["status"] == "open" and hz["assignee_id"] == OWNER_DIG and hz["ai_accepted"] is True
    assert hz["risk_score"] == 3 * hz["likelihood"]

    dash = client.get("/api/dashboard").json()
    elapsed = time.perf_counter() - t0
    assert dash["kpis"]["open"] == before + 1  # visible on the dashboard straight away
    assert elapsed < 5  # success criterion: report visible in seconds, not minutes

    r = client.post(f"/api/hazards/{hz['id']}/close", headers=h(OWNER_DIG), json={"action": "Hard hat issued"})
    assert r.status_code == 200 and r.json()["status"] == "closed"
    assert [e["kind"] for e in r.json()["events"]][-1] == "closed"


def test_reporter_can_correct_ai(client):
    hz = create(client).json()
    r = client.post(
        f"/api/hazards/{hz['id']}/confirm",
        headers=h(REPORTER),
        json={"category_code": "no_eye_protection", "consequence": 4},
    )
    assert r.json()["ai_accepted"] is False and r.json()["category_code"] == "no_eye_protection"


def test_photo_is_required(client):
    r = client.post("/api/hazards", data={"area_code": "CAL"}, headers=h(REPORTER))
    assert r.status_code == 422


def test_requires_sign_in(client):
    assert client.post("/api/hazards", data={"area_code": "DIG"}).status_code == 401


def test_wrong_person_cannot_close(client):
    hz = create(client).json()
    client.post(
        f"/api/hazards/{hz['id']}/confirm", headers=h(REPORTER), json={"category_code": "no_gloves", "consequence": 2}
    )
    r = client.post(f"/api/hazards/{hz['id']}/close", headers=h(REPORTER), json={"action": "x"})
    assert r.status_code == 403


def test_validation_errors(client):
    hz = create(client).json()
    assert (
        client.post(
            f"/api/hazards/{hz['id']}/confirm",
            headers=h(REPORTER),
            json={"category_code": "no_gloves", "consequence": 9},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/hazards/{hz['id']}/confirm", headers=h(REPORTER), json={"category_code": "nope", "consequence": 2}
        ).status_code
        == 422
    )
    assert create(client, area="XXX").status_code == 422
    bad = client.post(
        "/api/hazards",
        data={"area_code": "DIG"},
        headers=h(REPORTER),
        files={"photo": ("a.jpg", b"not an image", "image/jpeg")},
    )
    assert bad.status_code == 422


def test_detect_endpoint(client):
    r = client.post(
        "/api/detect", headers=h(REPORTER), files={"photo": ("x_no_gloves.jpg", jpeg_bytes(), "image/jpeg")}
    )
    assert r.status_code == 200 and r.json()["suggestions"][0]["code"] == "no_gloves"


def test_html_pages_render(client):
    assert client.get("/", follow_redirects=False).status_code == 303  # not signed in -> login
    client.post("/login", data={"user_id": SUPERVISOR})
    for path in [
        "/",
        "/report",
        "/hazards",
        "/hazards?status=open&level=High",
        "/queue",
        "/matrix",
        "/areas/DIG",
        "/notifications",
        "/hazards/1",
    ]:
        r = client.get(path)
        assert r.status_code == 200, path


def test_html_report_flow(client):
    client.post("/login", data={"user_id": REPORTER})
    r = client.post(
        "/report",
        data={"area_id": 3},
        files={"photo": ("p_no_eye_protection.jpg", jpeg_bytes(), "image/jpeg")},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"].endswith("/confirm")
    page = client.get(r.headers["location"]).text
    assert "AI suggestion" in page and "Worker without eye / face protection" in page
    r = client.post(
        r.headers["location"],
        data={
            "category_code": "no_eye_protection",
            "consequence": "4",
            "fixed_on_spot": "true",
            "closure_action": "Face shield issued",
        },
    )
    assert r.status_code == 200 and "fixed on the spot" in r.text


def test_vest_not_suggested_where_not_required(client):
    """Digestion (area 3) does not require a hi-vis vest, so a vest detection is not pre-selected."""
    client.post("/login", data={"user_id": REPORTER})
    r = client.post(
        "/report", data={"area_id": 3}, files={"photo": ("p_no_hi_vis_vest.jpg", jpeg_bytes(), "image/jpeg")}
    )
    assert r.status_code == 200 and "not checked here" in r.text and "(AI suggestion)" not in r.text


def test_idempotent_report_creation(client):
    """Microservices lab: a double tap / retry with the same key returns the same report, not a duplicate."""
    hdr = {**h(REPORTER), "Idempotency-Key": "tap-123"}
    files = lambda: {"photo": ("site_no_hard_hat.jpg", jpeg_bytes(), "image/jpeg")}  # noqa: E731
    first = client.post("/api/hazards", data={"area_code": "DIG"}, headers=hdr, files=files())
    again = client.post("/api/hazards", data={"area_code": "DIG"}, headers=hdr, files=files())
    assert first.status_code == 201 and first.json()["replayed"] is False
    assert again.status_code == 200 and again.json()["replayed"] is True and again.json()["id"] == first.json()["id"]
    other = client.post("/api/hazards", data={"area_code": "CAL"}, headers=hdr, files=files())
    assert other.status_code == 409  # same key, different report -> refused
    fresh = client.post(
        "/api/hazards", data={"area_code": "DIG"}, headers={**h(REPORTER), "Idempotency-Key": "tap-124"}, files=files()
    )
    assert fresh.status_code == 201 and fresh.json()["id"] != first.json()["id"]


def test_html_double_submit_returns_same_draft(client):
    client.post("/login", data={"user_id": REPORTER})
    form = client.get("/report").text
    key = form.split('name="idem_key" value="')[1].split('"')[0]
    send = lambda: client.post(
        "/report",
        data={"area_id": 3, "idem_key": key},
        follow_redirects=False,  # noqa: E731
        files={"photo": ("p_no_gloves.jpg", jpeg_bytes(), "image/jpeg")},
    )
    a, b = send(), send()
    assert a.headers["location"] == b.headers["location"]


def test_monitoring_and_metrics(client):
    client.post("/login", data={"user_id": SUPERVISOR})
    assert client.get("/monitoring").status_code == 200
    m = client.get("/api/monitoring").json()
    assert m["reports"] > 0 and {c["name"] for c in m["checks"]} == {
        "AI latency p95",
        "AI error rate",
        "Reporter acceptance",
    }
    text = client.get("/metrics").text
    assert (
        "shms_http_requests_total" in text
        and 'shms_hazards{status="open"}' in text
        and "shms_ai_acceptance_ratio" in text
    )
