"""Synthetic query fixtures, NOT observed live DATAFAST contracts."""

from decimal import Decimal
from typing import Any
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from gateways.services import DatafastClient


@override_settings(
  DATAFAST_ENVIRONMENT='phase2',
  DATAFAST_BASE_URL='https://eu-test.oppwa.com/v1/',
  DATAFAST_AUTH_TOKEN='test-token',
  DATAFAST_ENTITY_ID='test-entity',
  DATAFAST_TEST_MODE='EXTERNAL',
)
class QueryTests(SimpleTestCase):
  def test_authenticated_get_endpoints_and_decimal_decoder(self):
    response = Mock(status_code=200)
    response.json.return_value = {'payments': []}
    with (
      patch('gateways.services.requests.get', return_value=response) as get,
      patch('gateways.services.requests.post') as post,
    ):
      client = DatafastClient()
      client.query_by_provider_id('provider-1')
      self.assertEqual(get.call_args.args, ('https://eu-test.oppwa.com/v1/query/provider-1',))
      self.assertEqual(get.call_args.kwargs['params'], {'entityId': 'test-entity'})
      client.query_by_merchant_id('merchant &/?=1')
      self.assertEqual(get.call_args.args, ('https://eu-test.oppwa.com/v1/query',))
      self.assertEqual(get.call_args.kwargs['params']['merchantTransactionId'], 'merchant &/?=1')
      self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer test-token')
      self.assertEqual(get.call_args.kwargs['timeout'], 10)
      self.assertIs(get.call_args.kwargs['verify'], True)
      self.assertIs(get.call_args.kwargs['allow_redirects'], False)
      response.json.assert_called_with(parse_float=Decimal)
      post.assert_not_called()

  @override_settings(
    DATAFAST_ENVIRONMENT='production',
    DJANGO_ENV='production',
    STRICT_PROFILE=True,
    DEBUG=False,
    DATAFAST_ALLOW_LOCALHOST=False,
    DATAFAST_BASE_URL='https://eu-prod.oppwa.com/v1/',
    DATAFAST_AUTH_TOKEN='production-token',
    DATAFAST_ENTITY_ID='production-entity',
    DATAFAST_PHASE1_AUTH_TOKEN='phase1-decoy-token',
    DATAFAST_PHASE1_ENTITY_ID='phase1-decoy-entity',
    DATAFAST_TEST_MODE='',
  )
  def test_production_queries_use_canonical_endpoints_and_production_credentials(self):
    response = Mock(status_code=200)
    response.json.return_value = {'payments': []}
    with (
      patch('gateways.services.requests.get', return_value=response) as get,
      patch('gateways.services.requests.post') as post,
    ):
      client = DatafastClient()
      self.assertEqual(client.environment, 'production')
      self.assertEqual(client.test_mode, '')
      cases = (
        (client.query_by_provider_id, 'provider-1', '/provider-1', {'entityId': 'production-entity'}),
        (
          client.query_by_merchant_id,
          'merchant &/?=1',
          '',
          {
            'entityId': 'production-entity',
            'merchantTransactionId': 'merchant &/?=1',
          },
        ),
      )
      for query, identity, suffix, params in cases:
        with self.subTest(endpoint=suffix):
          get.reset_mock()
          self.assertEqual(query(identity), {'payments': []})
          get.assert_called_once_with(
            'https://eu-prod.oppwa.com/v1/query' + suffix,
            params=params,
            headers={
              'Authorization': 'Bearer production-token',
              'Content-Type': 'application/x-www-form-urlencoded',
            },
            timeout=10,
            allow_redirects=False,
            verify=True,
          )
          self.assertNotIn('testMode', get.call_args.kwargs['params'])
      response.json.assert_called_with(parse_float=Decimal)
      post.assert_not_called()

  def test_phase1_query_uses_its_own_endpoint_and_credentials(self):
    response = Mock(status_code=200)
    response.json.return_value = {'payments': []}
    with (
      override_settings(
        DATAFAST_ENVIRONMENT='phase1',
        DATAFAST_BASE_URL='https://test.oppwa.com/v1/',
        DATAFAST_TEST_MODE='',
        DATAFAST_PHASE1_ENTITY_ID='phase1-entity',
        DATAFAST_PHASE1_AUTH_TOKEN='phase1-token',
        DJANGO_ENV='development',
        STRICT_PROFILE=False,
        DEBUG=True,
      ),
      patch('gateways.services.requests.get', return_value=response) as get,
    ):
      DatafastClient().query_by_provider_id('provider-1')
      self.assertEqual(get.call_args.args, ('https://test.oppwa.com/v1/query/provider-1',))
      self.assertEqual(get.call_args.kwargs['params'], {'entityId': 'phase1-entity'})
      self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer phase1-token')
      get.reset_mock()
      for changes in ({'DATAFAST_TEST_MODE': 'EXTERNAL'}, {'DATAFAST_ENVIRONMENT': 'invalid'}):
        with self.subTest(changes=changes), override_settings(**changes), self.assertRaises(ValueError):
          DatafastClient().query_by_provider_id('provider-1')
      get.assert_not_called()

  def test_invalid_id_and_configuration_never_query(self):
    identities: list[Any] = ['', '../id', 'https://other', 'id?secret', None]
    with patch('gateways.services.requests.get') as get:
      for identity in identities:
        self.assertEqual(DatafastClient().query_by_provider_id(identity), {'outcome': 'UNKNOWN'})
      for base in (
        'http://host/v1/',
        'https://user:password@host/',
        'https://host/arbitrary',
        'https://host/?x=1',
        'https://host/#fragment',
      ):
        with self.subTest(base=base), override_settings(DATAFAST_BASE_URL=base), self.assertRaises(ValueError):
          DatafastClient().query_by_merchant_id('merchant')
      get.assert_not_called()

  def test_malformed_json_is_unknown_and_bearer_is_not_duplicated(self):
    response = Mock(status_code=200)
    response.json.side_effect = ValueError('malformed private response')
    with (
      override_settings(DATAFAST_AUTH_TOKEN='Bearer test-token'),
      patch('gateways.services.requests.get', return_value=response) as get,
    ):
      self.assertEqual(DatafastClient().query_by_provider_id('id'), {'outcome': 'UNKNOWN'})
      self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer test-token')
      get.assert_called_once()

  def test_unavailability_and_redirects_are_unknown_without_retries(self):
    for error in (requests.Timeout(), requests.ConnectionError(), ValueError('private')):
      with patch('gateways.services.requests.get', side_effect=error) as get:
        self.assertEqual(DatafastClient().query_by_provider_id('id'), {'outcome': 'UNKNOWN'})
        get.assert_called_once()
    for status in (302, 500):
      with patch('gateways.services.requests.get', return_value=Mock(status_code=status)) as get:
        self.assertEqual(DatafastClient().query_by_provider_id('id'), {'outcome': 'UNKNOWN'})
        get.assert_called_once()
