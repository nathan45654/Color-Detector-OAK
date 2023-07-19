# what is the cob_id line 72
# what is self.format line 8*
# create function for finding whether or not the purple color is centered
# create code.py for the M4 feather



from __future__ import annotations

import time
from struct import pack
from struct import unpack

from farm_ng.canbus import canbus_pb2
# from farm_ng.core.stamp import timestamp_from_monotonic
# from farm_ng.core.timestamp_pb2 import Timestamp

# things I've included
from farm_ng.canbus.packet import Packet



GANTRY_ID = 0x12
# feed rate, x position, y position


class GantryControlState:
    """State of the Amiga vehicle control unit (VCU)"""

    # TODO: add some comments about this states
    STATE_MANUAL_READY = 1
    STATE_MANUAL_ACTIVE = 2
    STATE_AUTO_READY = 3
    STATE_AUTO_ACTIVE = 4
    STATE_ALARM = 5
    STATE_ESTOPPED = 6
    

def make_gantry_rpdo1_proto(R_y: int, R_x: int
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
            R_x=R_x,
            R_y=R_y,
            ).encode(),
    )
    
#/////////////
class GantryRpdo1(Packet):
    #State, feed, location sent to the Amiga vehicle control unit (VCU).
    

    cob_id = 0x200

    def __init__(
        self,
        R_state: GantryControlState = GantryControlState.STATE_ESTOPPED,
        R_x: int = 0,
        R_y: int = 0
    ):
        self.format = '<2I'

        # self.R_state = R_state
        self.R_x = R_x
        self.R_y = R_y

        self.stamp()

    def encode(self):
        """Returns the data contained by the class encoded as CAN message data."""
        return pack(
            self.format, 
            self.R_x, 
            self.R_y
        )

    def decode(self, data):
        """Decodes CAN message data and populates the values of the class."""

        (self.R_x, self.R_y) = unpack(self.format, data)


    def __str__(self):
        return "Gantry Rpdo1 R state {} R x {:x} R y {:x}".format(
            self.R_x, self.R_y)
#/////////////

#/////////////
class GantryTpdo1(Packet):
    """State, speed, and angular rate of the Amiga vehicle control unit (VCU).

    New in fw v0.1.9 / farm-ng-amiga v0.0.7: Add pto & hbridge control. Message data is now 8 bytes (was 5).
    """

    cob_id = 0x180

    def __init__(
        self,
        T_state: GantryControlState = GantryControlState.STATE_ESTOPPED,
        T_x: int = 0,
        T_y: int = 0,
    ):
        self.format = str("<2I")

        # self.T_state = T_state
        self.T_x = T_x
        self.T_y = T_y

        self.stamp()

    def encode(self):
        """Returns the data contained by the class encoded as CAN message data."""
        return pack(
            self.format,
            # self.T_state,
            self.T_x,
            self.T_y
        )

    def decode(self, data):
        """Decodes CAN message data and populates the values of the class."""
        (self.T_x, self.T_y) = unpack(self.format, data)


    def __str__(self):
        return "Gantry Tpdo1 T_state {} T x {:x} T y{:x} @ time {}".format(
            self.T_x, self.T_y, self.stamp)
#/////////////
    
def parse_gantry_tpdo1_proto(message: canbus_pb2.RawCanbusMessage) -> GantryTpdo1 | None:
    #Parses a canbus_pb2.RawCanbusMessage.

    if message.id != GantryTpdo1.cob_id + GANTRY_ID:
        return None
    return GantryTpdo1.from_can_data(message.data, stamp=message.stamp)

