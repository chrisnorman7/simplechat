"""A simple chat server using Twisted and Autobahn."""

import os
from argparse import ArgumentParser
from inspect import getdoc
from socket import getfqdn
from json import loads, dumps
from jinja2 import Environment, FileSystemLoader
from twisted.python import log  # Used by Klein (annoyingly).
from twisted.web.static import File
from klein import Klein
from autobahn.twisted.websocket import (
    WebSocketServerProtocol, WebSocketServerFactory, listenWS
)

parser = ArgumentParser()  # So we can add command line arguments.

parser.add_argument(
    '-i', '--interface', default='0.0.0.0',
    help='The interface to listen on'
)

parser.add_argument(
    '-p', '--http-port', type=int, default=4000,
    help='The port to listen for HTTP requests on'
)

parser.add_argument(
    '-w', '--websocket-port', type=int, default=4001,
    help='The port to listen for websocket connections on'
)

parser.add_argument(
    '-d', '--default-name', default='System',
    help='The name to use when sending system messages'
)


connections = []  # A list of all connected clients.
names = set()  # The names that are already in use.
commands = {}  # The supported commands.


def command(func):
    """Decorator to add a command to the commands dictionary. Couple with
    @no_args if you want a command that takes no arguments."""
    commands[func.__name__] = func
    return func


def no_arguments(func):
    """A decorator that says this command takes no arguments. Used with
    @command."""
    def inner(con, *args, **kwargs):
        """Check to see if the command was given any arguments."""
        if any(args) or any(kwargs):
            con.message('This command takes no arguments.')
        else:
            func(con)
    # The next two lines are needed becuase otherwise the command will be
    # registered as inner.
    inner.__name__ = func.__name__
    inner.__doc__ = func.__doc__
    # Return this function.
    return inner


def send_message(message, name=None):
    """Send the provided message to all connected clients. Use the provided
    name instead of the default one."""
    for connection in connections:
        connection.message(message, name=name)


class WebSocketProtocol(WebSocketServerProtocol):
    """This class is used for handling data from websockets and should not be
    confused with the Klein instance which handles pure HTTP requests."""

    def disconnect(self, message=None):
        """Disconnect this socket. If message is not None then the message will
        be sent first."""
        if message is not None:
            self.message(message)
        self.transport.loseConection()

    def log_message(self, message, **kwargs):
        """Log a message using twisted.python.log."""
        kwargs.setdefault('host', self.host)
        kwargs.setdefault('port', self.port)
        log.msg(message, **kwargs)

    def send(self, name, *args, **kwargs):
        """Send a command named name with the provided args and kwargs to this
        socket."""
        data = dumps(dict(name=name, args=args, kwargs=kwargs))
        self.sendMessage(data.encode())

    def message(self, message, name=None):
        """Send a message to this socket. If name is None then the default name
        will be used."""
        if name is None:
            name = self.factory.default_name
        self.log_message(message, name=self.name)
        self.send('message', name, message)

    def message_lines(self, lines, name=None):
        """Send a message which spans several lines. The name will only be
        printed once."""
        return self.message('\n'.join(lines), name=name)

    def onOpen(self):
        """The socket is connected. Setup some initial values and add this
        socket to the connections list."""
        connections.append(self)
        self.name = None  # Don't let them transmit unless they've set a name.
        peer = self.transport.getPeer()  # Connection information.
        self.host = peer.host
        self.port = peer.port
        self.log_message('Conected.')
        self.message('Welcome.')
        self.message(
            'Type /name followed by your desired name to set your name.',
            name='Suggestion'
        )

    def connectionLost(self, reason):
        """This socket has been disconnected for some reason. Log the reason
        and remove this connection. Not overriding
        WebSocketServerProtocol.onClose because we aren't doing anything
        specific to websockets."""
        self.log_message(reason.getErrorMessage())
        # It is highly unlikely that this socket isn't in the list, but best to
        # check because some of the things that haunt the internet don't do
        # stuff as we'd expect and they might disconnect before our onOpen
        # method has been called.
        if self in connections:
            connections.remove(self)
        if self.name in names:  # They might not have set a name.
            send_message(f'{self.name} has left the server.')
            names.remove(self.name)

    def onMessage(self, payload, is_binary):
        """A message was received. This will be a string of raw data which we
        expect to be json-encoded. Of course it is entirely likely that
        whatever sent it is just messing with us so we're not trying too hard
        to catch errors since any exceptions thrown will result in the
        connection being dropped."""
        if is_binary:
            # Kick them off as we don't support binary.
            self.log_message('Binary string received.')
            return self.disconnect('No binary allowed.')
        # The below line assumes the message is in the right format. If it's
        # not they will be disconnected by the resulting error.
        name, args, kwargs = loads(payload)
        # Let's find they command they're trying to call.
        func = commands.get(name)
        if func is None:  # Command not found.
            return self.message(f'Unsupported command: {name}.')
        # Call the valid function. Any errors thrown at this point will still
        # cause a disconnect.
        func(self, *args, **kwargs)


# Let's add commands.
# The help command treats docstrings from the command functions as descriptions
# so they should be formatted as such.

@command
def name(con, name):
    """Set your name."""
    if not name:  # We don't want blank names.
        con.message('You must give a name.')
    elif name in names:  # That name is already taken.
        con.message('You cannot use that name.')
    else:  # This is a good name.
        if con.name in names:  # Allow the name to be used again.
            names.remove(con.name)
        old = con.name  # For comparison.
        if old == name:  # They aren't actually changing anything.
            con.message('Name unchanged.')
        else:  # It is different.
            con.name = name  # Set the new name.
            names.add(name)  # Add it to the set of names.
            # In the below lines we use a variable to store the message. This
            # means if the API ever changes we only need to change the line
            # that sends the message.
            if old:  # This was a name change.
                msg = f'{old} is now known as {con.name}.'
            else:  # They are setting their name for the first time.
                msg = f'{con.name} has joined the server.'
            # Send the message:
            send_message(msg)


@command
def message(con, text):
    """Send a message to everyone in the chatroom. You do not need to type this
    command directly."""
    if con.name is None:  # They haven't set their name yet.
        con.message('You must set your name before you can transmit.')
    elif not text:  # Blank message.
        con.message('Messages cannot be blank.')
    else:  # Good to go.
        send_message(text, name=con.name)


@command
@no_arguments  # Don't accept extra text after the command.
def who(con):
    """Show who's connected."""
    results = ['Who listing:']
    for connection in connections:
        if connection.name is None:
            continue
        results.append(
            f'{connection.name} from {connection.host}:{connection.port}'
        )
    con.message_lines(results)


@command
@no_arguments
def disconnect(con):
    """Disconnect from the server. You will need to refresh the page in order
    to reconnect."""
    con.disconnect('Goodbye.')


# This command overrides Python's help builtin and will cause confusion if
# examining code from the interactive python shell. To get around this problem
# you could make the command decorator accept an optional name argument so you
# could name functions whatever you like without compromising usability.
@command
def help(con, command):
    """Get help on a command or list all commands."""
    if command is None:  # Show them all.
        results = ['Commands:']
        for name, func in commands.items():
            results.append(f'/{name}')
            results.append(getdoc(func))
    elif command in commands:  # They want to know about a specific command.
        results = [f'Help on /{command}:']
        results.append(getdoc(commands[command]))
    else:  # They want to know about a command that doesn't exist.
        results = ['No such command.']
    con.message_lines(results)


# Web stuff. This is separate to the socket stuff and just renders the HTML,
# Javascript and MP3 data to clients' web browsers.
app = Klein()  # We use this to serve HTML.

# We need a loader that can load templates from the filesystem with the
# environment.get_template method.
loader = FileSystemLoader(os.curdir)

# The environment handles templating with Jinja2. To see the raw files open
# chat.html and chat.js. It is worth noting that Jinja2 knows nothing about the
# web and can be used anywhere templating is required.
environment = Environment(loader=loader)
index_kwargs = {}  # These are used for rendering from the index method.


@app.route('/notify.mp3')
def notify_mp3(request):
    """We use a twisted.web.static.File instance to render the mp3 as
    binary data."""
    return File('notify.mp3')


@app.route('/')
def index(request):
    """Return the main page."""
    # The template describing chat.html:
    template = environment.get_template('chat.html')
    return template.render(**index_kwargs)


if __name__ == '__main__':
    args = parser.parse_args()  # Command line arguments.

    # Tell Twisted how to serve websockets:
    factory = WebSocketServerFactory(
        f'ws://{args.interface}:{args.websocket_port}'
    )

    # Set up the default name from the command line.
    factory.default_name = args.default_name
    names.add(factory.default_name)

    # factory.protocol will be returned by factory.buildProtocol.
    # This is a shortcut instead of subclassing WebSocketServerFactory and
    # defining our own buildProtocol method.
    # If you wanted to disallow connections from certain hosts then you could
    # subclass WebSocketServerFactory and create your own buildProtocol method
    # that returned None when the hostname was blacklisted.
    factory.protocol = WebSocketProtocol

    # Create kwargs for use with the index method. By doing things this way we
    # don't hard code anything in javascript.
    index_kwargs.update(
        hostname=getfqdn(), http_port=args.http_port,
        websocket_port=args.websocket_port
    )
    listenWS(factory, interface=args.interface)  # Listen for websockets.
    app.run(host=args.interface, port=args.http_port)  # Main loop.
