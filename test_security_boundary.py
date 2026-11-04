from src.services.auth import client_ip


def test_forwarded_ip_is_not_trusted():
    from starlette.requests import Request
    request = Request({'type': 'http', 'client': ('127.0.0.1', 123), 'headers': [(b'x-forwarded-for', b'fake')]})
    assert client_ip(request) == '127.0.0.1'
