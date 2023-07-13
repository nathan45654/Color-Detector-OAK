# what is the cob_id line 72
# what is self.format line 8*
# create function for finding whether or not the purple color is centered
# create code.py for the M4 feather



from __future__ import annotations

import time
from enum import IntEnum
from struct import pack
from struct import unpack

from farm_ng.canbus import canbus_pb2
# from farm_ng.core.stamp import timestamp_from_monotonic
# from farm_ng.core.timestamp_pb2 import Timestamp

# things I've included
from farm_ng.canbus.packet import Packet



GANTRY_ID = 0x12
# feed rate, x position, y position


class GantryControlState(IntEnum):
    """State of the Amiga vehicle control unit (VCU)"""

    # TODO: add some comments about this states
    STATE_MANUAL_READY = 1
    STATE_MANUAL_ACTIVE = 2
    STATE_AUTO_READY = 3
    STATE_AUTO_ACTIVE = 4
    STATE_ALARM = 5
    STATE_ESTOPPED = 6
    

def make_gantry_rpdo1_proto(
    state_req: GantryControlState, cmd_feed: int, cmd_y: int, cmd_x: int, relative: bool, jog: bool, pto_bits: int = 0x0
    ) -> canbus_pb2.RawCanbusMessage:
    """Creates a canbus_pb2.RawCanbusMessage.

    Uses the AmigaRpdo1 structure and formatting, that can be sent
    directly to the canbus service to be formatted and send on the CAN bus.

    Args:
        state_req: State of the Gantry.
        cmd_feed: Command speed in mm per second.
        cmd_x: x location
        cmd_y: y location
        relative: bool for relative or absolute commands
        jog: bool for $J= or G01 commands

    Returns:
        An instance of a canbus_pb2.RawCanbusMessage.
    """
    # TODO: add some checkers, or make python CHECK_API
    return canbus_pb2.RawCanbusMessage(
        id=GantryRpdo1.cob_id + GANTRY_ID,
        data=GantryRpdo1(
            state_req=state_req,
            cmd_feed=cmd_feed,
            cmd_x=cmd_x,
            cmd_y=cmd_y,
            relative=relative,
            jog=jog,
            pto_bits=pto_bits
        ).encode(),
    )
    
    
class GantryRpdo1(Packet):
    #State, feed, location, relative, and jog (request) sent to the Amiga vehicle control unit (VCU).
    

    cob_id = 0x200

    def __init__(
        self,
        state_req: GantryControlState = GantryControlState.STATE_ESTOPPED,
        cmd_feed: int = 0,
        cmd_x: int = 0,
        cmd_y: int = 0,
        relative: bool = True,
        jog: bool = True,
        pto_bits: int = 0x0
    ):
        self.format = "<BhhBBx"
        self.legacy_format = "<Bhh"

        self.state_req = state_req
        self.cmd_feed = cmd_feed
        self.cmd_x = cmd_x
        self.cmd_y = cmd_y
        self.relative = relative
        self.jog = jog
        self.pto_bits = pto_bits

        self.stamp_packet(time.monotonic())

    def encode(self):
        """Returns the data contained by the class encoded as CAN message data."""
        return pack(
            self.format,
            self.state_req,
            self.cmd_feed,
            self.cmd_x,
            self.cmd_y,
            self.relative,
            self.jog,
            self.pto_bits,
        )

    def decode(self, data):
        """Decodes CAN message data and populates the values of the class."""

        (self.state_req, self.cmd_feed, self.cmd_x, self.cmd_y, self.relative, self.jog, self.pto_bits) = unpack(self.format, data)


    def __str__(self):
        return "Gantry RPDO1 Request state {} Command feed {:x} Command x {:x} Command y {:x}".format(
            self.state_req, self.cmd_feed, self.cmd_x, self.cmd_y
        ) + "  Relative {} Jog {}".format(self.relative, self.jog)

class GantryTpdo1(Packet):
    """State, speed, and angular rate of the Amiga vehicle control unit (VCU).

    New in fw v0.1.9 / farm-ng-amiga v0.0.7: Add pto & hbridge control. Message data is now 8 bytes (was 5).
    """

    cob_id = 0x180

    def __init__(
        self,
        state: GantryControlState = GantryControlState.STATE_ESTOPPED,
        meas_feed: int = 0,
        meas_x: int = 0,
        meas_y: int = 0,
        relative: bool = True,
        jog: bool = True,
        pto_bits: int = 0x0,
    ):
        self.format = "<BhhBBx"
        self.legacy_format = "<Bhh"

        self.state = state
        self.meas_feed = meas_feed
        self.meas_x = meas_x
        self.meas_y = meas_y
        self.relative = relative
        self.jog = jog
        self.pto_bits = pto_bits

        self.stamp_packet(time.monotonic())

    def encode(self):
        """Returns the data contained by the class encoded as CAN message data."""
        return pack(
            self.format,
            self.state,
            self.meas_feed,
            self.meas_x,
            self.relative,
            self.jog,
            self.pto_bits,
        )

    def decode(self, data):
        """Decodes CAN message data and populates the values of the class."""
        (self.state, self.meas_feed, self.meas_x, self.meas_y, self.pto_bits, self.hbridge_bits) = unpack(self.format, data)


    def __str__(self):
        return "Gantry TPDO1 Amiga state {} Measured feed {:x} Measured x {:x} Measured y{:x} @ time {}".format(
            self.state, self.meas_feed, self.meas_x, self.meas_y, self.stamp.stamp
        ) + "  Relative {} Jog {}".format(self.relative, self.jog)
        
def parse_gantry_tpdo1_proto(message: canbus_pb2.RawCanbusMessage) -> GantryTpdo1 | None:
    #Parses a canbus_pb2.RawCanbusMessage.

    if message.id != GantryTpdo1.cob_id + GANTRY_ID:
        return None
    return GantryTpdo1.from_can_data(message.data, stamp=message.stamp)

