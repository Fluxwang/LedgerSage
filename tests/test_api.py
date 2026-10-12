import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from beanbot.config import Settings
from beanbot.api.app import create_app


def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path / 'data', ledger_root=tmp_path / 'ledgers',
                    jwt_secret='test-secret-that-is-at-least-32-characters', invite_code='test-invite',
                    llm_base_url='http://localhost:9999/v1', llm_api_key='test', llm_model='fixture')


def test_health_and_required_configuration(tmp_path):
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get('/health').json() == {'status': 'ok'}


def test_invite_registration_login_and_identity(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        body = {'username': 'mark', 'password': 'correct-horse', 'invite_code': 'test-invite'}
        registered = client.post('/auth/register', json=body)
        assert registered.status_code == 200
        headers = {'Authorization': f"Bearer {registered.json()['access_token']}"}
        assert client.get('/auth/me', headers=headers).json()['username'] == 'mark'
        assert client.post('/auth/register', json={**body, 'username': 'other'}).status_code == 400
        assert client.post('/auth/login', json={'username': 'mark', 'password': 'wrong-pass'}).status_code == 401
