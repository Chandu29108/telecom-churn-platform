def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_register_then_me(client):
    res = client.post("/api/auth/register", json={
        "email": "chandu@acmetelecom.com",
        "password": "testpassword123",
        "full_name": "Chandu",
        "organization_name": "Acme Telecom",
    })
    assert res.status_code == 201
    token = res.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "chandu@acmetelecom.com"
    assert body["role"] == "owner"  # first user for a new org name


def test_second_user_same_org_name_without_invite_is_rejected(client):
    """Regression test for the tenant-isolation bug this replaces: typing
    an existing org's name must NOT be enough to join it."""
    client.post("/api/auth/register", json={
        "email": "owner@acme.com", "password": "testpassword123",
        "full_name": "Owner", "organization_name": "Acme Telecom",
    })
    res = client.post("/api/auth/register", json={
        "email": "intruder@evil.com", "password": "testpassword123",
        "full_name": "Intruder", "organization_name": "Acme Telecom",
    })
    assert res.status_code == 409


def test_invite_flow_joins_correct_org_as_member(client):
    owner_res = client.post("/api/auth/register", json={
        "email": "owner@acme.com", "password": "testpassword123",
        "full_name": "Owner", "organization_name": "Acme Telecom",
    })
    owner_headers = {"Authorization": f"Bearer {owner_res.json()['access_token']}"}
    owner_org_id = client.get("/api/auth/me", headers=owner_headers).json()["org_id"]

    invite_res = client.post("/api/auth/invites", json={}, headers=owner_headers)
    assert invite_res.status_code == 201
    invite_token = invite_res.json()["token"]

    join_res = client.post("/api/auth/register", json={
        "email": "teammate@acme.com", "password": "testpassword123",
        "full_name": "Teammate", "organization_name": "Acme Telecom",
        "invite_token": invite_token,
    })
    assert join_res.status_code == 201
    teammate_headers = {"Authorization": f"Bearer {join_res.json()['access_token']}"}
    teammate = client.get("/api/auth/me", headers=teammate_headers).json()
    assert teammate["role"] == "member"
    assert teammate["org_id"] == owner_org_id


def test_invite_token_is_single_use(client):
    owner_res = client.post("/api/auth/register", json={
        "email": "owner2@acme.com", "password": "testpassword123",
        "full_name": "Owner", "organization_name": "Acme Two",
    })
    owner_headers = {"Authorization": f"Bearer {owner_res.json()['access_token']}"}
    token = client.post("/api/auth/invites", json={}, headers=owner_headers).json()["token"]

    first = client.post("/api/auth/register", json={
        "email": "first@acme2.com", "password": "testpassword123",
        "full_name": "First", "organization_name": "Acme Two", "invite_token": token,
    })
    assert first.status_code == 201

    second = client.post("/api/auth/register", json={
        "email": "second@acme2.com", "password": "testpassword123",
        "full_name": "Second", "organization_name": "Acme Two", "invite_token": token,
    })
    assert second.status_code == 400


def test_invite_always_joins_the_inviting_org_regardless_of_name_field(client):
    """The invite token identifies its org directly (org_id on the Invite
    row) — organization_name in the payload is no longer consulted at all
    once an invite_token is present, so submitting a mismatched name
    alongside a real token just joins the token's real org rather than
    being rejected. The actual security property (you can't join an org
    you don't have a valid invite for) is covered by the invite-validity
    checks themselves, not by name-matching."""
    owner_a = client.post("/api/auth/register", json={
        "email": "ownera@a.com", "password": "testpassword123",
        "full_name": "Owner A", "organization_name": "Org A",
    })
    token_a = client.post(
        "/api/auth/invites", json={},
        headers={"Authorization": f"Bearer {owner_a.json()['access_token']}"},
    ).json()["token"]

    client.post("/api/auth/register", json={
        "email": "ownerb@b.com", "password": "testpassword123",
        "full_name": "Owner B", "organization_name": "Org B",
    })

    res = client.post("/api/auth/register", json={
        "email": "sneaky@b.com", "password": "testpassword123",
        "full_name": "Sneaky", "organization_name": "Org B", "invite_token": token_a,
    })
    assert res.status_code == 201
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {res.json()['access_token']}"}).json()
    assert me["organization_name"] == "Org A"  # joined the TOKEN's org, not the name field's org


def test_invite_with_invalid_token_is_rejected(client):
    client.post("/api/auth/register", json={
        "email": "ownerc@c.com", "password": "testpassword123",
        "full_name": "Owner C", "organization_name": "Org C",
    })
    res = client.post("/api/auth/register", json={
        "email": "sneaky2@c.com", "password": "testpassword123",
        "full_name": "Sneaky", "organization_name": "Org C", "invite_token": "not-a-real-token",
    })
    assert res.status_code == 400


def test_non_owner_cannot_create_invite(client):
    owner_res = client.post("/api/auth/register", json={
        "email": "owner3@acme.com", "password": "testpassword123",
        "full_name": "Owner", "organization_name": "Acme Three",
    })
    owner_headers = {"Authorization": f"Bearer {owner_res.json()['access_token']}"}
    token = client.post("/api/auth/invites", json={}, headers=owner_headers).json()["token"]

    member_res = client.post("/api/auth/register", json={
        "email": "member@acme3.com", "password": "testpassword123",
        "full_name": "Member", "organization_name": "Acme Three", "invite_token": token,
    })
    member_headers = {"Authorization": f"Bearer {member_res.json()['access_token']}"}

    res = client.post("/api/auth/invites", json={}, headers=member_headers)
    assert res.status_code == 403


def test_duplicate_email_rejected(client):
    payload = {
        "email": "dup@acme.com", "password": "testpassword123",
        "full_name": "Dup", "organization_name": "Acme Telecom",
    }
    first = client.post("/api/auth/register", json=payload)
    assert first.status_code == 201
    second = client.post("/api/auth/register", json=payload)
    assert second.status_code == 400


def test_login_with_wrong_password_rejected(client):
    client.post("/api/auth/register", json={
        "email": "loginuser@acme.com", "password": "correctpassword",
        "full_name": "Login User", "organization_name": "Acme Telecom",
    })
    res = client.post("/api/auth/login", data={
        "username": "loginuser@acme.com", "password": "wrongpassword",
    })
    assert res.status_code == 401


def test_protected_route_without_token_returns_401(client):
    res = client.get("/api/analysis/runs")
    assert res.status_code == 401


def test_protected_route_with_garbage_token_returns_401(client):
    res = client.get("/api/analysis/runs", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401
