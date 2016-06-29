import re
import json
import logging
from channels import Group
from channels.sessions import channel_session
from .models import Room

log = logging.getLogger(__name__)

@channel_session
def ws_connect(message):
    # Extract the room from the message. This expects message.path to be of the
    # form /chat/{label}/, and finds a Room if the message path is applicable,
    # and if the Room exists. Otherwise, bails (meaning this is a some othersort
    # of websocket). So, this is effectively a version of _get_object_or_404.
    try:
        prefix, label = message['path'].decode('ascii').strip('/').split('/')
        if prefix != 'chat':
            log.debug('invalid ws path=%s', message['path'])
            return
        room = Room.objects.get(label=label)
    except ValueError:
        log.debug('invalid ws path=%s', message['path'])
        return
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s, create it', label)
        room = Room.objects.create(label=label)

    log.debug('chat connect room=%s client=%s:%s',
        room.label, message['client'][0], message['client'][1])

    # Need to be explicit about the channel layer so that testability works
    # This may be a FIXME?
    Group('chat-'+label, channel_layer=message.channel_layer).add(message.reply_channel)

    message.channel_session['room'] = room.label

    # messages = room.messages.all()
    # for msg in messages:
    #     # See above for the note about Group
    #     msg_dict = msg.as_dict()
    #     msg_dict['history'] = "true"
    #     Group('chat-'+label, channel_layer=message.channel_layer).send({'text': json.dumps(msg_dict)})

@channel_session
def ws_receive(message):
    # Look up the room from the channel session, bailing if it doesn't exist
    try:
        label = message.channel_session['room']
        room = Room.objects.get(label=label)
    except KeyError:
        log.debug('no room in channel_session')
        return
    except Room.DoesNotExist:
        log.debug('recieved message, buy room does not exist label=%s', label)
        return

    # Parse out a chat message from the content text, bailing if it doesn't
    # conform to the expected message format.
    try:
        data = json.loads(message['text'])
    except ValueError:
        log.debug("ws message isn't json text=%s", text)
        return

    if set(data.keys()) != set(('handle', 'message')):
        log.debug("ws message unexpected format data=%s", data)
        return

    if data:
        log.debug('chat message room=%s handle=%s message=%s',
            room.label, data['handle'], data['message'])
        m = room.messages.create(**data)

        receiver = extract_receiver(data['handle'], label)
        m_dict = m.as_dict()

        # See above for the note about Group
        Group('chat-'+label, channel_layer=message.channel_layer).send({'text': json.dumps(m_dict)})
        Group('chat-rec_' + receiver).send({'text': json.dumps(m_dict)})

@channel_session
def ws_disconnect(message):
    try:
        label = message.channel_session['room']
        room = Room.objects.get(label=label)
        Group('chat-'+label, channel_layer=message.channel_layer).discard(message.reply_channel)
    except (KeyError, Room.DoesNotExist):
        pass

def extract_receiver(handle, label):
    a, b = label.split('_')
    if (a == handle):
        return b
    else:
        return a
