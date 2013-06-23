# -*- coding: utf-8 -*-
"""
    chat

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from datetime import datetime
import uuid

from gevent import queue
import simplejson as json
from nereid import request, render_template, jsonify, Response, abort, \
    login_required
from trytond.model import ModelView, ModelSQL, fields
from trytond.transaction import Transaction
from trytond.pool import Pool

counter = {'c': 0}


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
    _name = 'nereid.user'

    chat_available = fields.Function(
        fields.Boolean('Available'), 'get_available'
    )

    def get_available(self, ids, name):
        '''
        Looks into the message queue and figures out if the user is available
        or not
        '''
        res = {}
        for user in ids:
            res[user] = not MQ.is_user_offline(user)
        return res

    def _json(self, sender):
        """
        Serialize the sender alone and return a dictionary. This is separated
        so that other modules can easily modify the behavior independent of
        this module.

        :param sender: Browse record of nereid.user.
        """
        return {
            "url": None,
            "objectType": self._name,
            "id": sender.id,
            "displayName": sender.display_name,
        }

    @login_required
    def get_chat_friends(self, nereid_user):
        """
        Returns list of friends of nereid_user. This is separated so that
        other modules can easily modify the behavior independent of this
        modules.
        This is for other modules which implement the functionality to extend.
        Current functionality allows all are chatting friends.

        :param nereid_user: Browse record of nereid.user.
        :return: List of browse records of friends.
        """
        return filter(
            lambda user: user != request.nereid_user,
            self.browse(self.search([]))
        )

    @login_required
    def chat_friends(self):
        """
        GET: Returns the JSON dictionary of all chat friends with their
        presence stanza.
        """
        friends = self.get_chat_friends(request.nereid_user)
        friends_presence = []
        for friend in friends:
            friends_presence.append(self.get_presence(friend))
        return jsonify({
            'friends': friends_presence,
        })

    def get_presence(self, nereid_user):
        '''
        Returns the presence status of a nereid_user.

        :param nereid_user: Browse record of nereid.user.
        '''
        return {
            "entity": self._json(nereid_user),
            "show": "chat",
            "status": None,
            'available': nereid_user.chat_available,
        }

    def can_chat(self, me, other):
        '''
        Return True if the user can talk to the other user.

        This is for other modules which implement the functionality to extend.
        Current functionality allows to talk to user's chat friends only.

        :param me: Browse record of nereid_user, to check permission of.
        :param other: Browse record of nereid_user, to check permission with.
        '''
        if other in self.get_chat_friends(me):
            return True
        return False

NereidUser()


class NereidChat(ModelSQL, ModelView):
    '''
    Nereid Chat
    '''
    _name = 'nereid.chat'
    _description = __doc__

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

    def __init__(self):
        super(NereidChat, self).__init__()
        self._sql_constraints += [
            ('unique_thread', 'UNIQUE(thread)',
                'Thread should be unique.'),
        ]

    def default_thread(self):
        '''
        Returns default thread id.
        '''
        return unicode(uuid.uuid4())

    @login_required
    def chat_js(self):
        '''
        Renders the JavaScript required for application to run.
        '''
        return Response(
            render_template('chat/chat.jinja'),
            mimetype='text/javascript'
        )

    @login_required
    def chat_template(self):
        '''
        The rendered templates are used by the javascript code to fetch chat
        views. You can modify this template to change the look and feel of your
        chat app.
        '''
        return Response(
            render_template('chat/chat_base.jinja'),
            mimetype='text/template'
        )

    def publish_message(self, user, data_message):
        '''
        Publishes message to channel/queue
        '''
        return MQ.publish(user.id, data_message)

    def publish_presence(self, nereid_user):
        '''
        Publishes presence to all friends.

        :param nereid_user: Browse record of nereid.user.
        '''
        nereid_user_obj = Pool().get('nereid.user')

        presence_message = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "presence",
            "presence": nereid_user_obj.get_presence(nereid_user),
        }
        friends = nereid_user_obj.get_chat_friends(nereid_user)
        for user in friends:
            MQ.publish(user.id, presence_message)

    @login_required
    def start_session(self):
        '''
        POST: Start chat session with another user.
            :args user: User Id of nereid user.

        :return: JSON as
                {
                    success: 'True/False',
                    thread_id: uuid,
                    members: Serialized members list.
                }
        '''
        nereid_user_obj = Pool().get('nereid.user')

        chat_with = request.form.get('user', 0, int)

        if not chat_with:
            abort(400, "Cannot find the person you want to talk to")

        chat_with = nereid_user_obj.browse(chat_with)
        if not nereid_user_obj.can_chat(request.nereid_user, chat_with):
            abort(403, "You can only talk to friends")

        chat = self.get_or_create_room(
            request.nereid_user.id, chat_with.id
        )
        return jsonify({
            'success': True,
            'thread_id': chat.thread,
            'members': map(
                lambda m: nereid_user_obj._json(m.user), chat.members
            )
        })

    def get_or_create_room(self, owner, *users):
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

        chat_ids = self.search(domain, limit=1)

        if not chat_ids:
            # create a chat since one does not exist
            values = {
                'members': [
                    ('create', {
                        'user': owner,
                        'role': 'owner'
                    }),
                ]
            }
            for user in users:
                values['members'].append((
                    'create', {
                        'user': user,
                        'role': 'guest'
                    }
                ))
            chat_ids = [self.create(values)]

        return self.browse(chat_ids[0])

    @login_required
    def send_message(self):
        '''
        POST: Publish messages to a thread.
            thread_id: thread id of session.
            message: message to send to a thread.
            type: (optional) Type of message, Default: plain

        :return: JSON ad {
                'success': True/False,
                'UUID': 'unique id of message',
            }
        '''
        nereid_user_obj = Pool().get('nereid.user')

        try:
            chat, = self.browse(self.search([
                ('thread', '=', request.form['thread_id']),
                ('members.user', '=', request.nereid_user.id)
            ]))
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
                "sender": nereid_user_obj._json(request.nereid_user),
                'members': map(
                    lambda m: nereid_user_obj._json(m.user),
                    chat.members
                )
            }
        }

        # Save the message to messages list
        self.save_message(chat, request.nereid_user, data_message)

        # Publish my presence too
        self.publish_presence(request.nereid_user)

        # Publish the message to the queue system
        for receiver in chat.members:
            self.publish_message(receiver.user, data_message)

        return jsonify({
            'success': True,
            'UUID': unicode(data_message['message']['id']),
        })

    def save_message(self, chat, user, data_message):
        '''
        This should not be used in production as saving each chat message to
        the database might be costly
        '''
        message_obj = Pool().get('nereid.chat.message')

        return message_obj.create({
            'chat': chat.id,
            'message': json.dumps(data_message),
            'user': user.id
        })

    @login_required
    def stream(self):
        '''
        Set user to online in Redis and publish presence of this user to all
        friends.
        '''
        self.publish_presence(request.nereid_user)

        return Response(
            self.generate_event_stream(
                request.nereid_user.id,
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

NereidChat()


class ChatMember(ModelSQL):
    """
    Chat members
    """
    _name = "nereid.chat.member"
    _doc = __doc__

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

    def default_role(self):
        '''
        Returns default role of chat member to a chat.
        '''
        return 'guest'

ChatMember()


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
    _name = 'nereid.chat.message'

    create_date = fields.DateTime('Create Date', select=True)
    chat = fields.Many2One('nereid.chat', 'Chat', select=True, required=True)
    user = fields.Many2One('nereid.user', 'User', select=True, required=True)
    message = fields.Text('Message')

    def __init__(self):
        super(Message, self).__init__()
        self._order.insert(0, ('create_date', 'DESC'))

Message()
