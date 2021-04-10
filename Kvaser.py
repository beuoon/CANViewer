# Kvaser 관련 lib
from canlib import canlib
from canlib.canlib import ChannelData
from canlib.canlib import exceptions


class Kvaser:
    def __init__(self, channel=0):
        self.channel = channel
        self.openFlags = canlib.canOPEN_ACCEPT_VIRTUAL
        self.bitrate = canlib.canBITRATE_500K
        self.bitrateFlags = canlib.canDRIVER_NORMAL

        self.valid = False
        self.ch = None
        self.device_name = ''
        self.card_upc_no = ''
        try:
            ch = canlib.openChannel(self.channel, self.openFlags)
            ch.setBusOutputControl(self.bitrateFlags)
            ch.setBusParams(self.bitrate)
            ch.iocontrol.timer_scale = 1
            ch.iocontrol.local_txecho = True
            ch.busOn()
        except exceptions.CanGeneralError:
            self.valid = False
            self.ch = None
        else:
            self.valid = True
            self.ch = ch
            self.device_name = ChannelData.channel_name
            self.card_upc_no = ChannelData(self.channel).card_upc_no

        if self.card_upc_no == '00-00000-00000-0':
            print('Virtual CAN 모드입니다.')

    def __del__(self):
        if self.ch:
            try:
                self.tearDownChannel()
            except:
                pass

    def read(self, timeout_ms=0):
        return self.ch.read(timeout=timeout_ms)

    def __iter__(self):
        while True:
            try:
                frame = self.ch.read()
                yield frame
            except canlib.canNoMsg:
                yield 0
            except canlib.canError:
                return

    def tearDownChannel(self):
        self.ch.busOff()
        self.ch.close()
