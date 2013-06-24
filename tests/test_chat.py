# -*- coding: utf-8 -*-
"""
    test_chat

    test the chat system components

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import os
import sys
import json
DIR = os.path.abspath(os.path.normpath(os.path.join(__file__,
    '..', '..', '..', '..', '..', 'trytond')))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))

import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT
from trytond.transaction import Transaction

from nereid.testing import NereidTestCase


class TestChat(NereidTestCase):
    "Test the chat system"

    def setUp(self):
        trytond.tests.test_tryton.install_module('nereid_chat')
        self.country_obj = POOL.get('country.country')
        self.currency_obj = POOL.get('currency.currency')
        self.company_obj = POOL.get('company.company')
        self.nereid_website_obj = POOL.get('nereid.website')
        self.url_map_obj = POOL.get('nereid.url_map')
        self.language_obj = POOL.get('ir.lang')
        self.nereid_user_obj = POOL.get('nereid.user')
        self.chat_obj = POOL.get('nereid.chat')

    def get_template_source(self, name):
        '''
        Return templates
        '''
        self.templates = {
            'localhost/login.jinja':
            '{{ login_form.errors }}{{ get_flashed_messages()|safe }}',
        }
        return self.templates.get(name)

    def setup_defaults(self):
        currency = self.currency_obj.create({
            'name': 'US Dollar',
            'code': 'USD',
            'symbol': '$',
        })
        company = self.company_obj.create({
            'name': 'openlabs',
            'currency': currency,
        })
        guest_user = self.nereid_user_obj.create({
            'name': 'Guest User',
            'display_name': 'Guest User',
            'email': 'guest@openlabs.co.in',
            'password': 'password',
            'company': company,
        })

        # Create website
        url_map_id, = self.url_map_obj.search([], limit=1)
        en_us, = self.language_obj.search([('code', '=', 'en_US')])
        self.nereid_website_obj.create({
            'name': 'localhost',
            'url_map': url_map_id,
            'company': company,
            'application_user': USER,
            'default_language': en_us,
            'guest_user': guest_user,
            'currencies': [('set', [currency])],
        })
        return {
            'company': company,
            'currency': currency,
        }

    def test_0010_get_or_create_room(self):
        """
        Create a room for a 1:1 chat and check if it works
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            data = self.setup_defaults()

            user_1 = self.nereid_user_obj.create({
                'name': 'Name',
                'display_name': 'nome',
                'email': 'user1@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            })
            user_2 = self.nereid_user_obj.create({
                'name': 'Name 2',
                'display_name': 'nome',
                'email': 'user2@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            })

            # Get or create a room.
            room = self.chat_obj.get_or_create_room(user_1, user_2)

            self.assertEqual(
                room,
                self.chat_obj.get_or_create_room(user_1, user_2)
            )
            # Test the lookup the other way around
            self.assertEqual(
                room,
                self.chat_obj.get_or_create_room(user_2, user_1)
            )

    def test_0020_get_or_create_room(self):
        """
        Create a room for a 1:1 chat and check if it works with
        multiple pairs
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            data = self.setup_defaults()

            user_1_1 = self.nereid_user_obj.create({
                'name': 'Name',
                'display_name': 'nome',
                'email': 'user11@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            })
            user_1_2 = self.nereid_user_obj.create({
                'name': 'Name 2',
                'display_name': 'nome',
                'email': 'user12@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            })

            user_2_1 = self.nereid_user_obj.create({
                'name': 'Name',
                'display_name': 'nome',
                'email': 'user21@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            })
            user_2_2 = self.nereid_user_obj.create({
                'name': 'Name 2',
                'display_name': 'nome',
                'email': 'user22@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            })

            # get or create a room
            # 1_1 <-------> 1_2
            # 2_1 <-------> 2_2
            # 1_1 <-------> 2_2
            r_11_12 = self.chat_obj.get_or_create_room(user_1_1, user_1_2)
            r_21_22 = self.chat_obj.get_or_create_room(user_2_1, user_2_2)
            r_11_22 = self.chat_obj.get_or_create_room(user_1_1, user_2_2)

            self.assertEqual(
                r_11_12, self.chat_obj.get_or_create_room(user_1_1, user_1_2)
            )
            self.assertEqual(
                r_21_22, self.chat_obj.get_or_create_room(user_2_1, user_2_2)
            )
            self.assertEqual(
                r_11_22, self.chat_obj.get_or_create_room(user_1_1, user_2_2)
            )

    def test_0030_get_or_create_room(self):
        """
        Check a multi user chat
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            data = self.setup_defaults()

            user_1_1 = self.nereid_user_obj.create({
                'name': 'Name',
                'display_name': 'nome',
                'email': 'user11@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            })
            user_1_2 = self.nereid_user_obj.create({
                'name': 'Name 2',
                'display_name': 'nome',
                'email': 'user12@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            })
            user_1_3 = self.nereid_user_obj.create({
                'name': 'Name 2',
                'display_name': 'nome',
                'email': 'user13@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            })

           # get or create a room
            # 1_1 <--->1_2<----> 1_3
            # 1_1 <-------> 1_2 (1:1 chat)
            # 1_1 <-------> 1_3 (1:1 chat)
            # 1_2 <-------> 1_3 (1:1 chat)
            r_123 = self.chat_obj.get_or_create_room(
                user_1_1, user_1_2, user_1_3
            )
            r_12 = self.chat_obj.get_or_create_room(user_1_1, user_1_2)
            r_13 = self.chat_obj.get_or_create_room(user_1_1, user_1_3)
            r_23 = self.chat_obj.get_or_create_room(user_1_2, user_1_3)

            self.assertEqual(
                r_123,
                self.chat_obj.get_or_create_room(user_1_1, user_1_2, user_1_3)
            )
            self.assertEqual(
                r_12, self.chat_obj.get_or_create_room(user_1_1, user_1_2)
            )
            self.assertEqual(
                r_13, self.chat_obj.get_or_create_room(user_1_1, user_1_3)
            )
            self.assertEqual(
                r_23, self.chat_obj.get_or_create_room(user_1_1, user_1_2)
            )

    def test_0040_post_message(self):
        """
        Check post message
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            data = self.setup_defaults()
            app = self.get_app()

            self.nereid_user_obj.create({
                'name': 'Name',
                'display_name': 'nome',
                'email': 'user1@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            })
            user_2 = self.nereid_user_obj.create({
                'name': 'Name 2',
                'display_name': 'nome',
                'email': 'user2@openlabs.co.in',
                'password': 'password',
                'company': data['company'],
            })
            login_data = {
                'email': 'user1@openlabs.co.in',
                'password': 'password',
            }
            with app.test_client() as c:
                # Login
                rv = c.post('/en_US/login', data=login_data)
                self.assertEqual(rv.status_code, 302)

                # Test posting without thread_id
                rv = c.post(
                    '/en_US/nereid-chat/send-message',
                    data={
                        'message': 'Send Message',
                    }
                )
                self.assertEqual(rv.status_code, 400)

                # Test posting to wrong thread_id
                # This will throw ValueError as logged in user is not a
                # participant of thread.
                rv = c.post(
                    '/en_US/nereid-chat/send-message',
                    data={
                        'message': 'Send Message',
                        'thread_id': '02bf6368-712f-4711-b059-f16ca5642d12',
                    }
                )
                self.assertEqual(rv.status_code, 404)

                # Get session id
                rv = c.post(
                    '/en_US/nereid-chat/start-session',
                    data={
                        'user': user_2,
                    }
                )
                self.assertEqual(rv.status_code, 200)
                response_json = json.loads(rv.data)
                self.assertTrue(response_json['success'])

                # Try posting to correct thread_id
                rv = c.post(
                    '/en_US/nereid-chat/send-message',
                    data={
                        'message': 'Send Message',
                        'thread_id': response_json['thread_id'],
                    }
                )
                self.assertEqual(rv.status_code, 200)
                # Any listener is not there so success will be false
                self.assertTrue(json.loads(rv.data)['success'])


def _suite():
    "Test suite"
    test_suite = unittest.TestSuite()
    test_suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestChat)
    )
    return test_suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(_suite())
