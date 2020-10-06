import os
import time
from collections import deque
from datetime import datetime
from threading import Thread

import cv2


class VideoStream:
    """
    Class that continuously gets frames from a cv2 VideoCapture object
    with a dedicated thread.
    """

    def __init__(self, camName, src, isVideoFile=True, queueSize=5, writeDir=None, reconnectThreshold=20,
                 resize_fn=None):
        self.camName = camName
        self.src = src
        self.stream = cv2.VideoCapture(self.src)
        self.reconnectThreshold = reconnectThreshold
        self.pauseTime = None
        self.stopped = True
        self.Q = deque(maxlen=queueSize)
        self.resize_fn = resize_fn
        self.inited = False
        self.isVideoFile = isVideoFile
        self.vidInfo = {}
        self.writeDir = writeDir

        if self.writeDir is not None:
            self.record_tracks = True
            if not os.path.isdir(self.writeDir):
                os.makedirs(self.writeDir)
        else:
            self.record_tracks = False

    def init_src(self):
        try:
            self.stream = cv2.VideoCapture(self.src)
            if self.isVideoFile:
                self.fps = int(self.stream.get(cv2.CAP_PROP_FPS))
            else:
                self.fps = int(os.environ.get('ORIG_FPS', 15))
            # width and height returns 0 if stream not captured
            self.vid_width = int(self.stream.get(3))
            self.vid_height = int(self.stream.get(4))
            self.vidInfo = {'height': self.vid_height, 'width': self.vid_width, 'fps': self.fps, 'inited': False}

            self.out_vid = None

            if self.vid_width != 0:
                self.inited = True
                self.vidInfo['inited'] = True

            if self.record_tracks and self.inited:
                now = datetime.now()
                day = now.strftime("%Y_%m_%d_%H-%M-%S")
                out_vid_fp = os.path.join(
                    self.writeDir, 'orig_{}_{}.avi'.format(self.camName, day))
                self.out_vid = cv2.VideoWriter(out_vid_fp, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'), int(
                    self.fps), (self.vid_width, self.vid_height))

        except Exception as error:
            print('init stream {} error: {}'.format(self.camName, error))

    def start(self):
        self.init_src()
        self.stopped = False

        t = Thread(target=self.get, args=())
        t.start()

        print('start video streaming for {}'.format(self.camName))
        return self

    def reconnect_start(self):
        s = Thread(target=self.reconnect, args=())
        s.start()
        return self

    def get(self):
        while not self.stopped:
            try:
                # print('getting video' + str(time.time()))
                grabbed, frame = self.stream.read()

                if grabbed:
                    self.Q.appendleft(frame)

                    if self.record_tracks:
                        try:
                            self.out_vid.write(frame)
                        except Exception as e:
                            pass

                    if self.isVideoFile:
                        time.sleep(1 / self.fps)

            except Exception as e:
                print('stream grab {} error: {}'.format(self.camName, e))
                grabbed = False

            if not grabbed:
                if self.pauseTime is None:
                    self.pauseTime = time.time()
                    self.printTime = time.time()
                    print('No frames for {}, starting {:0.1f}sec countdown to reconnect.'. \
                          format(self.camName, self.reconnectThreshold))
                time_since_pause = time.time() - self.pauseTime
                time_since_print = time.time() - self.printTime
                if time_since_print > 1:  # prints only every 1 sec
                    print('No frames for {}, reconnect starting in {:0.1f}sec'. \
                          format(self.camName, self.reconnectThreshold - time_since_pause))
                    self.printTime = time.time()

                if time_since_pause > self.reconnectThreshold:
                    self.reconnect_start()
                    break
                continue

            self.pauseTime = None

    def read(self):
        if self.more():
            self.currentFrame = self.Q.pop()
        if self.resize_fn:
            self.currentFrame = self.resize_fn(self.currentFrame)
        return self.currentFrame

    def more(self):
        return bool(self.Q)

    def stop(self):
        if not self.stopped:
            self.stopped = True
            time.sleep(0.1)

            if self.stream:
                self.stream.release()

            if self.more():
                self.Q.clear()

            if self.out_vid:
                self.out_vid.release()

            print('stop video streaming for {}'.format(self.camName))

    def reconnect(self):
        print('Reconnecting')
        if self.stream:
            self.stream.release()

        if self.more():
            self.Q.clear()

        while not self.stream.isOpened():
            print(str(datetime.now()), 'Reconnecting to', self.camName)
            self.stream = cv2.VideoCapture(self.src)
        if not self.stream.isOpened():
            return ('error opening {}'.format(self.camName))

        if not self.inited:
            self.init_src()

        print('VideoStream for {} initialised!'.format(self.camName))
        self.pauseTime = None
        self.start()
