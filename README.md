# simplechat
A simple web-based chat server

This chatroom is purely text-based (although unicode including emojis are supported).

It requires only python (tested with 3.6) and a few external dependancies to run.

## Usage

### Clone The Code
```
git clone https://github.com/chrisnorman7/simplechat.git
cd simplechat
```

### Create virtualenv (Optional)
```
virtualenv env
```

### Activate The Environment
#### Linux
```
source env/bin/activate
```

#### Windows
```
env\scripts\activate.bat
```

### Install Requirements
```
pip install -r requirements.txt
```

### Run the server
```
python server.py
```

## Files
* server.py: Python source for the server.
* chat.html: The [Jinja2](http://jinja.pocoo.org/docs/2.10/) template used by the `index` webroute.
* chat.js: The javascript which is included by chat.html.
* setup.cfg: Configuration for [Flake8](http://flake8.pycqa.org/).
* requirements.txt: The [requirements](https://pip.readthedocs.io/en/1.1/requirements.html) file for use with [Pip](https://pypi.python.org/pypi/pip).
* todo.txt: A list of suggestions for code improvements left as an exercise for the reader.
* notify.mp3: The notification sound played when messages are sent and received.
* LICENSE: Licensing information.
