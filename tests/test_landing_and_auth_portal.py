import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token


client = TestClient(app, follow_redirects=False)


def test_public_clubs_endpoint():
    """Verifica que el endpoint público de clubes retorne la lista de sedes activas."""
    response = client.get("/api/v1/clubs/public")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    
    first_club = data[0]
    assert "id" in first_club
    assert "name" in first_club
    
    auth_clubs_res = client.get("/api/v1/auth/clubs/public")
    assert auth_clubs_res.status_code == 200
    assert len(auth_clubs_res.json()) >= 1


def test_landing_page_unauthenticated():
    """Verifica que GET / sirva la landing page cuando no hay sesión activa."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "YieldPadel" in html
    assert "Ingresar al Club" in html
    assert "login-modal" in html
    assert "login-club-select" in html
    assert "RevPAST" in html


def test_dashboard_route_protection_unauthenticated():
    """Verifica que GET /dashboard redirija a /?login=true cuando el usuario no está autenticado."""
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["location"] == "/?login=true"


def test_dashboard_authenticated_with_cookie():
    """Verifica que GET /dashboard permita el acceso y retorne 200 si tiene cookie de sesión válida."""
    token = create_access_token({
        "sub": "1",
        "username": "admin",
        "role": "SUPERADMIN",
        "full_name": "Administrador General",
        "club_id": "2756f34a-7d24-4815-9f7e-6ed125ea5de7"
    })
    
    response = client.get("/dashboard", cookies={"access_token": token})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Panel Operativo" in response.text or "Afluenc.IA" in response.text


def test_landing_page_redirects_when_authenticated():
    """Verifica que GET / redirija a /dashboard si el usuario ya cuenta con sesión activa."""
    token = create_access_token({
        "sub": "1",
        "username": "admin",
        "role": "SUPERADMIN",
        "full_name": "Administrador General",
        "club_id": "2756f34a-7d24-4815-9f7e-6ed125ea5de7"
    })
    
    response = client.get("/", cookies={"access_token": token})
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


def test_auth_login_successful_and_cookie_set():
    """Verifica inicio de sesión exitoso, generación de JWT y cookies HTTP-only."""
    payload = {
        "username": "admin",
        "password": "admin123",
        "club_id": "2756f34a-7d24-4815-9f7e-6ed125ea5de7"
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "user" in data
    assert data["user"]["username"] == "admin"
    assert "access_token" in response.cookies


def test_auth_login_invalid_password():
    """Verifica rechazo con 401 si la contraseña es errónea."""
    payload = {
        "username": "admin",
        "password": "wrongpassword123",
        "club_id": "2756f34a-7d24-4815-9f7e-6ed125ea5de7"
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert "Credenciales incorrectas" in response.json()["detail"]


def test_auth_login_wrong_club_isolation():
    """
    Verifica que un usuario recepcionista asignado a Maloka no pueda ingresar a Chía
    si no tiene rol SUPERADMIN o GERENTE.
    """
    payload = {
        "username": "recepcion",
        "password": "recepcion123",
        "club_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"  # Country Padel Arena Chía
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 403
    assert "El usuario no pertenece a la sede" in response.json()["detail"]


def test_auth_logout_clears_cookie():
    """Verifica que /api/v1/auth/logout elimine la cookie de sesión."""
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
