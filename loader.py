import pandas as pd
from tqdm import tqdm
import time
import socket
import sys


class FileLoader:
    HOST = '127.0.0.1'
    PORT = 45555

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((HOST, PORT))

    csvPath = None

    runSpeed = 0.05

    EMIT_INTERVAL = 0.1
    PACKET_INTERVAL = EMIT_INTERVAL * runSpeed

    def setFilePath(self, file_path):
        self.csvPath = file_path

    def setRunSpeed(self, run_speed):
        self.runSpeed = run_speed
        self.PACKET_INTERVAL = self.EMIT_INTERVAL * self.runSpeed

    def run(self):
        if self.csvPath is None:
            return

        df = pd.read_csv(self.csvPath)

        values = df.values
        packet_len = len(df.index)

        pbar = tqdm(total=packet_len)

        prev_timestamp = values[0][0]

        prev_emit_time = time.time()
        prev_idx = 0
        idx = 0
        while idx < packet_len:
            while idx < packet_len:
                timestamp = values[idx][0]
                if timestamp > prev_timestamp + self.PACKET_INTERVAL:
                    break
                record = '{},{},{},'.format(values[idx][0], values[idx][1], values[idx][2])
                record += values[idx][3] + '\n'
                self.client_socket.sendall(record.encode())
                idx += 1

            pbar.update(idx-prev_idx+1)
            prev_idx = idx + 1
            prev_timestamp = prev_timestamp + self.PACKET_INTERVAL

            elapse_time = time.time() - prev_emit_time
            prev_emit_time = time.time()
            if elapse_time < self.EMIT_INTERVAL:
                time.sleep(self.EMIT_INTERVAL - elapse_time)

        pbar.close()


if __name__ == '__main__':
    # Parsing Path Argument
    if len(sys.argv) < 2:
        print('need dataset file')
        exit(1)
    data_file_path = sys.argv[1]

    # Parsing Run Speed Argument
    if len(sys.argv) >= 3:
        run_speed = float(sys.argv[2])
    else:
        run_speed = 0.01

    loader = FileLoader()
    loader.setFilePath(data_file_path)
    loader.setRunSpeed(run_speed)
    loader.run()
