######################################################################
#
# All files associated with the OpenFlow Python Switch (ofps) are
# made available for public use and benefit with the expectation
# that others will use, modify and enhance the Software and contribute
# those enhancements back to the community. However, since we would
# like to make the Software available for broadest use, with as few
# restrictions as possible permission is hereby granted, free of
# charge, to any person obtaining a copy of this Software to deal in
# the Software under the copyrights without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject
# to the following conditions:
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT.  IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# 
######################################################################

"""
Controller Interface Class

This class supports the interface to the controller.  It is 
roughly based on the controller object from OFTest.  It is 
threaded.
"""

import os
import socket
import time
import sys
from threading import Thread
from oftest.message import *
from oftest.parse import *
from oftest.ofutils import *
# For some reason, it seems select to be last (or later).
# Otherwise get an attribute error when calling select.select
import select
import logging

##@todo Find a better home for these identifiers (controller)
RCV_SIZE_DEFAULT = 32768

class ControllerInterface(Thread):
    """
    Class abstracting the interface to the controller.
    """

    def __init__(self, host='127.0.0.1', port=6633):
        super(ControllerInterface, self).__init__()

        self.ctrl_socket = None
        self.rcv_size = RCV_SIZE_DEFAULT
        self.socs = []

        # Counters
        self.parse_errors = 0
        self.packets_total = 0
        self.packets_handled = 0
        self.packets_discarded = 0

        # State
        self.handlers = {}
        self.keep_alive = True
        self.active = True
        self.initial_hello = True
        self.exit_on_reset = True

        # Settings
        self.host = host
        self.port = port
        self.dbg_state = "init"
        self.logger = logging.getLogger("controller")
        self.no_version_check = False
        self.version_checked = False

    def _pkt_handle(self, pkt):
        """
        Check for all packet handling conditions

        Parse and verify message 
        Check if keep alive is on and message is an echo request
        Check if any registered handler wants the packet
        Discard if none of those conditions is met

        @param pkt The raw packet (string) which may contain multiple OF msgs
        """
        # Process each of the OF msgs inside the pkt
        offset = 0
        while offset < len(pkt):
            # Parse the header to get type
            hdr = of_header_parse(pkt[offset:])
            if not hdr:
                self.logger.info("Could not parse header, pkt len", len(pkt))
                self.parse_errors += 1
                return
            if hdr.length == 0:
                self.logger.info("Header length is zero")
                self.parse_errors += 1
                return

            # Extract the raw message bytes
            rawmsg = pkt[offset : offset + hdr.length]

            self.logger.debug("Msg in: len %d. offset %d. type %s. hdr.len %d" %
                (len(pkt), offset, ofp_type_map[hdr.type], hdr.length))
            if hdr.version != OFP_VERSION:
                if self.version_checked is None:
                    self.version_checked = 1
                    self.logger.error("Version %d does not match my version %d"
                                      % (hdr.version, OFP_VERSION))
                    print "Version %d does not match my version %d" % \
                        (hdr.version, OFP_VERSION)
                if not self.no_version_check:
                    self.active = False
                    self.ctrl_socket = None
                    self.kill()

            msg = of_message_parse(rawmsg)
            if not msg:
                self.parse_errors += 1
                self.logger.warn("Could not parse message")
                continue

            # Check if keep alive is set; if so, respond to echo requests
            if hdr.type == OFPT_ECHO_REQUEST:
                if self.keep_alive:
                    self.logger.debug("Responding to echo request")
                    rep = echo_reply()
                    rep.header.xid = hdr.xid
                    # Ignoring additional data
                    self.message_send(rep.pack(), zero_xid=True)
                    offset += hdr.length
                    continue

            # Now check for message handlers; preference is given to
            # handlers for a specific packet
            handled = False
            if hdr.type in self.handlers.keys():
                fn = self.handlers[hdr.type]["fn"]
                cookie = self.handlers[hdr.type]["cookie"]
                handled = fn(cookie, msg, rawmsg)
            if not handled and ("all" in self.handlers.keys()):
                fn = self.handlers["all"]["fn"]
                cookie = self.handlers["all"]["cookie"]
                handled = fn(cookie, msg, rawmsg)

            if not handled: # Not handled, enqueue
                self.packets_discarded += 1
                self.logger.debug("Message discarded")
            else:
                self.packets_handled += 1
                self.logger.debug("Message handled by callback")

            offset += hdr.length

    def _process_socket(self):
        """
        Return False if error reading socket
        Otherwise handle packet
        """
        try:
            pkt = self.ctrl_socket.recv(self.rcv_size)
        except StandardError:
            self.logger.warning("Error on switch read")
            return False

        if len(pkt) == 0:
            self.logger.info("zero-len pkt in")
            return False

        # @todo Handle case of incomplete packet
        self._pkt_handle(pkt)
        return True

    def run(self):
        """
        Activity function for class

        Create connection to controller.
        Listens on socket for messages until an error (or zero len pkt)
        occurs.

        Loop until we get a connection with exponential back-off

        When there is a message on the socket, check for handlers; queue the
        packet if no one handles the packet.
        """

        self.dbg_state = "starting"


        sleep_time = 1
        self.dbg_state = "connecting"
        while self.dbg_state == "connecting" or self.dbg_state == "connected":
            try:
                self.active = False
                # Create socket
                self.logger.info("Create at " + self.host + ":" +
                         str(self.port))
                self.ctrl_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

                self.logger.info("Connecting")
                self.dbg_state = "connecting"
                self.ctrl_socket.connect((self.host, self.port))
                self.logger.info("Connected to " + self.host + " on " +
                                 str(self.port))
                self.dbg_state = "connected"
                sleep_time = 1      # reset connection back-off timer
                self.socs = [self.ctrl_socket]
                while self.active:
                    try:
                        sel_in, sel_out, sel_err = \
                            select.select(self.socs, [], self.socs, 1)
                    except StandardError:
                        print sys.exc_info()
                        self.logger.error("Select error, exiting")
                        sys.exit(1)
                    if self.ctrl_socket in sel_in:
                        if not self._process_socket():
                            self.logger.error("Error reading packet from controller")
                            self.active = False
            except (socket.error), e :
                sleep_time = min(sleep_time * 2, 5)
                print "Got error '%s': sleeping %d seconds and trying again" % (str(e), sleep_time)
            time.sleep(sleep_time)
        self.logger.error("Exiting controller thread");

    def message_send(self, msg, zero_xid=False):
        """
        Send the message to the switch

        @param msg A string or OpenFlow message object to be forwarded to
        the switch.

        @return -1 if error, 0 on success

        """

        if not self.ctrl_socket:
            self.logger.info("message_send: no socket")
            return -1
        # Sending a string indicates the message is ready to go
        # Otherwise, try to pack the message into a string
        if type(msg) != type(""):
            try:
                if msg.header.xid == 0 and not zero_xid:
                    msg.header.xid = gen_xid()
                outpkt = msg.pack()
            except StandardError:
                self.logger.error(
                         "message_send: not an OF message or string?")
                return -1
        else:
            outpkt = msg

        self.logger.debug("Sending pkt of len " + str(len(outpkt)))
        if self.ctrl_socket.sendall(outpkt) is None:
            return 0

        self.logger.error("Unknown error on sendall")
        return -1

    def register(self, msg_type, handler, calling_obj=None, cookie=None):
        """
        Register a callback to receive a specific message type.

        Only one handler may be registered for a given message type.

        WARNING:  A lock is held during the handler call back, so 
        the handler should not make any blocking calls

        @param msg_type The type of message to receive.  May be DEFAULT 
        for all non-handled packets.  The special type, the string "all"
        will send all packets to the handler.
        @param handler The function to call when a message of the given 
        type is received.
        """
        # Should check type is valid
        if not handler and msg_type in self.handlers.keys():
            del self.handlers[msg_type]
            return
        self.handlers[msg_type] = {"fn" : handler, 
                                   "cookie" : cookie}

    def __str__(self):
        string = "Controller Interface:\n"
        string += "  state           " + self.dbg_state + "\n"
        string += "  total pkts      " + str(self.packets_total) + "\n"
        string += "  handled pkts    " + str(self.packets_handled) + "\n"
        string += "  discarded pkts  " + str(self.packets_discarded) + "\n"
        string += "  parse errors    " + str(self.parse_errors) + "\n"
        string += "  host            " + str(self.host) + "\n"
        string += "  port            " + str(self.port) + "\n"
        string += "  keep_alive      " + str(self.keep_alive) + "\n"
        return string

    def show(self):
        print str(self)
