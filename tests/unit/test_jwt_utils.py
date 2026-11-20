import pytest
import time

from okta_jwt_verifier.jwt_utils import JWTUtils
from okta_jwt_verifier.exceptions import JWTValidationException


def test_verify_expiration(mocker):
    # verify token is not expired
    headers = {'alg': 'RS256', 'kid': 'test_kid'}
    issuer = 'https://test_issuer.com'
    iss_time = time.time()
    claims = {'ver': 1,
              'jti': 'test_jti_str',
              'iss': issuer,
              'iat': iss_time,
              'exp': iss_time+300,
              'uid': 'test_uid',
              'scp': ['openid'],
              'sub': 'test_jwt@okta.com'}
    signing_input = 'test_signing_input'
    signature = 'test_signature'

    mock_parse_token = lambda token: (headers, claims, signing_input, signature)
    mocker.patch('okta_jwt_verifier.jwt_utils.JWTUtils.parse_token', mock_parse_token)

    JWTUtils.verify_expiration('test_token')

    # verify token is expired
    claims = {'ver': 1,
              'jti': 'test_jti_str',
              'iss': issuer,
              'iat': iss_time,
              'exp': iss_time-300,
              'uid': 'test_uid',
              'scp': ['openid'],
              'sub': 'test_jwt@okta.com'}
    with pytest.raises(JWTValidationException):
        JWTUtils.verify_expiration('test_token')


def test_rs256_verification_supported_at_runtime():
    """RS256 (what Okta signs with) needs PyJWT's crypto backend at runtime."""
    import jwt
    from jwt.algorithms import has_crypto
    assert has_crypto, "cryptography is missing: PyJWT cannot verify RS256 tokens"
    assert 'RS256' in jwt.algorithms.get_default_algorithms()


def test_verify_signature_rs256_end_to_end():
    """Sign a token with a local RSA key and verify it through JWTUtils, no network."""
    import json
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({'kid': 'test_kid', 'alg': 'RS256'})
    token = jwt.encode({'sub': 'test'}, private_key, algorithm='RS256', headers={'kid': 'test_kid'})

    JWTUtils.verify_signature(token, jwk)

    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bad_token = jwt.encode({'sub': 'test'}, other_key, algorithm='RS256', headers={'kid': 'test_kid'})
    with pytest.raises(jwt.exceptions.InvalidSignatureError):
        JWTUtils.verify_signature(bad_token, jwk)
