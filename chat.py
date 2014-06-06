# -*- coding: utf-8 -*-
"""
    chat

    :copyright: (c) 2013-2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from datetime import datetime
import uuid

from gevent import queue
from redis import Redis
import simplejson as json
from flask_wtf import Form
from wtforms import IntegerField, validators
from nereid import request, render_template, jsonify, Response, abort, \
    login_required, route, current_app, current_user
from trytond.model import ModelView, ModelSQL, fields
from trytond.transaction import Transaction
from trytond.config import CONFIG
from trytond.pool import Pool, PoolMeta

__all__ = ['NereidUser', 'NereidChat', 'ChatMember', 'Message']
__metaclass__ = PoolMeta

counter = {'c': 0}


class NewChatForm(Form):
    "New Chat Form"
    user = IntegerField('User', [validators.Required()])


class MessageQueue(object):
    '''
    A simple message queue system that will allow this POC to run
    '''

    def __init__(self):
        self.store = {}

    def get_queue(self, user):
        '''
        Return the queue of the user
        '''
        # Tryton has one python instance for several databases. So namespace
        # the store for each database
        return self.store.setdefault(
            Transaction().cursor.dbname, {}
        ).setdefault(user, queue.Queue())

    def is_user_offline(self, user, threshold=5):
        '''
        Assumes that a user_backlog more than the threshold means the user is
        offline

        :param user: Id of user.
        :param threshold: Maximum Limit of queue.

        :return: True/False if user is offline.
        '''
        return self.user_backlog(user) > threshold

    def user_backlog(self, user):
        '''
        Returns the number of messages waiting for a user to be received
        '''
        return self.get_queue(user).qsize()

    def publish(self, user, data):
        '''
        Push the data to the queue of the user.

        :param user: Id of user.
        :param data: Data to publish on queue.
        '''
        return self.get_queue(user).put(data)

    def listen(self, user, dbname=None):
        '''
        Listen to messages of the user and yield whenever something is there

        :param user: Id of user.
        :param dbname: Optionally specify the dbname, if the transaction
                       context is not available
        '''
        if dbname is not None:
            q = self.store.setdefault(
                dbname, {}).setdefault(user, queue.Queue())
        else:
            q = self.get_queue(user)

        while True:
            try:
                yield q.get(timeout=5)
            except queue.Empty:
                yield '{}'

MQ = MessageQueue()


class NereidUser(ModelSQL, ModelView):
    '''
    Nereid User
    '''
    __name__ = 'nereid.user'

    chat_available = fields.Function(
        fields.Boolean('Available'), 'get_available'
    )

    def get_available(self, name):
        '''
        Looks into the message queue and figures out if the user is available
        or not
        '''
        return not MQ.is_user_offline(self)

    def serialize(self, purpose=None):
        """
        Serialize the sender alone and return a dictionary. This is separated
        so that other modules can easily modify the behavior independent of
        this module.
        """
        return {
            "url": None,
            "objectType": self.__name__,
            "id": self.id,
            "displayName": self.display_name,
        }

    def get_chat_friends(self):
        """
        Returns list of friends of nereid_user. This is separated so that
        other modules can easily modify the behavior independent of this
        modules.
        This is for other modules which implement the functionality to extend.
        Current functionality allows all are chatting friends.

        :return: List of browse records of friends.
        """
        return self.search([('id', '!=', self.id)])

    def publish_message(self, data_message):
        '''
        Publishes message to user's channel/queue
        '''
        return MQ.publish(self.id, data_message)

    def broadcast_presence(self):
        '''
        Publishes presence to all friends.
        '''
        presence_message = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "presence",
            "presence": self.get_presence(),
        }
        friends = self.get_chat_friends()
        for user in friends:
            MQ.publish(user.id, presence_message)

    @classmethod
    @route('/nereid-chat/get-friends')
    @login_required
    def chat_friends(cls):
        """
        GET: Returns the JSON dictionary of all chat friends with their
        presence stanza.
        """
        friends = request.nereid_user.get_chat_friends()
        friends_presence = []
        for friend in friends:
            friends_presence.append(friend.get_presence())
        return jsonify({
            'friends': friends_presence,
        })

    def get_presence(self):
        '''
        Returns the presence status of a nereid_user.
        '''
        return {
            "entity": self.serialize(),
            "show": "chat",
            "status": None,
            'available': self.chat_available,
        }

    def can_chat(self, other):
        '''
        Return True if the user can talk to the other user.

        This is for other modules which implement the functionality to extend.
        Current functionality allows to talk to user's chat friends only.

        :param other: Browse record of nereid_user, to check permission with.
        '''
        return other in self.get_chat_friends()


class NereidChat(ModelSQL, ModelView):
    '''
    Nereid Chat
    '''
    __name__ = 'nereid.chat'

    thread = fields.Char('Thread ID')
    members = fields.One2Many(
        'nereid.chat.member', 'chat', 'Members',
    )

    #: This POC implementation uses the database backend to store messages.
    #: This should not be used in production as this may cause too many writes
    #: to your transactional database. Instead use something like redis
    messages = fields.One2Many(
        'nereid.chat.message', 'chat', 'Messages'
    )

    @classmethod
    def __setup__(cls):
        super(NereidChat, cls).__setup__()
        cls._sql_constraints += [
            ('unique_thread', 'UNIQUE(thread)',
                'Thread should be unique.'),
        ]

    @staticmethod
    def default_thread():
        '''
        Returns default thread id.
        '''
        return unicode(uuid.uuid4())

    @classmethod
    @route('/nereid-chat/chat.js')
    @login_required
    def chat_js(cls):
        '''
        Renders the JavaScript required for application to run.
        '''
        return Response(
            unicode(render_template('chat/chat.jinja')),
            mimetype='text/javascript'
        )

    @classmethod
    @route('/nereid-chat/chat-base')
    @login_required
    def chat_template(cls):
        '''
        The rendered templates are used by the javascript code to fetch chat
        views. You can modify this template to change the look and feel of your
        chat app.
        '''
        return Response(
            unicode(render_template('chat/chat_base.jinja')),
            mimetype='text/template'
        )

    @classmethod
    @route('/nereid-chat/start-session', methods=['POST'])
    @login_required
    def start_session(cls):
        '''
        POST: Start chat session with another user.
            :args user: User Id of nereid user.

        :return: JSON as
                {
                    thread_id: uuid,
                    members: Serialized members list.
                }
        '''
        NereidUser = Pool().get('nereid.user')
        form = NewChatForm()

        if not form.validate_on_submit():
            return jsonify(errors=form.errors), 400

        chat_with = NereidUser(form.user.data)
        if not request.nereid_user.can_chat(chat_with):
            abort(403, "You can only talk to friends")

        chat = cls.get_or_create_room(
            request.nereid_user.id, chat_with.id
        )
        return jsonify({
            'thread_id': chat.thread,
            'members': map(
                lambda m: m.user.serialize(), chat.members
            )
        })

    @classmethod
    def get_or_create_room(cls, owner, *users):
        """
        Given a list of user ids, it finds a chat room for them
        where only these users are members.

        This is separated into a separate module to make it easier
        to test the functionality and also customize for future
        modules.

        :return: No matter what happened a browse record of chat room is
                 returned
        """
        domain = [
            ('members.user', '=', owner),
        ]
        for user in users:
            domain.append(('members.user', '=', user))

        chats = cls.search(domain, limit=1)

        if not chats:
            # create a chat since one does not exist
            values = {
                'members': [
                    ('create', [{
                        'user': owner,
                        'role': 'owner'
                    }]),
                ]
            }
            for user in users:
                values['members'].append((
                    'create', [{
                        'user': user,
                        'role': 'guest'
                    }]
                ))
            chats = cls.create([values])

        return chats[0]

    @classmethod
    @route('/nereid-chat/send-message', methods=['POST'])
    @login_required
    def send_message(cls):
        '''
        POST: Publish messages to a thread.
            thread_id: thread id of session.
            message: message to send to a thread.
            type: (optional) Type of message, Default: plain

        :return: JSON ad {
                'UUID': 'unique id of message',
            }
        '''
        try:
            chat, = cls.search([
                ('thread', '=', request.form['thread_id']),
                ('members.user', '=', request.nereid_user.id)
            ])
        except ValueError:
            abort(404)

        data_message = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "message",
            "message": {
                "subject": None,
                "text": request.form['message'],
                "type": request.form.get('type', 'plain'),
                "language": "en_US",
                "attachments": [],
                "id": unicode(uuid.uuid4()),
                "thread": chat.thread,
                "sender": request.nereid_user.serialize(),
                'members': map(
                    lambda m: m.user.serialize(),
                    chat.members
                )
            }
        }

        # Save the message to messages list
        cls.save_message(chat, request.nereid_user, data_message)

        # Publish my presence too
        request.nereid_user.broadcast_presence()

        # Publish the message to the queue system
        for receiver in chat.members:
            receiver.user.publish_message(data_message)

        return jsonify({
            'UUID': unicode(data_message['message']['id']),
        })

    @classmethod
    def save_message(cls, chat, user, data_message):
        '''
        This should not be used in production as saving each chat message to
        the database might be costly
        '''
        Message = Pool().get('nereid.chat.message')

        return Message.create([{
            'chat': chat.id,
            'message': json.dumps(data_message),
            'user': user.id
        }])[0]

    @classmethod
    @route('/nereid-chat/token', methods=['POST'])
    @login_required
    def token(cls):
        '''
        Generate token for current_user with TTL of 1 hr.
        '''
        if hasattr(current_app, 'redis_client'):
            redis_client = current_app.redis_client
        else:
            redis_client = Redis(
                CONFIG.get('redis_host', 'localhost'),
                int(CONFIG.get('redis_port', 6379))
            )

        token = unicode(uuid.uuid4())
        key = 'chat:token:%s' % token
        # Save token to redis and set TTL of 1 hr.
        redis_client.set(key, current_user.id)
        redis_client.expire(key, 3600)

        return jsonify({
            'token': token
        })

    @classmethod
    @route('/nereid-chat/stream')
    @login_required
    def stream(cls):
        '''
        Set user to online and publish presence of this user to all
        friends.
        '''
        request.nereid_user.broadcast_presence()

        return Response(
            cls.generate_event_stream(
                request.nereid_user.id,
                Transaction().cursor.dbname
            ),
            mimetype='text/event-stream'
        )

    @classmethod
    @route('/nereid-chat/stream/<token>')
    def stream_via_token(cls, token):
        '''
        Set token user to online and publish presence of this user to all
        friends.
        '''
        NereidUser = Pool().get('nereid.user')

        if hasattr(current_app, 'redis_client'):
            redis_client = current_app.redis_client
        else:
            redis_client = Redis(
                CONFIG.get('redis_host', 'localhost'),
                int(CONFIG.get('redis_port', 6379))
            )

        key = 'chat:token:%s' % token
        if not redis_client.exists(key):
            abort(404)

        nereid_user = NereidUser(int(redis_client.get(key)))
        nereid_user.broadcast_presence()

        return Response(
            cls.generate_event_stream(
                nereid_user.id,
                Transaction().cursor.dbname
            ),
            mimetype='text/event-stream'
        )

    @staticmethod
    def generate_event_stream(user, dbname):
        '''
        Subscribe to chats addressed to the user and all the presence
        notifications addressed to the user.

        :param dbname: Optionally specify the dbname, if the transaction
                       context is not available
        :return: stream of a channel.
        '''
        for item in MQ.listen(user, dbname):
            yield 'data: %s\n\n' % json.dumps(item)


class ChatMember(ModelSQL):
    """
    Chat members
    """
    __name__ = "nereid.chat.member"

    chat = fields.Many2One(
        'nereid.chat', 'Chat', select=True, required=True
    )
    user = fields.Many2One(
        'nereid.user', 'User', select=True, required=True
    )
    role = fields.Selection([
        ('owner', 'owner'),
        ('guest', 'guest'),
    ], 'Role', required=True)

    @staticmethod
    def default_role():
        '''
        Returns default role of chat member to a chat.
        '''
        return 'guest'


class Message(ModelSQL):
    '''
    Message
    ~~~~~~~

    A model to store messages in a chat.

    .. warning::

        Do not use this in production as this will cause too many database
        writes and may not be scalable. Instead use a key value store like
        redis.
    '''
    __name__ = 'nereid.chat.message'

    create_date = fields.DateTime('Create Date', select=True)
    chat = fields.Many2One('nereid.chat', 'Chat', select=True, required=True)
    user = fields.Many2One('nereid.user', 'User', select=True, required=True)
    message = fields.Text('Message')

    @classmethod
    def __setup__(cls):
        super(Message, cls).__setup__()
        cls._order.insert(0, ('create_date', 'DESC'))
