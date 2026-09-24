"""Admin-configured Chat Completions transport for the website assistant only."""
import ipaddress
import json
import socket
from urllib.parse import urlsplit

import requests

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


def validate_url(value, resolve=False):
    value = (value or '').strip().rstrip('/')
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.port not in (None, 443)
                or any(c.isspace() for c in value)
                or parsed.path.endswith(('/chat/completions', '/responses', '/embeddings'))):
            raise ValueError()
        host = parsed.hostname
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            raise ValueError()
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal and not literal.is_global:
            raise ValueError()
        if resolve:
            addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
                raise ValueError()
    except (ValueError, OSError):
        raise ValidationError('Use a public HTTPS API base URL on port 443, without credentials, query parameters or an endpoint suffix such as /chat/completions or /embeddings.') from None
    return value


class Provider(models.AbstractModel):
    _name = 'b2b.ai.provider'
    _description = 'Partner Hub Third-party AI Transport'

    def _configuration(self):
        params = self.env['ir.config_parameter'].sudo()
        return {key: params.get_param('b2b_ai.third_party_' + key) for key in
                ('enabled', 'url', 'key', 'model', 'format')}

    def _enabled(self):
        return self._configuration()['enabled'] in ('True', '1', True)

    def _complete(self, config, instruction, payload, schema):
        url = validate_url(config['url'], resolve=True)
        key, model = config.get('key'), (config.get('model') or '').strip()
        if not key or key == 'False' or not model or len(model) > 200:
            raise UserError(_('Configure the third-party API key and model name first.'))
        mode = config.get('format') or 'json_schema'
        if mode not in ('json_schema', 'json_object'):
            raise UserError(_('Select a supported JSON output mode.'))
        body = {'model': model, 'stream': False, 'max_tokens': 1600,
                'messages': [{'role': 'system', 'content': instruction + '\nReturn JSON matching this schema:\n' + json.dumps(schema)},
                             {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
                'response_format': {'type': mode}}
        if mode == 'json_schema':
            body['response_format']['json_schema'] = {'name': 'partner_hub_response', 'strict': True, 'schema': schema}
        # No retries or redirects: neither duplicate billing nor forwarding keys.
        try:
            with requests.post(url + '/chat/completions', json=body,
                    headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
                    timeout=(5, 20), allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    raise UserError(_('Third-party AI returned HTTP %(status)s. Check the URL, key, model and JSON output support.', status=response.status_code))
                raw = bytearray()
                for chunk in response.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw) > 1_000_000:
                        raise ValueError()
                result = json.loads(raw)
            choices = result['choices']
            if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
                raise ValueError()
            message = choices[0]['message']
            if message.get('tool_calls') or message.get('function_call') or message.get('refusal'):
                raise ValueError()
            answer = json.loads(message['content'])
            if not isinstance(answer, dict):
                raise ValueError()
            return answer
        except requests.RequestException:
            raise UserError(_('Third-party AI connection failed or timed out. No automatic retry was made.')) from None
        except (ValueError, KeyError, TypeError, IndexError):
            raise UserError(_('The model did not return a complete JSON answer. Check model compatibility and JSON output mode.')) from None


class Settings(models.TransientModel):
    _inherit = 'res.config.settings'

    b2b_ai_third_party_enabled = fields.Boolean(string='Use a third-party model for Partner Hub', config_parameter='b2b_ai.third_party_enabled', groups='base.group_system')
    b2b_ai_third_party_url = fields.Char(string='API Base URL', config_parameter='b2b_ai.third_party_url', groups='base.group_system')
    b2b_ai_third_party_key = fields.Char(string='API Key', config_parameter='b2b_ai.third_party_key', groups='base.group_system', copy=False)
    b2b_ai_third_party_model = fields.Char(string='Model Name', config_parameter='b2b_ai.third_party_model', groups='base.group_system')
    b2b_ai_third_party_format = fields.Selection([('json_schema', 'Strict JSON Schema (recommended)'),
        ('json_object', 'JSON Object (compatibility mode)')], default='json_schema', string='JSON Output Mode',
        config_parameter='b2b_ai.third_party_format', groups='base.group_system')

    b2b_ai_embedding_configured = fields.Boolean(string='Prepare third-party embedding configuration',
        config_parameter='b2b_ai.embedding_configured', groups='base.group_system')
    b2b_ai_embedding_url = fields.Char(string='Embedding API Base URL',
        config_parameter='b2b_ai.embedding_url', groups='base.group_system')
    b2b_ai_embedding_model = fields.Char(string='Embedding Model Name',
        config_parameter='b2b_ai.embedding_model', groups='base.group_system')
    b2b_ai_embedding_reuse_chat_key = fields.Boolean(string='Use the third-party chat API key',
        config_parameter='b2b_ai.embedding_reuse_chat_key', groups='base.group_system')
    b2b_ai_embedding_key = fields.Char(string='Embedding API Key', copy=False,
        config_parameter='b2b_ai.embedding_key', groups='base.group_system')
    b2b_ai_embedding_dimensions = fields.Integer(string='Target Vector Dimensions', default=1536,
        config_parameter='b2b_ai.embedding_dimensions', groups='base.group_system')
    b2b_ai_embedding_send_dimensions = fields.Boolean(string='Send dimensions parameter',
        default=True, config_parameter='b2b_ai.embedding_send_dimensions', groups='base.group_system',
        help='Disable if the provider rejects dimensions and its model already returns 1536 dimensions.')

    def _b2b_validate_embedding_configuration(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only Settings administrators can configure AI providers.'))
        validate_url(self.b2b_ai_embedding_url)
        if not (self.b2b_ai_embedding_model or '').strip() or len(self.b2b_ai_embedding_model) > 200:
            raise ValidationError(_('Enter the exact embedding model name.'))
        if self.b2b_ai_embedding_dimensions != 1536:
            raise ValidationError(_('Native vector storage currently requires 1536 dimensions. Choose a model that supports 1536-dimensional output; other dimensions require a separate storage migration.'))
        key = self.b2b_ai_third_party_key if self.b2b_ai_embedding_reuse_chat_key else self.b2b_ai_embedding_key
        if not key or key == 'False':
            raise ValidationError(_('Enter an embedding API key, or configure the third-party chat key before choosing to reuse it.'))

    def _b2b_third_party_values(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only Settings administrators can configure AI providers.'))
        config = {'url': self.b2b_ai_third_party_url, 'key': self.b2b_ai_third_party_key,
                  'model': self.b2b_ai_third_party_model, 'format': self.b2b_ai_third_party_format}
        validate_url(config['url'])
        if not config['key'] or not config['model'] or len(config['model']) > 200:
            raise ValidationError(_('Enter the API key and exact model name.'))
        return config

    def set_values(self):
        params = self.env['ir.config_parameter'].sudo()
        previous_key = params.get_param('b2b_ai.third_party_key')
        if self.b2b_ai_third_party_enabled:
            self._b2b_third_party_values()
        if self.b2b_ai_embedding_configured:
            self._b2b_validate_embedding_configuration()
        result = super().set_values()
        if (self.b2b_ai_third_party_enabled and self.b2b_ai_third_party_key
                and self.b2b_ai_third_party_key != previous_key):
            self.env['website'].search([]).action_b2b_ai_authorize_environment()
        return result

    def action_b2b_ai_test_provider(self):
        config = self._b2b_third_party_values()
        answer = self.env['b2b.ai.provider']._complete(config,
            'Return the requested JSON object only.', {'instruction': 'Return {"ok": true}.'},
            {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'], 'additionalProperties': False})
        if answer != {'ok': True}:
            raise UserError(_('The provider responded, but the JSON compatibility test failed.'))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'title': _('Connection successful'),
            'message': _('The model returned valid JSON. Save settings to use this provider.'), 'sticky': False}}
