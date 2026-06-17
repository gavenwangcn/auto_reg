import unittest
from unittest import mock

from core.skymail_auth import SkyMailAuthError, fetch_skymail_token, resolve_skymail_token


class SkyMailAuthTests(unittest.TestCase):
    @mock.patch("core.skymail_auth.requests.post")
    def test_fetch_skymail_token_success(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "code": 200,
            "message": "success",
            "data": {"token": "token-abc"},
        }

        token = fetch_skymail_token(
            "https://mail.example.com",
            "admin@example.com",
            "secret",
        )

        self.assertEqual(token, "token-abc")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://mail.example.com/api/public/genToken")
        self.assertEqual(
            kwargs["json"],
            {"email": "admin@example.com", "password": "secret"},
        )

    @mock.patch("core.skymail_auth.requests.post")
    def test_fetch_skymail_token_api_error(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "code": 401,
            "message": "bad credentials",
        }

        with self.assertRaises(SkyMailAuthError):
            fetch_skymail_token(
                "https://mail.example.com",
                "admin@example.com",
                "wrong",
            )

    def test_resolve_skymail_token_prefers_credentials(self):
        with mock.patch(
            "core.skymail_auth.fetch_skymail_token",
            return_value="fresh-token",
        ) as mock_fetch:
            token = resolve_skymail_token(
                "https://mail.example.com",
                auth_token="old-token",
                email="admin@example.com",
                password="secret",
            )

        self.assertEqual(token, "fresh-token")
        mock_fetch.assert_called_once()

    def test_resolve_skymail_token_uses_saved_token(self):
        token = resolve_skymail_token(
            "https://mail.example.com",
            auth_token="saved-token",
        )
        self.assertEqual(token, "saved-token")


if __name__ == "__main__":
    unittest.main()
