# Kvaser 관련 lib
from canlib import canlib, Frame
from canlib.canlib import ChannelData
from canlib.canlib import exceptions

# Python built-in lib
import time
import os
import datetime
import signal
import socket
from random import randint

# External lib
from tqdm import tqdm

# todo: 다른 외부 라이브러리 사용 시 기재
# import ...


## 1. Kvaser 연결 정보(채널확인 및 KVASER 넘버 확인) class
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
        except exceptions.CanGeneralError as error:
            self.valid = False
            self.ch = None
        else:
            self.valid = True
            self.ch = ch
            self.device_name = ChannelData.channel_name
            self.card_upc_no = ChannelData(self.channel).card_upc_no

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
            except (canlib.canNoMsg) as ex:
                yield 0
            except (canlib.canError) as ex:
                return

    def tearDownChannel(self):
        self.ch.busOff()
        self.ch.close()


## 2. CAN 메시지 전송 class
class Transmitter:
    def __init__(self):
        self.package_root = os.path.dirname(os.path.realpath(__file__))
        self.threads = []
        self.kvaser = Kvaser(channel=0)
        if not self.kvaser.valid:
            print('Kvaser가 연결되지 않았습니다.')
            os._exit(-1)
        if self.kvaser.card_upc_no == '00-00000-00000-0':
            print('Virtual CAN이 대신 선택되었습니다. 디버그 모드입니다.')
        elif self.kvaser.card_upc_no not in ['73-30130-00351-4', '73-30130-00752-9']:
            print('현재 선택된 채널 %d은(는) 테스트베드 Kvaser를 가리키고 있지 않습니다.' % self.kvaser.channel)

    def mkdata(self, string):             # 16진수로 자동 변환
        new_list = []
        for hex in string.split():
            new_list.append(int(hex, 16))
        return new_list

    def transmit_data(self, id: int, data: str, dlc=None, msgFlag=canlib.canMSG_STD,
                      interMsgTime: float=0.01, nMsg: int=300):
        #       id : 16진수, Arbitration ID(목적 ECU ID)
        #       data : 16진수를 string으로 기재(각 byte 사이는 띄워쓰기), mkdata 함수가 입력 포맷에 맞게 변환
        #       *dlc : 데이터 길이, 입력하지 않아도 data 입력에 따라 자동 설정됨, 실제 data 입력 크기 보다 작을경우 지정 숫자에 따라 잘림
        #       *msgFlag : 프레임 설정(canlib.canMSG_STD : 일반, canlib.canMSG_RTR : 리모트, canMSG_ERROR_FRAME : 에러), 확장프레임 제공 X
        #       interMsgTime : 전송할 메시지 사이에 쉬는 간격 (초)
        #       nMsg : 전송할 총 메시지 수

        ch = Kvaser(channel=0)
        # CAN frame 생성
        if dlc:
            frame = Frame(id_=id, data=self.mkdata(data), dlc=dlc, flags=msgFlag)
        else:
            frame = Frame(id_=id, data=self.mkdata(data), flags=msgFlag)
        # 전송할 record 콘솔에 출력
        record = '0x{:03X}\t{}\t'.format(frame.id, frame.dlc)
        record += ' '.join(['{:02X}'.format(val) for val in frame.data])
        print(record)

        for i in tqdm(range(nMsg)):
            # ch에 CAN 데이터 전송
            while True:
                # 1ms 단위로 precise하게 시간 딜레이 주기 (초당 몇~몇십 개 정도의 오차는 발생함)
                delay = time.perf_counter() + interMsgTime
                while time.perf_counter() < delay:
                    pass
                try:
                    self.kvaser.ch.write(frame)
                except canlib.exceptions.CanGeneralError:
                    continue
                else:
                    break


## 3. CAN read/dump class
class Extractor:        # Extractor : 추출 위함 Kvaser 설정(연결, 캡쳐 정보 포함)
    def __init__(self):
        self.package_root = os.path.dirname(os.path.realpath(__file__))
        self.carID = 'CN7'
        self.threads = []
        self.kvaser = Kvaser(channel=0)
        if not self.kvaser.valid:
            print('Kvaser가 연결되지 않았습니다.')
            os._exit(-1)
        if self.kvaser.card_upc_no == '00-00000-00000-0':
            print('Virtual CAN이 대신 선택되었습니다. 디버그 모드입니다.')
        elif self.kvaser.card_upc_no not in ['73-30130-00351-4', '73-30130-00752-9']:
            print('현재 선택된 채널 %d은(는) 테스트베드 Kvaser를 가리키고 있지 않습니다.' % self.kvaser.channel)
            
        HOST = '127.0.0.1'
        PORT = 45555

        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.connect((HOST, PORT))

    def make_drive_record(self):        #  차량 CAN 데이터 수집
        print('*** 데이터 수집 ***')
        self.carID = 'CN7'
        self.idx_db = None
        now = datetime.datetime.now()
        ts_start = now.strftime('%Y-%m-%d %H:%M:%S')
        self.ts_start = datetime.datetime.strptime(ts_start, "%Y-%m-%d %H:%M:%S")
        print('캡쳐 시작 시각: {}'.format(self.idx_db, self.ts_start))

        # 저장 경로 및 폴더명 설정, ./dump/ 저장
        # 수집 시작 '날짜_시간_차량명'폴더명으로 저장됨
        folder_name = '{}/dump/{}_{}'.format(self.package_root, self.ts_start.strftime("%Y%m%d_%H%M%S"), self.carID)
        os.mkdir(folder_name)

        print('주행을 종료하려면 반드시 Ctrl+C를 누르세요. CMD 창에서 실행시키는 것을 권장합니다.')
        print('IDE에서 실행(Run)할 경우 Ctrl+C로 중단되지 않을 수 있습니다. 이 경우 대다수 데이터는 제대로 저장되나 마지막 1초 가량의 데이터가 저장되지 않을 수 있습니다.')
        print('***\n')

        self.record_canmsg(folder_name)

        with open('{}/{}'.format(folder_name, '0_information.txt'), 'wt') as fp_info:        # 저장 경로 및 폴더명 설정, ./dump/ 저장, 수집 시
            fp_info.write('*** Information ***\n')
            fp_info.write('The capture was started at {} KST\n'.format(self.ts_start.strftime("%Y-%m-%d %H:%M:%S")))
            fp_info.write('Thank you.\n\n2020 Hacking and Countermeasure Research Lab., Korea University\n')

    def record_canmsg(self, folder_name):         # Kvaser 데이터 dump
        global ready_to_exit        # 시그널로 인한 전역변수 변화를 관찰하기 위해 글로벌 선언
        fp_can = open('{}/{}'.format(folder_name, '1_candump.txt'), 'wt')       # ./dump/'실행 시간 폴더'/에 1_candump.txt로 기록
        fp_can.write(','.join(['Timestamp', 'Arbitration_ID', 'DLC', 'Data']) + '\n')   # Timestamp, ID, DLC, DATA 기록

        for frame in self.kvaser:
            if ready_to_exit:
                break               # 시그널이 입력되었으면 루틴을 빠져나감
            elif frame == 0:
                continue
            elif frame is None:     # error 체크
                break
            record = '{},{:03X},{},'.format(frame.timestamp / 1000000, frame.id, frame.dlc)
            record += ' '.join(['{:02X}'.format(val) for val in frame.data])
            
            self.client_socket.sendall((record + '\n').encode())

            print(record)                   # todo: 너무 느리거나 수집된 메시지를 콘솔에는 출력하고 싶지 않을 경우 주석 처리
            # if frame.id == 0x130:           # 원하는 ID만 출력하도록 필터 넣기 가능
            #     print(record)
            fp_can.write(record + '\n')
            fp_can.flush()                  # todo: 하드디스크가 너무 느리면 주석 처리하기
        fp_can.close()                      # can통신 종료

    def stop_collecting(self):              # 데이터 추출 종료
        for thread in self.threads:
            thread.join()
        now = datetime.datetime.now()
        ts_end = now.strftime('%Y-%m-%d %H:%M:%S')
        return datetime.datetime.strptime(ts_end, "%Y-%m-%d %H:%M:%S")


ready_to_exit = False
ts_end = None

def handler(signum, frame):
    global ready_to_exit, ts_end
    if signum == signal.SIGINT:
        if not ready_to_exit:
            ts_end = extractor.stop_collecting()
            ready_to_exit = True


if __name__ == '__main__':
    os.system('cls')

    # %%
    # 1. CAN 메시지 주입 (*는 optional)
    #       id : 16진수, Arbitration(목적 ECU ID 등)
    #       data : 16진수를 string으로 기재(각 byte 사이는 띄워쓰기), mkdata 함수가 입력 포맷에 맞게 변환
    #       *dlc : 데이터 길이, 실제 data 입력 크기 보다 작을경우 지정 숫자에 따라 잘림
    #              (default: 입력하지 않아도 입력한 data 길이에 따라 자동 설정됨)
    #       *msgFlag : 프레임 설정 (확장프레임 제공 X)
    #                  - canlib.MessageFlag.STD : 일반, canlib.MessageFlag.RTR : 리모트, canlib.MessageFlag.ERROR_FRAME : 에러
    #                  (default: canlib.MessageFlag.STD)
    #       interMsgTime : 전송할 메시지 사이에 쉬는 간격 (초)
    #       nMsg : 전송할 총 메시지 수
    Transmitter().transmit_data(id=0x366, data='00 00 00 00 00 00 00 00', dlc=8, msgFlag=canlib.MessageFlag.STD,
                                interMsgTime=0.0005, nMsg=2000)

    # %%
    # 2. CAN 트래픽 덤프 (dump 폴더에 저장됨)
    signal.signal(signal.SIGINT, handler)   # Ctrl+C를 입력해 정상적으로 dump 중단하기 위해 필요

    print('*** 주행 정보 ***\n주행 데이터가 업데이트되지 않으면, 데이터가 수집되지 않는 것입니다.\n')
    print('*** 데이터 출력 시 Timestamp가 실제 시간에 비해 느리게 증가한다면,\n'
          'records_canmsg 함수 내 print(record)를 주석 처리하여 보시기 바랍니다.')
    extractor = Extractor()
    extractor.make_drive_record()
    print('추출 종료 시각: {}\n추출기는 에러 없이 정상 종료되었습니다.'.format(ts_end))
