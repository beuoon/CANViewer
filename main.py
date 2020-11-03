import copy
import os
import string
import sys
import time
import threading

import numpy as np
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from socket import *


class Loader(QThread):
    EMIT_INTERVAL = 0.1

    HOST = ''
    PORT = 45555
    BUFF_SIZE = 1024
    ADDRESS = (HOST, PORT)

    serverSocket = socket(AF_INET, SOCK_STREAM)
    serverSocket.bind(ADDRESS)

    serverSocket.listen(1)

    emitter = pyqtSignal(np.ndarray)
    bRun = True

    @staticmethod
    def RecvFunc(msg_list):
        clientSocket = None
        prev_data = ''

        while Loader.bRun:
            try:
                encoded_packet = clientSocket.recv(Loader.BUFF_SIZE)
                packet = encoded_packet.decode()
                data_list = packet.splitlines()

                data_list[0] = prev_data + data_list[0]
                prev_data = ''

                for data in data_list[:-1]:
                    msg = data.split(',')
                    msg_list.append(msg)

                data = data_list[-1]
                if packet[-1] != '\n':
                    prev_data = data
                else:
                    msg = data.split(',')
                    msg_list.append(msg)

            except:
                clientSocket, _ = Loader.serverSocket.accept()

    def run(self):
        msg_list = []
        t = threading.Thread(target=Loader.RecvFunc, args=(msg_list,))
        t.start()

        prev_emit_time = time.time()
        while self.bRun:
            if len(msg_list) > 0:
                try:
                    emit_msg = np.array(msg_list)
                except:
                    continue
                msg_list.clear()
                self.emitter.emit(emit_msg)

            elapse_time = time.time() - prev_emit_time
            prev_emit_time = time.time()
            if elapse_time < self.EMIT_INTERVAL:
                time.sleep(self.EMIT_INTERVAL - elapse_time)

        t.join()


class CANViewer(QWidget):
    ROW_MAX_LEN = 30

    def __init__(self, color_maintain_len=3):
        '''CAN Viewer

        EMIT_INTERVAL = 0.1
        :param file_path: 읽을 CSV 파일
        :param run_speed: 출력 속도 (EMIT_INTERVAL 마다 EMIT_INTERVAL*run_speed 만큼 출력)
        :param color_maintain_len: 변화한 데이터의 변화색 지속 시간 (EMIT_INTERVAL*color_maintain_len 만큼 지속)
        '''
        super().__init__()
        self.layout = None
        self.labelDic = {}
        self.columnIndex = 0

        self.COLOR_MAINTAIN_LEN = color_maintain_len
        self.valueChangedCount = {}

        self.printable = copy.deepcopy(string.printable)
        self.printable = self.printable[:self.printable.find('\t')]

        self.loader = Loader()
        self.loader.emitter.connect(self.updatePacket)
        self.loader.start()

        self.initUI()

    def initUI(self):
        self.layout = QGridLayout()
        self.setLayout(self.layout)

        self.setWindowTitle('CAN Viewer')
        self.move(300, 300)
        self.resize(400, 200)
        self.show()

    def setLabelTextColor(self):
        for id in self.labelDic:

            label = self.labelDic[id]
            for idx in range(len(self.valueChangedCount[id])):
                self.valueChangedCount[id][idx] -= 1

                if self.valueChangedCount[id][idx] > 0:
                    color = 'red'
                else:
                    color = 'white'

                label[1][idx].setStyleSheet(f'color: {color}')

    @pyqtSlot(np.ndarray)
    def updatePacket(self, packet_list):
        for packet in packet_list:
            id = packet[1]
            DLC = int(packet[2])
            data = packet[3]
            data_byte_list = data.split(' ')
            text = ''
            for byte in data.split(' '):
                ch = chr(int('0x' + byte, 16))
                if ch in self.printable:
                    text += ch
                else:
                    text += '.'

            if id not in self.labelDic:
                # 새로운 컬럼 추가
                if len(self.labelDic) % self.ROW_MAX_LEN == 0:
                    id_label = QLabel('ID')
                    id_label.setStyleSheet("min-width: 40px")
                    self.layout.addWidget(id_label, 0, self.columnIndex + 0)

                    data_label_list = []
                    for i in range(8):
                        if i == 0:
                            data_label = QLabel('Bytes')
                        else:
                            data_label = QLabel(' ')
                        data_label.setStyleSheet("min-width: 20px")
                        self.layout.addWidget(data_label, 0, self.columnIndex + i+1)
                        data_label_list.append(data_label)

                    text_label = QLabel('Text')
                    text_label.setStyleSheet("min-width: 100px")
                    self.layout.addWidget(text_label, 0, self.columnIndex + 9)

                    self.columnIndex += 10

                # 새로운 ID 추가
                id_label = QLabel(id)
                id_label.setStyleSheet("min-width: 40px")

                data_label_list = []
                for data_byte in data_byte_list:
                    data_label = QLabel(data_byte)
                    data_label.setStyleSheet("min-width: 20px")
                    data_label_list.append(data_label)

                text_label = QLabel(text)
                text_label.setStyleSheet("min-width: 100px")

                self.labelDic[id] = [id_label, data_label_list, text_label]
                self.valueChangedCount[id] = [self.COLOR_MAINTAIN_LEN for _ in range(DLC)]

                # 정렬 및 Reformat
                keys = sorted(self.labelDic.keys())
                for idx, key in enumerate(keys):
                    row = idx % self.ROW_MAX_LEN + 1
                    column = (idx // self.ROW_MAX_LEN) * 10

                    label = self.labelDic[key]
                    self.layout.addWidget(label[0], row, column + 0)
                    for i, data_label in enumerate(label[1]):
                        self.layout.addWidget(data_label, row, column + i+1)
                    self.layout.addWidget(label[2], row, column + 9)
            else:
                # 텍스트 변경
                for idx, data_label in enumerate(self.labelDic[id][1]):
                    if data_label.text() != data_byte_list[idx]:
                        self.valueChangedCount[id][idx] = self.COLOR_MAINTAIN_LEN
                        data_label.setText(data_byte_list[idx])

                text_label = self.labelDic[id][2]
                text_label.setText(text)

        self.setLabelTextColor()


if __name__ == '__main__':
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = './can_env/Lib/site-packages/PyQt5/Qt/plugins/platforms'

    app = QApplication(sys.argv)
    app.setStyleSheet('QWidget{ background-color: black } QLabel{ color: white }')
    app.setFont(QFont('Consolas', 10), "QLabel")

    ex = CANViewer(color_maintain_len=3)

    sys.exit(app.exec_())
