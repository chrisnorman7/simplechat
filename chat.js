/* global Cookies */

const cookies_options = {expires: 365}

let input = document.getElementById("input")
let output = document.getElementById("output")
let command_match = /[/]([^ $]+)[ ]?([^$]+)?$/
let notification = document.getElementById("notification")
let last_notification = 0

function play_notification() {
    let now = new Date().getTime()
    if ((now - last_notification) >= 1000) {
        notification.currentTime = 0
        notification.play()
        last_notification = now
    }
}

const functions = {
    message: obj => {
        play_notification()
        let name = obj.args[0]
        let text = obj.args[1]
        write_message(name, text)
    },
    name: obj => {
        Cookies.set("name", obj.args[0], cookies_options)
    }
}

document.forms[0].onsubmit = (e) => {
    play_notification()
    e.preventDefault()
    let text = input.value
    input.value = ""
    let match = text.match(command_match)
    if (match === null) {
        // Let's just send.
        send("message", [text])
    } else {
        // They want to send a command.
        let command = match[1]
        let arg = match[2]
        let args = [arg]
        send(command, args)
    }
}

function write_message(name, text) {
    if (!name) {
        name = "<local>"
    }
    let h = document.createElement("h3")
    h.innerText = name
    output.appendChild(h)
    let p = document.createElement("p")
    p.innerHTML = text
    output.appendChild(p)
    window.scrollTo(0,document.body.scrollHeight)
}

function send(command, args, kwargs) {
    if (args === undefined) {
        args = []
    }
    if (kwargs === undefined) {
        kwargs = {}
    }
    let data = JSON.stringify([command, args, kwargs])
    socket.send(data)
}

let socket = new WebSocket("ws://{{ hostname }}:{{ websocket_port }}")

socket.onopen = () => {
    input.focus()
    write_message(null, "Connected")
    let name = Cookies.get("name")
    if (name !== undefined) {
        send("name", [name])
    }
}

socket.onclose = () => {
    write_message(null, "Disconnected (press refresh)")
}

socket.onmessage = (e) => {
    let obj = JSON.parse(e.data)
    let func = functions[obj.name]
    if (func !== undefined) {
        func(obj)
    } else {
        write_message(null, `Unrecognised command: ${e.data}.`)
    }
}
