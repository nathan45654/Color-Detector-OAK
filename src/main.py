# Copyright (c) farm-ng, inc.
#
# Licensed under the Amiga Development Kit License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://github.com/farm-ng/amiga-dev-kit/blob/main/LICENSE
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# To do:
# get all of the Tpdo and Rpdo good. Draw a diagram please so you get it right
# get the depth and color cameras working in sync


import argparse
import asyncio
import os
from typing import List
from typing import Optional

import grpc


# canbus things
from farm_ng.canbus import canbus_pb2
from farm_ng.canbus.canbus_client import CanbusClient
from farm_ng.canbus.packet import AmigaControlState
from farm_ng.canbus.packet import AmigaTpdo1
# from farm_ng.canbus.packet import make_amiga_rpdo1_proto
from farm_ng.canbus.packet import parse_amiga_tpdo1_proto

# camera things
from farm_ng.oak import oak_pb2
from farm_ng.oak.camera_client import OakCameraClient
from farm_ng.service import service_pb2
from farm_ng.service.service_client import ClientConfig
import turbojpeg

# things I've added #
from gantry import GantryControlState
from gantry import GantryTpdo1
from gantry import make_gantry_rpdo1_proto
from gantry import parse_gantry_tpdo1_proto

import cv2
import numpy as np
#----#

os.environ["KIVY_NO_ARGS"] = "1"


from kivy.config import Config  # noreorder # noqa: E402

Config.set("graphics", "resizable", False)
Config.set("graphics", "width", "1280")
Config.set("graphics", "height", "800")
Config.set("graphics", "fullscreen", "false")
Config.set("input", "mouse", "mouse,disable_on_activity")
Config.set("kivy", "keyboard_mode", "systemanddock")

from kivy.app import App  # noqa: E402
from kivy.lang.builder import Builder  # noqa: E402
from kivy.graphics.texture import Texture  # noqa: E402


class CameraColorApp(App):
    def __init__(self, address: str, camera_port: int, canbus_port: int, stream_every_n: int) -> None:
        super().__init__()
        self.address: str = address
        self.camera_port : int = camera_port
        self.canbus_port: int = canbus_port
        self.stream_every_n = stream_every_n
        
        self.amiga_tpdo1: AmigaTpdo1 = AmigaTpdo1()
        self.amiga_state = AmigaControlState.STATE_AUTO_READY
        self.amiga_rate = 0
        self.amiga_speed = 0
        
        self.gantry_tpdo1: GantryTpdo1 = GantryTpdo1()
        self.gantry_state = GantryControlState.STATE_AUTO_READY
        self.gantry_x = 0
        self.gantry_y = 0
        self.gantry_feed = 1000
        self.gantry_jog = 1

        self.image_decoder = turbojpeg.TurboJPEG()
        
        self.tasks: List[asyncio.Task] = []

    def build(self):
        return Builder.load_file("res/main.kv")

    def on_exit_btn(self) -> None:
        """Kills the running kivy application."""
        App.get_running_app().stop()

    async def app_func(self):
        async def run_wrapper():
            # we don't actually need to set asyncio as the lib because it is
            # the default, but it doesn't hurt to be explicit
            await self.async_run(async_lib="asyncio")
            for task in self.tasks:
                task.cancel()

        # configure the camera client
        camera_config: ClientConfig = ClientConfig(
            address=self.address, port=self.camera_port
        )
        camera_client: OakCameraClient = OakCameraClient(camera_config)

        # configure the canbus client
        canbus_config: ClientConfig = ClientConfig(
            address=self.address, port=self.canbus_port
        )
        canbus_client: CanbusClient = CanbusClient(canbus_config)

        # Camera task(s)
        self.tasks.append(
            asyncio.ensure_future(self.stream_camera(camera_client))
        )

        # Canbus task(s)
        self.tasks.append(
            asyncio.ensure_future(self.stream_canbus(canbus_client))
        )
        self.tasks.append(
            asyncio.ensure_future(self.send_can_msgs(canbus_client))
        )


        return await asyncio.gather(run_wrapper(), *self.tasks)


    async def stream_canbus(self, client: CanbusClient) -> None:
        """This task:

        - listens to the canbus client's stream
        - filters for AmigaTpdo1 messages
        - extracts useful values from AmigaTpdo1 messages
        """
        while self.root is None:
            await asyncio.sleep(0.01)

        response_stream = None

        while True:
            # check the state of the service
            state = await client.get_state()

            if state.value not in [
                service_pb2.ServiceState.IDLE,
                service_pb2.ServiceState.RUNNING,
            ]:
                if response_stream is not None:
                    response_stream.cancel()
                    response_stream = None

                print("Canbus service is not streaming or ready to stream")
                await asyncio.sleep(0.1)
                continue

            if (
                response_stream is None
                and state.value != service_pb2.ServiceState.UNAVAILABLE
            ):
                # get the streaming object
                response_stream = client.stream_raw()
                # pass

            try:
                # try/except so app doesn't crash on killed service
                response: canbus_pb2.StreamCanbusReply = await response_stream.read()
                assert response and response != grpc.aio.EOF, "End of stream"
            except Exception as e:
                print(e)
                response_stream.cancel()
                response_stream = None
                continue

            for proto in response.messages.messages:
                # Check if message is for the dashboard
                amiga_tpdo1: Optional[AmigaTpdo1] = parse_amiga_tpdo1_proto(proto)
                if amiga_tpdo1:
                    # Store the value for possible other uses
                    self.amiga_tpdo1 = amiga_tpdo1

                    # Update the Label values as they are received
                    self.amiga_state = AmigaControlState(amiga_tpdo1.state).name[6:]
                    
                    self.amiga_speed = amiga_tpdo1.meas_speed
                    self.amiga_rate = amiga_tpdo1.meas_ang_rate
                    
                # Check if message is for the gantry
                gantry_tpdo1: Optional[GantryTpdo1] = parse_gantry_tpdo1_proto(proto)
                if gantry_tpdo1:
                    # Store the value for possible other uses
                    self.gantry_tpdo1 = gantry_tpdo1
                    
                    # Update the Label values as they are received
                    self.gantry_state = self.amiga_state
                    self.gantry_feed = gantry_tpdo1.meas_feed
                    self.gantry_x = gantry_tpdo1.meas_x
                    self.gantry_y = gantry_tpdo1.meas_y
                    self.gantry_jog = gantry_tpdo1.jog
                    

    async def stream_camera(self, client: OakCameraClient) -> None:
        """This task listens to the camera client's stream and populates the tabbed panel with all 4 image streams
        from the oak camera."""
        while self.root is None:
            await asyncio.sleep(0.01)

        response_stream = None

        while True:
            # check the state of the service
            state = await client.get_state()

            if state.value not in [
                service_pb2.ServiceState.IDLE,
                service_pb2.ServiceState.RUNNING,
            ]:
                # Cancel existing stream, if it exists
                if response_stream is not None:
                    response_stream.cancel()
                    response_stream = None
                print("Camera service is not streaming or ready to stream")
                await asyncio.sleep(0.1)
                continue

            # Create the stream
            if response_stream is None:
                response_stream = client.stream_frames(every_n=self.stream_every_n)

            try:
                # try/except so app doesn't crash on killed service
                response: oak_pb2.StreamFramesReply = await response_stream.read()
                assert response and response != grpc.aio.EOF, "End of stream"
            except Exception as e:
                print(e)
                response_stream.cancel()
                response_stream = None
                continue

            # get the sync frame
            frame: oak_pb2.OakSyncFrame = response.frame

            # get image and show
            for view_name in ["rgb", "disparity", "left", "right"]:
                # Skip if view_name was not included in frame
                try:
                    # Decode the image and render it in the correct kivy texture
                    
                    
                    #----------rgb and purple filtering----------#
                    if view_name == 'rgb':
                        img = self.image_decoder.decode(
                            getattr(frame, view_name).image_data
                        )
                        
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

                        purple_lower = np.array([120,70,50])
                        purple_upper = np.array([135,255,255])
                        purple_amount = 400
                        purple_full_mask = cv2.inRange(img, purple_lower, purple_upper)
                        rgb_size = (img.shape[1],img.shape[0])                        
                        
                        #//////////// calculate the middle of all purple, set gantry_x and gantry_y to location of blob center
                        # calculate moments of binary image
                        cX = None
                        cY = None
                        if np.count_nonzero(purple_full_mask) >= purple_amount:
                            ret,thresh = cv2.threshold(purple_full_mask,127,255,0)
        
                            # calculate moments of binary image
                            M = cv2.moments(thresh)
                            
                            # calculate x,y coordinate of center
                            cX = int(M["m10"] / M["m00"])
                            cY = int(M["m01"] / M["m00"])
                        #////////////
                        
                        
                        img = cv2.bitwise_and(img, img, mask=purple_full_mask)
                        img = cv2.cvtColor(img,cv2.COLOR_HSV2BGR) 
                        
                        
                        # #######
                        # # put text and highlight the center
                        if cX and cY:
                            cv2.circle(img, (cX, cY), 5, (255, 255, 255), -1)
                            text = "centroid: " + str(cX) + " " + str(cY)
                            cv2.putText(img, text, (cX - 25, cY - 25),cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                        # #######    
                        
                        # disparity_img = self.image_decoder.decode(
                        #     getattr(frame, "disparity").image_data
                        # )
                        # # disparity_img = cv2.resize(disparity_img,(img.shape[1], img.shape[0]))
                        # #-----#
                        # # put text and highlight the center
                        # if cX and cY:
                        #     cv2.circle(img, (cX, cY), 5, (255, 255, 255), -1)
                        #     text = "Center: " + str(disparity_img[10][10][1])
                        #     cv2.putText(img, text, (cX - 25, cY - 25),cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                        #-----#
                        
                    elif view_name == "disparity":
                        
                        img = disparity_img
                        img = cv2.resize(img,rgb_size)
                        # if cX and cY:
                            # text = "Distance: " + str(img[cY])
                            # cv2.circle(frame, (cX, cY), 5, (255, 255, 255), -1)
                            # cv2.putText(img, text, (cX - 25, cY - 25),cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                    else:
                        img = self.image_decoder.decode(
                            getattr(frame, view_name).image_data
                        )
                        
                        
                        
                        
                    #----------end of my custom code----------#
                    
                    texture = Texture.create(
                        size=(img.shape[1], img.shape[0]), icolorfmt="bgr"
                    )
                    texture.flip_vertical()
                    texture.blit_buffer(
                        img.tobytes(),
                        colorfmt="bgr",
                        bufferfmt="ubyte",
                        mipmap_generation=False,
                    )
                    self.root.ids[view_name].texture = texture

                except Exception as e:
                    print(e)
                    
    async def send_can_msgs(self, client: CanbusClient) -> None:
        """This task ensures the canbus client sendCanbusMessage method has the pose_generator it will use to send
        messages on the CAN bus to control the Amiga robot."""
        while self.root is None:
            await asyncio.sleep(0.01)

        response_stream = None
        while True:
            # check the state of the service
            state = await client.get_state()

            # Wait for a running CAN bus service
            if state.value != service_pb2.ServiceState.RUNNING:
                # Cancel existing stream, if it exists
                if response_stream is not None:
                    response_stream.cancel()
                    response_stream = None
                print("Waiting for running canbus service...")
                await asyncio.sleep(0.1)
                continue

            if response_stream is None:
                print("Start sending CAN messages")
                response_stream = client.stub.sendCanbusMessage(self.pose_generator())

            '''
            # This isn't working
            try:
                async for response in response_stream:
                    # Sit in this loop and wait until canbus service reports back it is not sending
                    assert response.success
            except Exception as e:
                print(e)
                response_stream.cancel()
                response_stream = None
                continue
            '''
            

            await asyncio.sleep(0.1)

#// this is where you will determine whether or not to move the gantry based on the purple color sent.
    async def pose_generator(self, period: float = 0.02):
        """The pose generator yields an AmigaRpdo1 (auto control command) for the canbus client to send on the bus
        at the specified period (recommended 50hz) based on the onscreen joystick position."""
        while self.root is None:
            await asyncio.sleep(0.01)
        #// put the x and y coordinate and feed stuff right here
        while True:
            msg: canbus_pb2.RawCanbusMessage = make_gantry_rpdo1_proto(
                state_req = GantryControlState.STATE_AUTO_ACTIVE,
                cmd_feed = self.gantry_feed,
                cmd_x = self.gantry_x,
                cmd_y = self.gantry_y,
                jog = self.gantry_jog
            )
            yield canbus_pb2.SendCanbusMessageRequest(message=msg)
            await asyncio.sleep(period)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="color-detector-oak")
    parser.add_argument(
        "--address", type=str, default="localhost", help="The server address"
    )
    parser.add_argument(
        "--camera-port",
        type=int,
        required=True,
        help="The grpc port where the camera service is running.",
    )
    parser.add_argument(
        "--canbus-port",
        type=int,
        required=True,
        help="The grpc port where the canbus service is running.",
    )    
    # parser.add_argument(
    #     "--address", type=str, default="localhost", help="The camera address"
    # )
    parser.add_argument(
        "--stream-every-n", 
        type=int, 
        default=1, 
        help="Streaming frequency"
    )
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(
            CameraColorApp(args.address, args.camera_port, args.canbus_port, args.stream_every_n).app_func()
        )
    except asyncio.CancelledError:
        pass
    loop.close()
    