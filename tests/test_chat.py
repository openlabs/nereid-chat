# -*- coding: utf-8 -*-
"""
    test_chat

    test the chat system components

    :copyright: (c) 2013-2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import os
import sys
import uuid
import json
DIR = os.path.abspath(os.path.normpath(os.path.join(
    __file__, '..', '..', '..', '..', '..', 'trytond')))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))

import unittest
from redis import Redis
import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT
from trytond.transaction import Transaction

from nereid.testing import NereidTestCase


class TestChat(NereidTestCase):
    "Test the chat system"

    def setUp(self):
        trytond.tests.test_tryton.install_module('nereid_chat')
        self.Currency = POOL.get('currency.currency')
        self.Company = POOL.get('company.company')
        self.Website = POOL.get('nereid.website')
        self.UrlMap = POOL.get('nereid.url_map')
        self.Language = POOL.get('ir.lang')
        self.NereidUser = POOL.get('nereid.user')
        self.Chat = POOL.get('nereid.chat')
        self.Party = POOL.get('party.party')
        self.Locale = POOL.get('nereid.website.locale')
        self.templates = {
            'localhost/login.jinja':
            '{{ login_form.errors }}{{ get_flashed_messages()|safe }}',
        }
        Redis().flushdb()

    def setup_defaults(self):
        currency, = self.Currency.create([{
            'name': 'US Dollar',
            'code': 'USD',
            'symbol': '$',
        }])
        company_party, = self.Party.create([{
            'name': 'openlabs'
        }])
        company, = self.Company.create([{
            'party': company_party,
            'currency': currency,
        }])
        guest_party, = self.Party.create([{
            'name': 'Non registered user'
        }])
        guest_user, = self.NereidUser.create([{
            'party': guest_party,
            'display_name': 'Guest User',
            'email': 'guest@openlabs.co.in',
            'company': company,
        }])

        # Create Locale
        en_us, = self.Language.search([('code', '=', 'en_US')])
        locale_en_us, = self.Locale.create([{
            'code': 'en_US',
            'language': en_us,
            'currency': currency,
        }])

        # Create website
        url_map, = self.UrlMap.search([], limit=1)
        self.Website.create([{
            'name': 'localhost',
            'url_map': url_map,
            'company': company,
            'application_user': USER,
            'default_locale': locale_en_us,
            'guest_user': guest_user,
            'currencies': [('set', [currency])],
        }])

        # test party
        test_party, = self.Party.create([{
            'name': 'Registered User'
        }])
        return {
            'company': company,
            'currency': currency,
            'test_party': test_party,
        }

    def test_0010_get_or_create_room(self):
        """
        Create a room for a 1:1 chat and check if it works
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            data = self.setup_defaults()

            user_1, = self.NereidUser.create([{
                'party': data['test_party'],
                'display_name': 'nome',
                'email': 'user1@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            }])
            user_2, = self.NereidUser.create([{
                'party': data['test_party'],
                'display_name': 'nome',
                'email': 'user2@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            }])

            # Get or create a room.
            room = self.Chat.get_or_create_room(user_1.id, user_2.id)

            self.assertEqual(
                room,
                self.Chat.get_or_create_room(user_1.id, user_2.id)
            )
            # Test the lookup the other way around
            self.assertEqual(
                room,
                self.Chat.get_or_create_room(user_2.id, user_1.id)
            )

    def test_0020_get_or_create_room(self):
        """
        Create a room for a 1:1 chat and check if it works with
        multiple pairs
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            data = self.setup_defaults()

            user_1_1, = self.NereidUser.create([{
                'party': data['test_party'],
                'display_name': 'nome',
                'email': 'user11@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            }])
            user_1_2, = self.NereidUser.create([{
                'party': data['test_party'],
                'display_name': 'nome',
                'email': 'user12@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            }])

            user_2_1, = self.NereidUser.create([{
                'party': data['test_party'],
                'display_name': 'nome',
                'email': 'user21@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            }])
            user_2_2, = self.NereidUser.create([{
                'party': data['test_party'],
                'display_name': 'nome',
                'email': 'user22@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            }])

            # get or create a room
            # 1_1 <-------> 1_2
            # 2_1 <-------> 2_2
            # 1_1 <-------> 2_2
            r_11_12 = self.Chat.get_or_create_room(user_1_1, user_1_2)
            r_21_22 = self.Chat.get_or_create_room(user_2_1, user_2_2)
            r_11_22 = self.Chat.get_or_create_room(user_1_1, user_2_2)

            self.assertEqual(
                r_11_12, self.Chat.get_or_create_room(user_1_1, user_1_2)
            )
            self.assertEqual(
                r_21_22, self.Chat.get_or_create_room(user_2_1, user_2_2)
            )
            self.assertEqual(
                r_11_22, self.Chat.get_or_create_room(user_1_1, user_2_2)
            )

    def test_0030_get_or_create_room(self):
        """
        Check a multi user chat
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            data = self.setup_defaults()

            user_1_1, = self.NereidUser.create([{
                'party': data['test_party'],
                'display_name': 'nome',
                'email': 'user11@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            }])
            user_1_2, = self.NereidUser.create([{
                'party': data['test_party'],
                'display_name': 'nome',
                'email': 'user12@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            }])
            user_1_3, = self.NereidUser.create([{
                'party': data['test_party'],
                'display_name': 'nome',
                'email': 'user13@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            }])

            # get or create a room
            # 1_1 <--->1_2<----> 1_3
            # 1_1 <-------> 1_2 (1:1 chat)
            # 1_1 <-------> 1_3 (1:1 chat)
            # 1_2 <-------> 1_3 (1:1 chat)
            r_123 = self.Chat.get_or_create_room(
                user_1_1, user_1_2, user_1_3
            )
            r_12 = self.Chat.get_or_create_room(user_1_1, user_1_2)
            r_13 = self.Chat.get_or_create_room(user_1_1, user_1_3)
            r_23 = self.Chat.get_or_create_room(user_1_2, user_1_3)

            self.assertEqual(
                r_123,
                self.Chat.get_or_create_room(user_1_1, user_1_2, user_1_3)
            )
            self.assertEqual(
                r_12, self.Chat.get_or_create_room(user_1_1, user_1_2)
            )
            self.assertEqual(
                r_13, self.Chat.get_or_create_room(user_1_1, user_1_3)
            )
            self.assertEqual(
                r_23, self.Chat.get_or_create_room(user_1_1, user_1_2)
            )

    def test_0040_post_message(self):
        """
        Check post message
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            data = self.setup_defaults()
            app = self.get_app()

            self.NereidUser.create([{
                'party': data['test_party'],
                'display_name': 'nome',
                'email': 'user1@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            }])
            user_2, = self.NereidUser.create([{
                'party': data['test_party'],
                'display_name': 'nome',
                'email': 'user2@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            }])
            login_data = {
                'email': 'user1@openlabs.co.in',
                'password': 'password',
            }
            with app.test_client() as c:
                # Login
                rv = c.post('/login', data=login_data)
                self.assertEqual(rv.status_code, 302)

                # Test posting without thread_id
                rv = c.post(
                    '/nereid-chat/send-message',
                    data={
                        'message': 'Send Message',
                    }
                )
                self.assertEqual(rv.status_code, 400)

                # Test posting to wrong thread_id
                # This will throw ValueError as logged in user is not a
                # participant of thread.
                rv = c.post(
                    '/nereid-chat/send-message',
                    data={
                        'message': 'Send Message',
                        'thread_id': '02bf6368-712f-4711-b059-f16ca5642d12',
                    }
                )
                self.assertEqual(rv.status_code, 404)

                # Get session id
                rv = c.post(
                    '/nereid-chat/start-session',
                    data={
                        'user': user_2.id,
                    }
                )
                self.assertEqual(rv.status_code, 200)
                response_json = json.loads(rv.data)

                # Try posting to correct thread_id
                rv = c.post(
                    '/nereid-chat/send-message',
                    data={
                        'message': 'Send Message',
                        'thread_id': response_json['thread_id'],
                    }
                )
                self.assertEqual(rv.status_code, 200)

    def test_0050_token_creation(self):
        """
        Test creation of token
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            data = self.setup_defaults()
            app = self.get_app()
            app.redis_client = Redis()

            self.NereidUser.create([{
                'party': data['test_party'],
                'display_name': 'nome',
                'email': 'user1@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            }])
            login_data = {
                'email': 'user1@openlabs.co.in',
                'password': 'password',
            }
            with app.test_client() as c:
                # Login
                rv = c.post('/login', data=login_data)
                self.assertEqual(rv.status_code, 302)

                rv = c.get('/nereid-chat/token')
                self.assertEqual(rv.status_code, 405)

                rv = c.post('/nereid-chat/token')
                self.assertEqual(rv.status_code, 200)

                self.assertTrue('token' in json.loads(rv.data))

    def test_0060_token_event_stream(self):
        """
        Test fetching of stream via token
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            data = self.setup_defaults()
            app = self.get_app()
            app.redis_client = Redis()

            nereid_user, = self.NereidUser.create([{
                'party': data['test_party'],
                'display_name': 'nome',
                'email': 'user1@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            }])
            with app.test_client() as c:
                token = unicode(uuid.uuid4())
                app.redis_client.set('chat:token:%s' % token, nereid_user.id)

                rv = c.get('/nereid-chat/stream/wrong-token')
                self.assertEqual(rv.status_code, 404)

                rv = c.get('/nereid-chat/stream/%s' % token)
                self.assertEqual(rv.status_code, 200)


def _suite():
    "Test suite"
    test_suite = unittest.TestSuite()
    test_suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestChat)
    )
    return test_suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(_suite())
