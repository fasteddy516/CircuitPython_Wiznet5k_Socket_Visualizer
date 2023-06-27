"""
CircuitPython WIZnet5k Socket Visualizer.

A tool to help visualize the state of hardware sockets on WIZnet5k chipsets.

* Author(s): Edward Wright

Developed and tested using CircuitPython 8.1.0 and Adafruit_CircuitPython_Wiznet5k
driver version 2.5.3 on a Raspberry Pi Pico attached to a WIZnet Ethernet Hat with a
w5100s chipset.  Output verified in the SimplySerial terminal application running in
PowerShell on Windows 11.

Colors and unicode characters are used in the console output, so be sure to
use a terminal application that supports those features.

This tool accesses private variables/properties (socket._socknum, socket._status,
and WIZNET5K._sockets_reserved) which are not part of the official driver API and may
be changed in driver versions beyond 2.5.3, which may also break this tool.


MIT License
=============================

Copyright (c) 2023 Edward Wright

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

"""
import os
import sys
import time

import board
import busio
import digitalio

try:
    import adafruit_wiznet5k.adafruit_wiznet5k_socket as socket
    from adafruit_wiznet5k.adafruit_wiznet5k import (
        SNSR_SOCK_CLOSE_WAIT,
        SNSR_SOCK_FIN_WAIT,
        WIZNET5K,
        __version__,
    )
except ImportError:
    print(
        "\r\n* The 'adafruit_wiznet5k' driver is required but "
        "does not appear to be installed."
    )
    sys.exit()

# CONFIGURATION --------------------------------------------------------------
DEBUG = False  # set to 'True' to enable driver debugging text

DHCP = True  # set to 'True' to enable DHCP, 'False' to use static settings
IP = (192, 168, 1, 200)  # only used if DHCP = False
SUBNET_MASK = (255, 255, 255, 0)  # only used if DHCP = False
DEFAULT_GATEWAY = (192, 168, 1, 1)  # only used if DHCP = False
DNS_SERVER = (192, 168, 1, 1)  # only used if DHCP = False

SERVER_PORT = 2231  # the TCP port to accept connections on1

# Set the following to match the pins used in your setup.  The default values
# work for a Raspberry Pi Pico connected to a WIZnet Ethernat Hat.  If your
# setup does not include a reset pin, set RESET_PIN to None.
CS_PIN = board.GP17  # Chip Select pin (default = board.GP17)
SPI_CLOCK_PIN = board.GP18  # SPI clock pin (default = board.GP18)
SPI_MOSI_PIN = board.GP19  # SPI MOSI pin (default = board.GP19)
SPI_MISO_PIN = board.GP16  # SPI MISO pin (default = board.GP16)
RESET_PIN = board.GP20  # Wiznet hadrware reset pin (default = board.GP20)

# END OF CONFIGURATION -------------------------------------------------------

# Virtual Terminal Sequences to specify text foreground color
FG = {
    "black": "\033[90m",
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "magenta": "\033[95m",
    "cyan": "\033[96m",
    "white": "\033[97m",
}

# Virtual Terminal Sequence used to reset text properties
CT = "\033[97m"  # normally '[0m', but using bright white here

# Colorized descriptions for socket state values
SOCKET_STATE = {
    "{:02X}".format(0x00): f"{FG['green']}CLOSED{CT}",
    "{:02X}".format(0x13): f"{FG['cyan']}INIT{CT}",
    "{:02X}".format(0x14): f"{FG['yellow']}LISTENING{CT}",
    "{:02X}".format(0x15): f"{FG['blue']}SYN_SENT{CT}",
    "{:02X}".format(0x16): f"{FG['blue']}SYN_RECV{CT}",
    "{:02X}".format(0x17): f"{FG['blue']}ESTABLISHED{CT}",
    "{:02X}".format(0x18): f"{FG['red']}FIN_WAIT{CT}",
    "{:02X}".format(0x1A): f"{FG['red']}CLOSING{CT}",
    "{:02X}".format(0x1B): f"{FG['cyan']}TIME_WAIT{CT}",
    "{:02X}".format(0x1C): f"{FG['red']}CLOSE_WAIT{CT}",
    "{:02X}".format(0x1D): f"{FG['cyan']}LAST_ACK{CT}",
    "{:02X}".format(0x22): f"{FG['yellow']}UDP{CT}",
    "{:02X}".format(0x32): f"{FG['yellow']}IPRAW{CT}",
    "{:02X}".format(0x42): f"{FG['yellow']}MACRAW{CT}",
    "{:02X}".format(0x5F): f"{FG['yellow']}PPPOE{CT}",
}

# Unicode characters used to represent socket reservation status
RESERVED_STATE = {
    "False": f"{FG['green']}●",
    "True": f"{FG['red']}●",
    "Unlocked": f"{FG['white']}●",
}

# Display program header
print(
    f"\r\n{FG['yellow']}✨ "
    + f"{FG['blue']} CircuitPython WIZnet5k Socket Visualizer "
    + f"{FG['yellow']}✨{CT}\r\n\r\n"
    + f"   {FG['yellow']}🖉 {CT}Written by Edward Wright\r\n"
    + f"   {FG['cyan']}🌐 {CT}"
    + "https://github.com/fasteddy516/CircuitPython_Wiznet5k_Socket_Visualizer\r\n"
)

# Configure and load Wiznet5k driver
cs = digitalio.DigitalInOut(CS_PIN)
spi_bus = busio.SPI(SPI_CLOCK_PIN, SPI_MOSI_PIN, MISO=SPI_MISO_PIN)
if RESET_PIN:
    reset = digitalio.DigitalInOut(RESET_PIN)
    reset.direction = digitalio.Direction.OUTPUT
else:
    reset = None
eth = WIZNET5K(spi_bus, cs, reset=reset, is_dhcp=DHCP, debug=DEBUG)
if not DHCP:
    eth.ifconfig = (IP, SUBNET_MASK, DEFAULT_GATEWAY, DNS_SERVER)

# Display hardware/configuration information
m = eth.mac_address
print(
    f"{FG['blue']}Board...............:{FG['white']} {os.uname()[4]}\r\n"
    + f"{FG['blue']}CircuitPython.......:{FG['white']} {os.uname()[3]}\r\n"
    + f"{FG['blue']}Driver..............:{FG['white']} {__version__}\r\n"
    + f"{FG['blue']}Chip................:{FG['white']} {eth.chip}\r\n"
    + f"{FG['blue']}Reservable Sockets..:{FG['white']} {eth.max_sockets - 1} "
    + f"{FG['black']}(Socket #0 cannot be reserved)\r\n"
    + f"{FG['blue']}MAC Address.........: {FG['white']}"
    + f"{m[0]:02X}:{m[1]:02X}:{m[2]:02X}:{m[3]:02X}:{m[4]:02X}:{m[5]:02X}\r\n"
    + f"{FG['blue']}IP address..........: {FG['white']}"
    + f"{eth.pretty_ip(eth.ip_address)}\r\n{CT}"
    + f"\r\n{FG['blue']}* Waiting for Ethernet connection {FG['white']} ... ",
    end="",
)

# Wait for ethernet connection to come up
while eth.link_status is False:
    time.sleep(0.25)

print(f"{FG['green']}[ {FG['white']}OK {FG['green']}]{CT}\r\n")

# Start our server
socket.set_interface(eth)
server = socket.socket()
ip = eth.pretty_ip(eth.ip_address)
server.bind((ip, SERVER_PORT))
server.settimeout(0.001)  # run in non-blocking (in general terms) mode
server.listen()


def show_listen_status() -> None:
    print(
        f"{FG['green']}* Listening for connections on "
        + f"{FG['yellow']}Socket {server._socknum:02d}{CT}"
        + f"{FG['green']} @ {FG['white']}{ip}:{SERVER_PORT}{CT}"
    )


show_listen_status()

# Set up variables used in our main loop
clients = [None for _ in range(eth.max_sockets)]
last_state = ""
stamp = time.monotonic()
heartbeat = False
out_of_sockets = False

# Main loop
while True:
    if DHCP:
        eth.maintain_dhcp_lease()

    # Accept incoming connections (non-blocking).
    try:
        c, a = server.accept()
        print(
            f"{FG['green']}+ Socket {FG['white']}{c._socknum:02d} {FG['green']}> "
            + f"Connection from {FG['white']}{a[0]}:{a[1]} {FG['green']}accepted"
            + f"{CT}"
        )
        clients[c._socknum] = (c, a, time.monotonic())
        c.send(
            bytearray(
                f"{FG['yellow']}🗲 {FG['green']}Connected to Socket {c._socknum:02d} "
                + f"{FG['yellow']}🗲\r\n"
            )
        )
        out_of_sockets = False
        show_listen_status()
    except TimeoutError:
        pass
    except RuntimeError as e:
        if str(e) == "All sockets in use." or str(e) == "Out of sockets.":
            if out_of_sockets is False:
                print(f"{FG['red']}* Could not accept connection, all sockets in use.")
                out_of_sockets = True
        else:
            raise

    # Process current clients.
    if time.monotonic() - stamp >= 2:
        heartbeat = True
        stamp = time.monotonic()

    for i, c in enumerate(clients):
        if c is None:
            continue
        if c[0]._status in (
            SNSR_SOCK_FIN_WAIT,
            SNSR_SOCK_CLOSE_WAIT,
        ):
            print(
                f"{FG['red']}- Socket {FG['white']}{c[0]._socknum:02d} {FG['red']}> "
                + f"Connection to {FG['white']}{c[1][0]}:{c[1][1]} {FG['red']}closed"
                + f"{CT}"
            )
            c[0].close()
            clients[i] = None
        elif heartbeat:
            c[0].send(
                bytearray(
                    f"{FG['red']}💓 {FG['white']}Socket {c[0]._socknum:02d} "
                    + f"[{time.monotonic() - c[2]:0.2f}s] {FG['red']}💓\r\n"
                )
            )

    heartbeat = False

    # Update socket status and print visualization if it has changed.
    current_state = (
        f"\r\n{FG['white']}┏━━━━┳━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┓{CT}\r\n"
    )
    for i in range(eth.max_sockets):
        socket_state = eth.socket_status(i)
        if isinstance(socket_state, int):
            state_text = SOCKET_STATE[f"{socket_state:02X}"]
        else:
            state_text = SOCKET_STATE[f"{int(socket_state[0]):02X}"]

        if clients[i] is None:
            client_text = "         ---         "
            client_color = f"{FG['black']}"
        else:
            client_text = f"{clients[i][1][0]}:{clients[i][1][1]}"
            client_color = f"{FG['yellow']}"

        current_state += (
            f"{FG['white']}┃ "
            + f"S{i}"
            + f"{FG['white']} ┃ "
            + (
                RESERVED_STATE[str(WIZNET5K._sockets_reserved[i - 1])]
                if i > 0
                else RESERVED_STATE["Unlocked"]
            )
            + f"{FG['white']} ┃ {state_text:<21}{FG['white']} ┃ "
            + f"{client_color}{client_text:<21}"
            + f"{FG['white']} ┃\r\n"
        )
    current_state += (
        f"{FG['white']}┗━━━━┻━━━┻━━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━━┛{CT}\r\n"
    )
    if current_state != last_state:
        print(current_state)
        last_state = current_state
