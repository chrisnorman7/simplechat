"""A simple chat server using Twisted and Autobahn."""

from argparse import ArgumentParser
from socket import getfqdn
from json import loads, dumps
from jinja2 import Environment
from twisted.python import log
from klein import Klein
from autobahn.twisted.websocket import (
    WebSocketServerProtocol, WebSocketServerFactory, listenWS
)

parser = ArgumentParser()

parser.add_argument(
    '-i', '--interface', default='0.0.0.0',
    help='The default interface to bind on'
)

parser.add_argument(
    '-p', '--http-port', type=int, default=4000,
    help='The port to listen for HTTP requests'
)

parser.add_argument(
    '-w', '--websocket-port', type=int, default=4001,
    help='The socket to listen for websocket connections'
)

parser.add_argument(
    '-d', '--default-name', default='System',
    help='The default name to use when sending messages'
)


connections = []  # Store all connections.
names = set()  # The names that are already in use.
commands = {}  # The supported commands.


def command(func):
    """Decorator to add a command to the commands dictionary."""
    commands[func.__name__] = func
    return func


def send_message(message, name=None):
    """Send a message to everyone connected."""
    for connection in connections:
        connection.message(message, name=name)


class WebSocketProtocol(WebSocketServerProtocol):
    """This class is used for handling data from websockets."""

    def log_message(self, message, **kwargs):
        """Log a message."""
        kwargs.setdefault('host', self.host)
        kwargs.setdefault('port', self.port)
        log.msg(message, **kwargs)

    def send(self, name, *args, **kwargs):
        """Prepare data and send it via self.sendString."""
        data = dumps(dict(name=name, args=args, kwargs=kwargs))
        self.sendMessage(data.encode())

    def message(self, message, name=None):
        """Send a message to this socket."""
        if name is None:
            name = self.factory.default_name
        self.log_message(message, name=self.name)
        self.send('message', name, message)

    def onOpen(self):
        """Setup some initial values."""
        connections.append(self)
        self.name = None  # Don't let them transmit unless they've set a name.
        peer = self.transport.getPeer()
        self.host = peer.host
        self.port = peer.port
        self.log_message('Conected.')
        self.message('Welcome to the chatroom.')
        self.message(
            'Type /name followed by your desired name to set your name.',
            name='Suggestion'
        )

    def connectionLost(self, reason):
        """Log the reason and remove this connection."""
        self.log_message(reason.getErrorMessage())
        if self in connections:
            connections.remove(self)
        if self.name in names:
            names.remove(self.name)

    def onMessage(self, payload, is_binary):
        """A message was received."""
        if is_binary:
            # Kick them off as we don't support binary.
            return self.transport.loseConnection()
        # The below line assumes the message is in the right format. If it's
        # not they will be disconnected by the resulting error.
        name, args, kwargs = loads(payload)
        func = commands.get(name)
        if func is None:
            return self.message(f'Unsupported command: {name}.')
        func(self, *args, **kwargs)


@command
def name(con, name):
    """Set con.name."""
    if not name:
        con.message('You must give a name.')
    elif name in names:
        con.message('You cannot use that name.')
    else:
        if con.name in names:
            names.remove(con.name)
        old = con.name
        if old == name:
            con.message('Name unchanged.')
        else:
            con.name = name
            names.add(name)
            if old:
                msg = f'{old} is now known as {con.name}.'
            else:
                msg = f'{con.name} has joined the chatroom.'
            send_message(msg)


@command
def message(con, text):
    """Connection con has sent a message."""
    if con.name is None:
        con.message('You must set your name before you can transmit.')
    elif not text:
        con.message('Messages cannot be blank.')
    else:
        send_message(text, name=con.name)


app = Klein()  # We use this to serve HTML.
environment = Environment()  # We use this for templating.
index_kwargs = {}


@app.route('/')
def index(request):
    with open('chat.html', 'r') as f:
        return environment.from_string(f.read()).render(**index_kwargs)


if __name__ == '__main__':
    args = parser.parse_args()
    factory = WebSocketServerFactory(
        f'ws://{args.interface}:{args.websocket_port}'
    )
    factory.default_name = args.default_name
    names.add(factory.default_name)
    factory.protocol = WebSocketProtocol
    index_kwargs.update(
        hostname=getfqdn(), http_port=args.http_port,
        websocket_port=args.websocket_port
    )
    listenWS(factory, interface=args.interface)
    app.run(host=args.interface, port=args.http_port)
