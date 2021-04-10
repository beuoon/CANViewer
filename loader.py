from Kvaser import Kvaser
from canlib import canlib, Frame
from tqdm import tqdm
import pandas as pd
import time
import sys
import msvcrt


class KvaserSender:
    def __init__(self):
        self.bStop = False
        self.startTime = 0
        self.stopTime = 0

    @staticmethod
    def convert_str_to_hex(data):
        new_list = []
        for byte in data.split():
            new_list.append(int(byte, 16))
        return new_list

    def keyPress(self):
        if not msvcrt.kbhit():
            return
        key = msvcrt.getch()

        if key == b' ':
            if not self.bStop:
                self.stopTime = time.perf_counter()
            else:
                self.startTime = time.perf_counter() - (self.stopTime - self.startTime)

            self.bStop = not self.bStop

    def run(self, csv_path):
        # Kvaser 생성
        kvaser = Kvaser(channel=0)
        if not kvaser.valid:
            return

        # 파일 불러오기
        df = pd.read_csv(csv_path)
        df = df.dropna()
        values = df.values

        self.startTime = 0  # time.perf_counter()
        start_timestamp = values[0][0]

        # 진행
        for packet in tqdm(values):
            # Key 입력
            self.keyPress()
            if self.bStop:
                time.sleep(0.1)
                continue

            time_stamp = packet[0]
            id = int('0x'+packet[1], 16)
            dlc = packet[2]
            data = KvaserSender.convert_str_to_hex(packet[3])

            frame = Frame(id_=id, data=data, dlc=dlc, flags=canlib.canMSG_STD)

            # Delay
            while time.perf_counter() - self.startTime < (time_stamp - start_timestamp):
                continue

            # Send
            while True:
                try:
                    kvaser.ch.write(frame)
                except canlib.exceptions.CanGeneralError:
                    continue
                else:
                    break


if __name__ == '__main__':
    # Parsing Path Argument
    if len(sys.argv) < 2:
        print('need dataset file')
        exit(1)

    arg_csv_path = sys.argv[1]
    sender = KvaserSender()
    sender.run(arg_csv_path)
