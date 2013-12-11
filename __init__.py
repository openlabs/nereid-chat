# -*- coding: utf-8 -*-
'''
    __init__

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Ltd.
    :license: see LICENSE for more details

'''
from chat import NereidUser, NereidChat, ChatMember, Message

from trytond.pool import Pool


def register():
    '''
        Register classes
    '''
    Pool.register(
        NereidUser,
        NereidChat,
        ChatMember,
        Message,
        module='nereid_chat', type_='model'
    )
