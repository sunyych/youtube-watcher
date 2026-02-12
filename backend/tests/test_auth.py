"""Tests for authentication"""
import pytest
from fastapi.testclient import TestClient


def test_login_success(client: TestClient, test_user):
    """Test successful login"""
    response = client.post(
        "/api/auth/login",
        json={"username": test_user.username, "password": "admin123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_failure(client: TestClient, test_user):
    """Test failed login with wrong password"""
    response = client.post(
        "/api/auth/login",
        json={"username": test_user.username, "password": "wrong_password"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


def test_protected_endpoint_without_auth(client: TestClient):
    """Test accessing protected endpoint without authentication"""
    response = client.get("/api/history")
    assert response.status_code == 403


def test_protected_endpoint_with_auth(authenticated_client: TestClient):
    """Test accessing protected endpoint with authentication"""
    response = authenticated_client.get("/api/history")
    assert response.status_code == 200
