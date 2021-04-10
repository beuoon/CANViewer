import copy
import os
import string
import sys
import time
from Kvaser import Kvaser

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *


class KvaserLoader(QThread):
    emitter = pyqtSignal(list)
    EMIT_INTERVAL = 0.1

    def run(self):
        # Kvaser 생성
        kvaser = Kvaser(channel=0)
        if not kvaser.valid:
            return

        # Load
        prev_emit_time = 0
        packet_list = []

        for frame in kvaser:
            if frame == 0:
                continue
            elif frame is None:  # error 체크
                break
            data = ' '.join(['{:02X}'.format(val) for val in frame.data])
            packet = [frame.timestamp / 1000000, '{:03X}'.format(frame.id), frame.dlc, data]
            packet_list.append(packet)

            if time.perf_counter() - prev_emit_time >= KvaserLoader.EMIT_INTERVAL:
                self.emitter.emit(packet_list)
                packet_list.clear()
                prev_emit_time = time.perf_counter()


class CANViewer(QWidget):
    ROW_MAX_LEN = 30

    def __init__(self, color_maintain_time=3):
        '''CAN Viewer

        EMIT_INTERVAL = 0.1
        :param file_path: 읽을 CSV 파일
        :param run_speed: 출력 속도 (EMIT_INTERVAL 마다 EMIT_INTERVAL*run_speed 만큼 출력)
        :param color_maintain_time: 변화한 데이터의 변화색 지속 시간
        '''
        super().__init__()
        self.layout = None
        self.labelDic = {}
        self.columnIndex = 0

        self.COLOR_MAINTAIN_TIME = color_maintain_time
        self.textColorMaintainTime = {}

        self.printable = copy.deepcopy(string.printable)
        self.printable = self.printable[:self.printable.find('\t')]

        self.valueInitFlag = False
        self.bgColorMaintainTime = {}
        self.prevByte = {}
        self.maxValue = {}
        self.valueDelta = {}

        self.loader = KvaserLoader()
        self.loader.emitter.connect(self.updatePacket)
        self.loader.start()

        self.initUI()

    def initUI(self):
        self.layout = QGridLayout()
        self.setLayout(self.layout)

        self.setWindowTitle('CAN Viewer')
        self.move(0, 0)
        self.resize(400, 200)
        self.show()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space:
            self.valueInitFlag = not self.valueInitFlag
            for id in self.bgColorMaintainTime:
                for idx in range(len(self.bgColorMaintainTime[id])):
                    self.bgColorMaintainTime[id][idx] = 0
            self.setLabelTextColor()

    def setLabelTextColor(self):
        current_time = time.perf_counter()

        for id in self.labelDic:
            data_label_list = self.labelDic[id][1]

            for idx in range(len(data_label_list)):
                if self.textColorMaintainTime[id][idx] > current_time:
                    color = 'red'
                else:
                    color = 'white'

                if not self.valueInitFlag:
                    bg_color = 'green'  # 초기화 중
                else:
                    if id in self.bgColorMaintainTime:
                        if self.bgColorMaintainTime[id][idx] > current_time:
                            if self.valueDelta[id][idx] == 0:
                                bg_color = 'green'  # 변하지 않던 값이 변함
                            else:
                                bg_color = '#FF8C00'  # 변동 값이 심해짐
                        else:
                            bg_color = 'black'  # 정상
                    else:
                        bg_color = '#3f0166'  # 이전에 존재하지 않던 ID
                
                data_label_list[idx].setStyleSheet(f'color: {color}; background-color: {bg_color}')

    @pyqtSlot(list)
    def updatePacket(self, packet_list):
        for packet in packet_list:
            id = packet[1]
            if len(id) < 3:
                id = (3-len(id))*'0' + id
            DLC = int(packet[2])
            data = packet[3]
            data_byte_list = data.split(' ')
            text = ''
            for byte in data.split(' '):
                try:
                    ch = chr(int('0x' + byte, 16))
                except:
                    ch = '.'

                if ch in self.printable:
                    text += ch
                else:
                    text += '.'

            # 데이터 변동 확인
            if not self.valueInitFlag:
                if id not in self.bgColorMaintainTime:
                    self.bgColorMaintainTime[id] = [0 for _ in range(DLC)]
                    self.valueDelta[id] = [0 for _ in range(DLC)]
                    self.maxValue[id] = [int('0x'+byte, 16) for byte in data_byte_list]
                else:
                    for idx in range(DLC):
                        max_value = self.maxValue[id][idx]
                        prev_value = int('0x'+self.prevByte[id][idx], 16)
                        curr_value = int('0x'+data_byte_list[idx], 16)
                        delta = abs(curr_value - prev_value)

                        if delta > self.valueDelta[id][idx]:
                            self.valueDelta[id][idx] = delta
                        if curr_value > max_value:
                            self.maxValue[id][idx] = curr_value

            # 데이터 변동에 따라 배경색 변경
            else:
                if id in self.bgColorMaintainTime:
                    maintain_end_time = time.perf_counter() + self.COLOR_MAINTAIN_TIME
                    for idx in range(DLC):
                        max_value = self.maxValue[id][idx]
                        prev_value = int('0x'+self.prevByte[id][idx], 16)
                        curr_value = int('0x'+data_byte_list[idx], 16)
                        delta = abs(curr_value - prev_value)
                        init_delta = self.valueDelta[id][idx]

                        if delta > init_delta*1.2 or init_delta == 0 and max_value != curr_value:  # or max_value < curr_value:
                            self.bgColorMaintainTime[id][idx] = maintain_end_time

            if id not in self.prevByte or len(self.prevByte) == DLC:
                self.prevByte[id] = data_byte_list

            # 새로운 컬럼 추가 및 포맷 정렬
            if id not in self.labelDic:
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

                maintain_end_time = time.perf_counter() + self.COLOR_MAINTAIN_TIME
                self.labelDic[id] = [id_label, data_label_list, text_label]
                self.textColorMaintainTime[id] = [maintain_end_time for _ in range(DLC)]

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

            # 텍스트 변경
            else:
                maintain_end_time = time.perf_counter() + self.COLOR_MAINTAIN_TIME
                for idx, data_label in enumerate(self.labelDic[id][1]):
                    if idx < len(data_byte_list) and data_label.text() != data_byte_list[idx]:
                        self.textColorMaintainTime[id][idx] = maintain_end_time
                        data_label.setText(data_byte_list[idx])

                text_label = self.labelDic[id][2]
                text_label.setText(text)

        self.setLabelTextColor()


if __name__ == '__main__':
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = './venv/Lib/site-packages/PyQt5/Qt/plugins/platforms'

    app = QApplication(sys.argv)
    app.setStyleSheet('QWidget{ background-color: black } QLabel{ color: white }')
    app.setFont(QFont('Consolas', 10), "QLabel")

    if len(sys.argv) >= 2:
        init_time = int(sys.argv[1])
    else:
        init_time = 30

    ex = CANViewer(color_maintain_time=3)

    sys.exit(app.exec_())
