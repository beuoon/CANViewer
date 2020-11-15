from tqdm import tqdm
from socket import *
import pandas as pd
import threading
import datetime
import time
import sys
import msvcrt


class FileLoader:
    def __init__(self, file_path, save_path, run_speed):
        self.HOST = '127.0.0.1'
        self.VIEWER_PORT = 45555
        self.ATTACK_PORT = 45556
        self.ATTACKER_VIEW_PORT = 45557
        self.BUFF_SIZE = 8192

        self.viewer_socket = socket(AF_INET, SOCK_STREAM)
        self.viewer_socket.connect((self.HOST, self.VIEWER_PORT))

        self.attackServerSocket = socket(AF_INET, SOCK_STREAM)
        self.attackServerSocket.bind((self.HOST, self.ATTACK_PORT))
        self.attackServerSocket.listen(1)

        self.attackSocket = None
        self.attackerViewSocket = None
        self.recvThread = threading.Thread(target=FileLoader.RecvFunc, args=(self,))
        self.recvDataList = []

        self.csvPath = file_path
        self.savePath = save_path
        self.runSpeed = run_speed

        self.bRun = False
        self.bStop = False
        self.startTime = 0
        self.stopTime = 0

    @staticmethod
    def RecvFunc(file_loader):
        prev_data = ''

        while file_loader.bRun:
            try:
                encoded_packet = file_loader.attackSocket.recv(file_loader.BUFF_SIZE)
                if encoded_packet == b'':
                    raise Exception('closed')

                packet = encoded_packet.decode()
                data_list = packet.splitlines()

                if len(data_list) == 0:
                    continue

                data_list[0] = prev_data + data_list[0]
                prev_data = ''

                for data in data_list[:-1]:
                    msg = data.split(',')
                    file_loader.recvDataList.append(msg)

                data = data_list[-1]
                if packet[-1] != '\n':
                    prev_data = data
                else:
                    msg = data.split(',')
                    file_loader.recvDataList.append(msg)

            except:
                viewSocket = file_loader.attackerViewSocket
                file_loader.attackerViewSocket = None
                if viewSocket is not None:
                    viewSocket.close()

                if file_loader.attackSocket is not None:
                    file_loader.attackSocket.close()
                file_loader.attackSocket = None

                try:
                    file_loader.attackSocket, _ = file_loader.attackServerSocket.accept()

                    viewSocket = socket(AF_INET, SOCK_STREAM)
                    viewSocket.connect((file_loader.HOST, file_loader.ATTACKER_VIEW_PORT))
                    file_loader.attackerViewSocket = viewSocket
                except:
                    pass

    def keyPress(self):
        while self.bRun:
            if msvcrt.kbhit():
                key = msvcrt.getch()
            else:
                time.sleep(0.001)
                continue

            if key == b' ':
                if not self.bStop:
                    self.stopTime = time.perf_counter()
                else:
                    self.startTime = time.perf_counter() - (self.stopTime - self.startTime)

                self.bStop = not self.bStop

    def run(self):
        if self.csvPath is None:
            return
        df = pd.read_csv(self.csvPath)
        df = df.dropna()

        values = df.values

        base_file = None
        # submit_file = None
        # answer_file = None
        if self.savePath is not None:
            try:
                ts = datetime.datetime.now().strftime('%Y%m%d_%H.%M.%S')

                base_file = open(self.savePath + '_' + ts + '.csv', 'wt')
                base_file.write('Number,Timestamp,Arbitration_ID,DLC,Data,Class\n')
                # submit_file = open(self.savePath + '_' + ts + '-Submit.csv', 'wt')
                # submit_file.write('Number,Timestamp,Arbitration_ID,DLC,Data\n')
                #
                # answer_file = open(self.savePath + '_' + ts + '-Answer.csv', 'wt')
                # answer_file.write('Number,Class\n')

            except Exception as e:
                print(e)
                self.attackServerSocket.close()
                return

        # 시작
        self.bRun = True
        self.recvThread.start()
        t = threading.Thread(target=self.keyPress)
        t.start()

        values_len = len(values)
        pbar = tqdm(total=values_len)

        self.startTime = time.perf_counter()
        start_timestamp = values[0][0]
        idx = 0
        number = 0

        while idx < values_len:
            if self.bStop:
                time.sleep(0.1)
                continue

            current_time = time.perf_counter()

            value = None
            dataClass = 'Normal'

            # 파일에서 가져오기
            if current_time - self.startTime >= (values[idx][0] - start_timestamp) / self.runSpeed:
                value = values[idx]

                pbar.update(1)
                idx += 1
            # 소켓에서 가져오기
            else:
                if len(self.recvDataList) > 0:
                    value = self.recvDataList[0]
                    dataClass = 'Attack'
                    self.recvDataList = self.recvDataList[1:]

            # 전송
            if value is not None:
                data = '{},{},{},{},{}\n'.format(current_time - self.startTime, value[1], value[2], value[3], dataClass)
                encoded_data = data.encode()

                try:
                    self.viewer_socket.sendall(encoded_data)
                except Exception as e:
                    break

                if self.attackerViewSocket is not None:
                    try:
                        self.attackerViewSocket.sendall(encoded_data)
                    except Exception as e:
                        self.attackerViewSocket = None
                if base_file is not None:
                    base_data = '{},{:.7f},{},{},{},{}\n'.format(number, current_time - self.startTime, value[1], value[2], value[3], dataClass)
                    # submit_data = '{},{:.7f},{},{},{}\n'.format(number, current_time - self.startTime, value[1], value[2], value[3])
                    # answer_data = '{},{}\n'.format(number, dataClass)
                    number += 1

                    base_file.write(base_data)
                    base_file.flush()

                    # submit_file.write(submit_data)
                    # submit_file.flush()
                    #
                    # answer_file.write(answer_data)
                    # answer_file.flush()

        # 종료
        pbar.close()
        print("종료")
        if base_file is not None:
            base_file.close()
            # submit_file.close()
            # answer_file.close()

        self.bRun = False
        self.attackServerSocket.close()
        if self.attackSocket is not None:
            self.attackSocket.close()


if __name__ == '__main__':
    # Parsing Path Argument
    if len(sys.argv) < 2:
        print('need dataset file')
        exit(1)
    arg_file_path = sys.argv[1]

    # Parsing Run Speed Argument
    if len(sys.argv) >= 3:
        arg_run_speed = float(sys.argv[2])
    else:
        arg_run_speed = 1

    # Parsing Save Path Argument
    if len(sys.argv) >= 4:
        arg_save_path = sys.argv[3]
    else:
        arg_save_path = None

    loader = FileLoader(arg_file_path, arg_save_path, arg_run_speed)

    try:
        loader.run()
    except:
        loader.bRun = False
        if loader.attackSocket is not None:
            loader.attackSocket.close()
        loader.attackServerSocket.close()
