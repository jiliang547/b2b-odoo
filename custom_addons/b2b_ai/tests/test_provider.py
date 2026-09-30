import json
from unittest.mock import patch

import requests
from odoo.exceptions import UserError, ValidationError, AccessError
from odoo.tests import TransactionCase, tagged
from odoo.addons.mail.tests.common import mail_new_test_user
from ..models.provider import validate_url


@tagged('post_install', '-at_install')
class TestThirdPartyProvider(TransactionCase):
    def setUp(self):
        super().setUp()
        self.provider = self.env['b2b.ai.provider']
        self.config = {'url': 'https://api.example.com/v1', 'key': 'test-secret',
                       'model': 'vendor/model-1', 'format': 'json_schema'}
        self.schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
                       'required': ['ok'], 'additionalProperties': False}

    def test_url_validation(self):
        for url in ['http://api.example.com', 'https://localhost', 'https://127.0.0.1',
                    'https://169.254.169.254', 'https://[::1]', 'https://user:secret@example.com',
                    'https://example.com?key=secret', 'https://example.com/v1/chat/completions',
                    'https://example.com:8080']:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                validate_url(url)
        self.assertEqual(validate_url('https://api.example.com/v1/'), self.config['url'])
        with patch('odoo.addons.b2b_ai.models.provider.socket.getaddrinfo',
                   return_value=[(2, 1, 6, '', ('10.0.0.1', 443))]), self.assertRaises(ValidationError):
            validate_url(self.config['url'], resolve=True)

    def test_valid_chat_completion_and_request_bounds(self):
        for mode in ('json_schema', 'json_object'):
            with patch('odoo.addons.b2b_ai.models.provider.validate_url', return_value=self.config['url']), \
                 patch('odoo.addons.b2b_ai.models.provider.requests.post') as post:
                response = post.return_value.__enter__.return_value
                response.status_code = 200
                response.iter_content.return_value = [json.dumps({'choices': [{
                    'finish_reason': 'stop', 'message': {'content': '{"ok": true}'}}]}).encode()]
                self.assertEqual(self.provider._complete(dict(self.config, format=mode), 'Policy', {}, self.schema), {'ok': True})
                args, kwargs = post.call_args
                self.assertEqual(args[0], self.config['url'] + '/chat/completions')
                self.assertFalse(kwargs['allow_redirects'])
                self.assertFalse(kwargs['json']['stream'])
                self.assertEqual(kwargs['json']['model'], 'vendor/model-1')
                self.assertEqual(kwargs['json']['response_format']['type'], mode)
                self.assertEqual(kwargs['json']['max_tokens'], 1600)
                self.assertNotIn('tools', kwargs['json'])

    def test_error_does_not_expose_key_or_retry(self):
        with patch('odoo.addons.b2b_ai.models.provider.validate_url', return_value=self.config['url']), \
             patch('odoo.addons.b2b_ai.models.provider.requests.post',
                   side_effect=requests.ConnectionError('test-secret private provider payload')) as post:
            with self.assertRaises(UserError) as error:
                self.provider._complete(self.config, 'Policy', {}, self.schema)
            self.assertNotIn('test-secret', str(error.exception))
            self.assertEqual(post.call_count, 1)

    def test_truncated_response_rejected(self):
        with patch('odoo.addons.b2b_ai.models.provider.validate_url', return_value=self.config['url']), \
             patch('odoo.addons.b2b_ai.models.provider.requests.post') as post:
            response = post.return_value.__enter__.return_value
            response.status_code = 200
            response.iter_content.return_value = [json.dumps({'choices': [{
                'finish_reason': 'length', 'message': {'content': '{"ok": true}'}}]}).encode()]
            with self.assertRaises(UserError):
                self.provider._complete(self.config, 'Policy', {}, self.schema)

    def test_routing_and_native_key_not_required_for_chat(self):
        params = self.env['ir.config_parameter'].sudo()
        for key, value in dict(self.config, enabled=True).items():
            params.set_param('b2b_ai.third_party_' + key, value)
        params.set_param('ai.openai_key', False)
        website = self.env['website'].search([], limit=1)
        website.write({'b2b_ai_enabled': True, 'b2b_ai_environment_token': website._b2b_ai_environment_fingerprint()})
        self.assertEqual(website._b2b_ai_ready(), 'ready')
        with patch.object(type(self.provider), '_complete', return_value={'ok': True}) as complete:
            result = self.env['b2b.ai.service']._json_call(website.b2b_ai_agent_id, 'Policy', {}, self.schema)
            self.assertEqual(result, {'ok': True})
            complete.assert_called_once()
        website.b2b_ai_environment_token = False
        with patch('odoo.addons.b2b_ai.models.configuration.os.getenv', return_value='staging'):
            self.assertEqual(website._b2b_ai_ready(), 'test_calls_disabled')

    def test_non_admin_cannot_test_or_read_key(self):
        user = mail_new_test_user(self.env, login='third-party-portal', groups='base.group_portal')
        settings = self.env['res.config.settings'].create({})
        with self.assertRaises(AccessError):
            settings.with_user(user).action_b2b_ai_test_provider()
        with self.assertRaises(AccessError):
            settings.with_user(user).read(['b2b_ai_third_party_key'])
        with self.assertRaises(AccessError):
            settings.with_user(user).read(['b2b_ai_embedding_key'])

    def _embedding_settings(self, **values):
        return self.env['res.config.settings'].with_user(self.env.ref('base.user_admin')).create({
            'b2b_ai_embedding_configured': True,
            'b2b_ai_embedding_url': 'https://api.example.com/v1',
            'b2b_ai_embedding_model': 'example-embedding',
            'b2b_ai_embedding_key': 'test-embedding-secret',
            'b2b_ai_embedding_dimensions': 1536,
            **values,
        })

    def test_embedding_configuration_persists_without_calls(self):
        settings = self._embedding_settings()
        with patch('odoo.addons.b2b_ai.models.provider.requests.post',
                   side_effect=AssertionError('Saving must not call a provider')):
            settings.set_values()
        values = self.env['res.config.settings'].with_user(self.env.ref('base.user_admin')).default_get([
            'b2b_ai_embedding_model', 'b2b_ai_embedding_key',
            'b2b_ai_embedding_dimensions', 'b2b_ai_embedding_configured'])
        self.assertEqual(values['b2b_ai_embedding_model'], 'example-embedding')
        self.assertEqual(values['b2b_ai_embedding_key'], 'test-embedding-secret')
        self.assertEqual(values['b2b_ai_embedding_dimensions'], 1536)
        self.assertTrue(values['b2b_ai_embedding_configured'])
        self.assertFalse(self.provider._enabled())

    def test_embedding_key_reuse_and_dimension_validation(self):
        settings = self._embedding_settings(b2b_ai_embedding_key=False,
            b2b_ai_embedding_reuse_chat_key=True)
        with self.assertRaises(ValidationError):
            settings._b2b_validate_embedding_configuration()
        settings.b2b_ai_third_party_key = 'test-chat-key'
        settings._b2b_validate_embedding_configuration()
        settings.b2b_ai_embedding_dimensions = 1024
        with self.assertRaises(ValidationError):
            settings._b2b_validate_embedding_configuration()
        settings.b2b_ai_embedding_dimensions = 1536
        settings.b2b_ai_embedding_url = 'https://api.example.com/v1/embeddings'
        with self.assertRaises(ValidationError):
            settings._b2b_validate_embedding_configuration()
